"""낙찰 수집을 받치는 부분: 클라이언트(7일 창·페이지 상한·소스 예산), 예산 집계, /readyz,
재분류 스크립트, CLI (SPEC §15.2~§15.4)."""

from datetime import timedelta

import pytest
from sqlalchemy import select

from app.awards import collector as awards
from app.awards.reclassify import reclassify
from app.collector import __main__ as collector_cli
from app.db.models import BidAward, CollectorRun, OrgSettings, UsageLog
from app.g2b.client import G2BBudgetExceeded, G2BClient, G2BIncomplete, collect_shortfalls
from app.ops.status import last_collector_ok
from app.usage.budget import DbCallBudget
from tests.conftest import NOW, TEST_KEYS
from tests.fakes.g2b import FakeG2B, award_item, contract_item, regular_item
from tests.helpers import seed


def _client(fake: FakeG2B, **kw) -> G2BClient:
    return G2BClient(fake.http_client(), TEST_KEYS, retry_delays=(0, 0, 0), **kw)


async def test_awards_fetch_splits_by_kst_dates():
    """클라이언트도 날짜 7개 단위로 자른다(수집기가 아닌 곳에서 불러도 07 오류 없음)."""
    fake = FakeG2B()
    fake.add("awards", award_item("R26BK00000001", NOW - timedelta(days=9)))
    items = await _client(fake).fetch("awards", NOW - timedelta(days=14), NOW)
    got = [(r.url.params["inqryBgnDt"], r.url.params["inqryEndDt"]) for r in fake.requests]
    assert len(items) == 1
    assert got == [
        ("202610271500", "202611022359"),
        ("202611030000", "202611092359"),
        ("202611100000", "202611101459"),
    ]


async def test_page_size_is_capped_at_999():
    """numOfRows=1000은 실제 API가 조용히 10행만 준다 (probe 2번)."""
    fake = FakeG2B()
    await _client(fake, page_size=1000).fetch("awards", NOW - timedelta(days=1), NOW)
    assert fake.requests[0].url.params["numOfRows"] == "999"


async def test_missing_rows_raise_incomplete_for_awards_only():
    fake = FakeG2B()
    fake.add(
        "awards", *(award_item(f"R26BK1{i:07d}", NOW - timedelta(minutes=i + 1)) for i in range(15))
    )
    fake.add(
        "regular",
        *(regular_item(f"R26BK2{i:07d}", NOW - timedelta(minutes=i + 1)) for i in range(15)),
    )
    fake.hidden = {"R26BK10000001", "R26BK10000002", "R26BK10000003"}  # 허용치(1행)를 넘게 빠짐
    with pytest.raises(G2BIncomplete):
        await _client(fake, page_size=10).fetch("awards", NOW - timedelta(days=1), NOW)
    fake.drop_pages = {2}
    # 공고 수집은 기존 동작 그대로(받은 만큼)
    assert (
        len(await _client(fake, page_size=10).fetch("regular", NOW - timedelta(days=1), NOW)) == 10
    )


class _Budget:
    def __init__(self, limit: int) -> None:
        self.limit, self.pending, self.settled = limit, 0, 0

    async def reserve(self) -> None:
        if self.pending >= self.limit:
            raise G2BBudgetExceeded("소진")
        self.pending += 1

    def settle(self, n: int) -> None:
        self.pending -= n
        self.settled += n


async def test_source_budget_is_returned_when_global_budget_refuses():
    fake = FakeG2B()
    src, total = _Budget(5), _Budget(0)
    c = _client(fake, budget=total, source_budgets={"awards": src})
    with pytest.raises(G2BBudgetExceeded):
        await c.fetch("awards", NOW - timedelta(days=1), NOW)
    assert src.pending == 0 and fake.calls == 0
    # 공고 소스는 awards 예산을 쓰지 않는다
    total.limit = 10
    await c.fetch("regular", NOW - timedelta(days=1), NOW)
    assert src.pending == 0 and total.pending == 1


