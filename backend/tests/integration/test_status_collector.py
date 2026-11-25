"""개찰 상태 수집 `status` (2026-11-26, specs/2026-11-26-closed-bid-reason-design.md).

개찰결과 목록을 개찰일시(inqryDiv=3) 창으로 받아 bid_opening_status에 덮어쓴다.
"""

from datetime import timedelta

from sqlalchemy import func, select

from app.awards import status
from app.db.models import BidOpeningStatus, CollectorCoverage, UsageLog
from app.g2b.client import G2BClient
from tests.conftest import NOW, TEST_KEYS
from tests.fakes.g2b import kst_str, status_item


async def _rows(deps):
    async with deps.db.session() as s:
        return {r.key: r for r in (await s.scalars(select(BidOpeningStatus))).all()}


def _st(no, st, hours_ago, **kw):
    return status_item(no, st, opened_at=kst_str(NOW - timedelta(hours=hours_ago)), **kw)


async def test_incremental_takes_yesterday_and_today_and_overwrites(deps, fake_g2b):
    fake_g2b.add(
        "opening_status",
        _st("R26BK00000001", "유찰", 2),
        _st("R26BK00000002", "재입찰", 20),
        _st("R26BK00000003", "개찰완료", 24 * 5),  # 증분 창 밖
    )
    first = await status.incremental(deps)
    assert first.status == "ok", first.error
    rows = await _rows(deps)
    assert set(k[0] for k in rows) == {"R26BK00000001", "R26BK00000002"}
    assert rows[("R26BK00000001", "000", "0", "000")].status == "유찰"
    assert all("inqryDiv=3" in str(r.url) for r in fake_g2b.requests)
    # 같은 키가 바뀌어 다시 오면 덮어쓴다(재입찰 → 개찰완료)
    fake_g2b.items["opening_status"][1]["progrsDivCdNm"] = "개찰완료"
    again = await status.incremental(deps)
    assert again.status == "ok" and again.inserted == 0
    assert (await _rows(deps))[("R26BK00000002", "000", "0", "000")].status == "개찰완료"
    async with deps.db.session() as s:
        logged = await s.scalar(
            select(func.sum(UsageLog.g2b_calls)).where(UsageLog.cache["source"].astext == "status")
        )
        cov = await s.get(CollectorCoverage, "status")
    assert logged == fake_g2b.calls and cov is not None and cov.covered_to == NOW


async def test_backfill_splits_a_day_over_one_page(deps, fake_g2b):
    """하루가 한 페이지보다 많으면 시간으로 나눠 받는다(페이지 넘김 없음)."""
    deps.g2b = G2BClient(fake_g2b.http_client(), TEST_KEYS, page_size=3, retry_delays=(0, 0, 0))
    fake_g2b.add(
        "opening_status",
        *(_st(f"R26BK1{i:07d}", "개찰완료", 30 + i) for i in range(7)),
        _st("R26BK19999999", "유찰", 24 * 9),
    )
    r = await status.backfill(deps, days=10)
    assert r.status == "ok", r.error
    assert len(await _rows(deps)) == 8
    assert all(r.url.params.get("pageNo") == "1" for r in fake_g2b.requests)
