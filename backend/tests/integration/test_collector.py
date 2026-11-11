"""수집기: 커버리지 불변식·upsert 멱등·실패 처리 (SPEC §5.3, §12.3, §5.9-9)."""

from datetime import timedelta

import httpx
from sqlalchemy import func, select

from app.collector import runner
from app.db.models import Bid, BidFile, CollectorCoverage, CollectorRun
from tests.conftest import NOW
from tests.fakes.g2b import prespec_item, regular_item
from tests.helpers import seed


async def _coverage(deps, source):
    async with deps.db.session() as s:
        return await s.get(CollectorCoverage, source)


async def _count(deps, model):
    async with deps.db.session() as s:
        return await s.scalar(select(func.count()).select_from(model))


async def test_backfill_covers_window_without_gaps(deps, fake_g2b):
    for d in range(5):
        fake_g2b.add("regular", regular_item(f"R26BK0000{d:04d}", NOW - timedelta(days=d, hours=1)))
    result = await runner.backfill(deps, "regular", days=5)
    cov = await _coverage(deps, "regular")
    assert result.status == "ok"
    assert cov.covered_from <= NOW - timedelta(days=5) and cov.covered_to >= NOW
    assert await _count(deps, Bid) == 5
    # 하루 창 5개 → 1일 단위 호출 (G2B 15일 제한 안쪽)
    assert fake_g2b.calls == 5


async def test_same_window_twice_creates_no_duplicates(deps, fake_g2b):
    fake_g2b.add(
        "regular",
        *(regular_item(f"R26BK1000{i:04d}", NOW - timedelta(hours=i + 1)) for i in range(7)),
    )
    await runner.backfill(deps, "regular", days=1)
    await runner.backfill(deps, "regular", days=1)
    assert await _count(deps, Bid) == 7
    async with deps.db.session() as s:
        assert set((await s.execute(select(Bid.revision))).scalars()) == {1}


async def test_incremental_moves_covered_to_and_overlaps_30_minutes(deps, fake_g2b):
    await runner.backfill(deps, "regular", days=1)
    later = NOW + timedelta(hours=2)
    fake_g2b.add("regular", regular_item("R26BK20000001", NOW + timedelta(minutes=50)))
    deps.clock = lambda: later
    result = await runner.incremental(deps, "regular")
    cov = await _coverage(deps, "regular")
    assert result.status == "ok" and cov.covered_to == later
    # covered_to(=NOW, KST 15:00)에서 30분 겹쳐 시작
    assert fake_g2b.requests[-1].url.params["inqryBgnDt"] == "202611101430"
    assert await _count(deps, Bid) == 1


async def test_g2b_5xx_three_times_keeps_boundary_and_marks_failed(deps, fake_g2b):
    """§5.9-9: 5xx를 3번(재시도 포함 전부) 받으면 경계는 그대로, collector_runs.status=failed."""
    await runner.backfill(deps, "regular", days=1)
    before = await _coverage(deps, "regular")
    fake_g2b.fail(*(httpx.Response(503, text="busy") for _ in range(4)))
    deps.clock = lambda: NOW + timedelta(hours=3)
    result = await runner.incremental(deps, "regular")
    after = await _coverage(deps, "regular")
    assert result.status == "failed"
    assert (after.covered_from, after.covered_to) == (before.covered_from, before.covered_to)
    async with deps.db.session() as s:
        statuses = (
            (await s.execute(select(CollectorRun.status).order_by(CollectorRun.id))).scalars().all()
        )
    assert statuses == ["ok", "failed"]


async def test_lower_order_row_never_overwrites_newer(deps):
    """정정 차수가 거꾸로 도착해도 큰 차수가 남는다 (docs/decisions/2026-11-11-g2b-probe.md)."""
    newer = regular_item("R26BK30000001", NOW, ord="002", title="[취소] 공고", kind="취소공고")
    older = regular_item(
        "R26BK30000001", NOW - timedelta(hours=1), ord="001", title="[변경] 공고", kind="변경공고"
    )
    (bid_id,) = await seed(deps, "regular", newer)
    await seed(deps, "regular", older)
    async with deps.db.session() as s:
        bid = await s.get(Bid, bid_id)
    assert bid.title == "[취소] 공고" and bid.revision == 1


async def test_same_batch_keeps_highest_order(deps):
    rows = [
        regular_item("R26BK30000002", NOW, ord=o, title=f"차수 {o}") for o in ("000", "002", "001")
    ]
    (bid_id,) = await seed(deps, "regular", rows[0])
    await seed(deps, "regular", *rows)
    async with deps.db.session() as s:
        assert (await s.get(Bid, bid_id)).title == "차수 002"


async def test_upsert_adds_bid_files_once(deps):
    url = "https://www.g2b.go.kr/f/1.hwp"
    item = regular_item("R26BK30000003", NOW, files=[(url, "과업지시서.hwp")])
    await seed(deps, "regular", item)
    await seed(deps, "regular", item)
    async with deps.db.session() as s:
        files = (await s.execute(select(BidFile))).scalars().all()
    assert [(f.kind, f.origin, f.status) for f in files] == [("rfp", "notice", "new")]


async def test_prespec_source_is_collected_separately(deps, fake_g2b):
    fake_g2b.add("prespec", prespec_item("R26BD00000001", NOW - timedelta(hours=2)))
    await runner.backfill(deps, "prespec", days=1)
    assert await _coverage(deps, "regular") is None
    async with deps.db.session() as s:
        bid = (await s.execute(select(Bid))).scalar_one()
    assert bid.bid_key == "prespec:R26BD00000001" and bid.budget == 50_000_000