async def test_db_budget_counts_only_its_sources(db):
    async with db.transaction() as s:
        s.add_all(
            [
                UsageLog(event="collector", g2b_calls=7, cache={"source": "regular"}),
                UsageLog(event="collector", g2b_calls=3, cache={"source": "awards"}),
                UsageLog(event="search", g2b_calls=2, cache={}),
            ]
        )
    assert await DbCallBudget(db, 100).used_today() == 12
    assert await DbCallBudget(db, 100, sources={"awards", "contracts"}).used_today() == 3
    b = DbCallBudget(db, 3, sources={"awards"}, label="낙찰")
    with pytest.raises(G2BBudgetExceeded, match="낙찰 일일 호출 예산 3회"):
        await b.reserve()


async def test_readyz_last_ok_ignores_award_runs(deps):
    async with deps.db.transaction() as s:
        s.add(
            CollectorRun(
                source="awards",
                mode="incremental",
                window_from=NOW,
                window_to=NOW,
                status="ok",
                finished_at=NOW,
            )
        )
    assert await last_collector_ok(deps) is None


async def test_reclassify_recomputes_fields_and_prices(deps, fake_g2b):
    fake_g2b.add(
        "awards",
        award_item(
            "R26BK30000001",
            NOW - timedelta(hours=1),
            title="빅데이터 플랫폼 구축",
            amount="45000000",
        ),
    )
    await awards.backfill(deps, days=7)
    # 사전과 bids가 나중에 바뀜
    async with deps.db.transaction() as s:
        s.add(OrgSettings(id=1, field_keywords={"데이터": ["빅데이터"]}))
    await seed(
        deps, "regular", regular_item("R26BK30000001", NOW - timedelta(days=20), budget="50000000")
    )
    r1 = await reclassify(deps.db, batch=1)
    r2 = await reclassify(deps.db)
    assert (r1.scanned, r1.fields_changed, r1.prices_changed) == (1, 1, 1)
    assert (r2.fields_changed, r2.prices_changed) == (0, 0)  # 같은 사전이면 그대로
    async with deps.db.session() as s:
        row = await s.scalar(select(BidAward))
    assert row.fields == ["데이터"] and row.estimated_price == 50_000_000
    assert str(row.award_ratio) == "0.90000"


async def test_cli_refetch_only_for_awards_and_contracts_with_dates():
    with pytest.raises(SystemExit):
        await collector_cli.main(
            ["refetch", "--source", "regular", "--from", "2026-11-01", "--to", "2026-11-02"]
        )
    with pytest.raises(SystemExit):
        await collector_cli.main(["refetch", "--source", "awards"])


async def test_cli_rejects_fill_for_awards():
    with pytest.raises(SystemExit):
        await collector_cli.main(
            ["fill", "--source", "awards", "--from", "2026-11-01", "--to", "2026-11-02"]
        )


# ---------- 페이지 겹침·행 누락 (docs/decisions/2026-11-25-awards-paging.md) ----------


def _ntce(it):
    return it.get("bidNtceNo") or it.get("ntceNo")


@pytest.mark.parametrize("source", ["awards", "contracts"])
async def test_unstable_paging_is_avoided_by_splitting_windows(source):
    # G2B는 페이지를 넘기면 순서가 흔들려 겹친다: 창을 쪼개 한 페이지에 다 받는다
    fake = FakeG2B()
    make = (
        (lambda n, t: award_item(n, t))
        if source == "awards"
        else (lambda n, t: contract_item(n, t, [("주계약업체", "가", "60", "1234567890")]))
    )
    fake.add(
        source, *(make(f"R26BK3{i:07d}", NOW - timedelta(minutes=7 * i + 1)) for i in range(45))
    )
    fake.page_overlap = 2
    items = await _client(fake, page_size=10).fetch(source, NOW - timedelta(days=1), NOW)
    assert sorted(_ntce(i) for i in items) == sorted(f"R26BK3{i:07d}" for i in range(45))
    assert all(r.url.params["pageNo"] == "1" for r in fake.requests)


async def test_one_missing_row_in_a_page_is_tolerated_and_noted():
    # 2017-04-17 오전: G2B가 173건이라 하고 172행만 준다 → 넘어가되 기록
    fake = FakeG2B()
    fake.add(
        "awards", *(award_item(f"R26BK4{i:07d}", NOW - timedelta(minutes=i + 1)) for i in range(8))
    )
    fake.hidden = {"R26BK40000003"}
    with collect_shortfalls() as notes:
        items = await _client(fake, page_size=10).fetch("awards", NOW - timedelta(days=1), NOW)
    assert len(items) == 7
    assert len(notes) == 1 and "7/8" in notes[0]
