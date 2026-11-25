"""결과 감시 등록·맞추기 (계획 Task 4). DB만 쓰고 G2B를 부르지 않는다."""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import insert, select

from app.db.models import Bid, BidResultWatch, Bookmark
from app.results.watch import ensure_watch, opening_of, sync_watches
from tests.conftest import NOW
from tests.fakes.g2b import kst_str, prespec_item, regular_item
from tests.helpers import create_user, seed


def _regular(no: str, opening, ord: str = "000") -> dict:
    it = regular_item(no, NOW - timedelta(days=3), ord=ord)
    it["opengDt"] = opening if isinstance(opening, str) else kst_str(opening)
    return it


async def _bid(deps, item: dict, source: str = "regular") -> Bid:
    (bid_id,) = await seed(deps, source, item)
    async with deps.db.session() as s:
        return await s.get_one(Bid, bid_id)


async def _watch(deps, bid_id: int) -> BidResultWatch | None:
    async with deps.db.session() as s:
        return await s.get(BidResultWatch, bid_id)


async def test_future_opening_watched(deps):
    bid = await _bid(deps, _regular("R26BK90000001", NOW + timedelta(days=2)))
    async with deps.db.transaction() as s:
        w = await ensure_watch(s, bid, NOW)
    assert w is not None
    got = await _watch(deps, bid.id)
    assert got is not None
    assert (got.stage, got.notice_ord) == ("waiting", "000")
    assert got.opening_at == NOW + timedelta(days=2)
    assert got.next_check_at == got.opening_at


async def test_prespec_not_watched(deps):
    bid = await _bid(deps, prespec_item("R26BD00000001", NOW - timedelta(days=1)), "prespec")
    async with deps.db.transaction() as s:
        assert await ensure_watch(s, bid, NOW) is None
    assert await _watch(deps, bid.id) is None


async def test_missing_opening_not_watched(deps):
    """개찰일이 없거나 깨진 공고는 감시하지 않는다(Review 3)."""
    for no, opening in (("R26BK90000002", ""), ("R26BK90000003", "미정")):
        bid = await _bid(deps, _regular(no, opening))
        assert opening_of(bid) is None
        async with deps.db.transaction() as s:
            assert await ensure_watch(s, bid, NOW) is None


async def test_old_opening_not_watched(deps):
    bid = await _bid(deps, _regular("R26BK90000004", NOW - timedelta(days=8)))
    async with deps.db.transaction() as s:
        assert await ensure_watch(s, bid, NOW) is None


async def test_revision_reschedules(deps):
    """정정공고로 차수·개찰일이 바뀌면 새 값으로 다시 일정을 잡는다(Review 2)."""
    no = "R26BK90000005"
    bid = await _bid(deps, _regular(no, NOW + timedelta(days=1)))
    async with deps.db.transaction() as s:
        await ensure_watch(s, bid, NOW)
    new_open = NOW + timedelta(days=4)
    bid = await _bid(deps, _regular(no, new_open, ord="001"))
    async with deps.db.transaction() as s:
        await ensure_watch(s, bid, NOW)
    got = await _watch(deps, bid.id)
    assert got is not None
    assert (got.notice_ord, got.opening_at, got.next_check_at) == ("001", new_open, new_open)
    assert got.stage == "waiting"


async def test_sync_creates_for_existing_bookmarks(deps):
    """기존 북마크(알림 켬)는 실행할 때 감시 행이 생긴다. 끈 북마크·사전규격은 안 생긴다."""
    on = await _bid(deps, _regular("R26BK90000006", NOW + timedelta(hours=5)))
    off = await _bid(deps, _regular("R26BK90000007", NOW + timedelta(hours=5)))
    pre = await _bid(deps, prespec_item("R26BD00000002", NOW - timedelta(days=1)), "prespec")
    uid = await create_user(deps.db, "w@corp.example")
    async with deps.db.transaction() as s:
        await s.execute(
            insert(Bookmark),
            [
                {"user_id": uid, "bid_id": on.id},
                {"user_id": uid, "bid_id": off.id, "notify_result": False},
                {"user_id": uid, "bid_id": pre.id},
            ],
        )
    async with deps.db.transaction() as s:
        assert await sync_watches(s, NOW) == 1
    async with deps.db.session() as s:
        ids = (await s.execute(select(BidResultWatch.bid_id))).scalars().all()
    assert ids == [on.id]


async def test_past_opening_checked_right_away(deps):
    """개찰이 이미 지난 공고에 감시를 걸면 바로 확인한다(5분 뒤가 아니라)."""
    bid = await _bid(deps, _regular("R26BK90000008", NOW - timedelta(hours=1)))
    async with deps.db.transaction() as s:
        await ensure_watch(s, bid, NOW)
    got = await _watch(deps, bid.id)
    assert got is not None and got.next_check_at == NOW
