"""결과 확인기 (계획 Task 5). 가짜 G2B로 개찰·낙찰·유찰·재입찰·재공고·예산 소진을 본다."""

from __future__ import annotations

import dataclasses
from datetime import timedelta

from sqlalchemy import func, insert, select

from app.db.models import BidAward, BidParticipant, BidResultWatch, Bookmark
from app.g2b.client import RESULT_WATCH_SOURCE, G2BClient
from app.results.checker import Change, check_due, same_title
from app.results.watch import ensure_watch
from app.usage.budget import DbCallBudget
from tests.conftest import NOW, TEST_KEYS
from tests.fakes.g2b import award_item, kst_str, opening_item, regular_item, status_item
from tests.helpers import create_user, seed

NO = "R26BK91000001"
ORG = "행정안전부"
TITLE = "데이터 정비 용역"


def _regular(
    no: str, opening, *, title: str = TITLE, org: str = ORG, renotice: str = "N", notice=None
):
    it = regular_item(no, notice or NOW - timedelta(days=5), title=title)
    it.update(opengDt=kst_str(opening), dminsttNm=org, reNtceYn=renotice)
    return it


async def _watched(deps, no: str = NO, opening=None, stage: str = "waiting") -> int:
    """북마크(알림 켬) + 감시 행. 개찰 1시간 전이 기본이라 확인할 때가 됐다."""
    opening = opening or NOW - timedelta(hours=1)
    (bid_id,) = await seed(
        deps, "regular", _regular(no, opening, notice=opening - timedelta(days=7))
    )
    uid = await create_user(deps.db, f"{no.lower()}@corp.example")
    async with deps.db.transaction() as s:
        await s.execute(insert(Bookmark).values(user_id=uid, bid_id=bid_id))
        from app.db.models import Bid

        bid = await s.get_one(Bid, bid_id)
        w = await ensure_watch(s, bid, opening - timedelta(hours=1))
        assert w is not None
        w.stage = stage
        w.next_check_at = NOW - timedelta(minutes=1)
    return bid_id


async def _w(deps, bid_id: int) -> BidResultWatch:
    async with deps.db.session() as s:
        return await s.get_one(BidResultWatch, bid_id)


async def _count(deps, model) -> int:
    async with deps.db.session() as s:
        return int(await s.scalar(select(func.count()).select_from(model)) or 0)


async def test_opening_found_moves_to_opened(deps, fake_g2b):
    bid_id = await _watched(deps)
    fake_g2b.add("opening_status", status_item(NO, "개찰완료"))
    fake_g2b.add(
        "opening_compt",
        opening_item(NO, "1111111111", rank="1"),
        opening_item(NO, "2222222222", rank="2", name="나래"),
    )
    assert await check_due(deps, NOW) == [Change(bid_id, "opened")]
    w = await _w(deps, bid_id)
    assert (w.stage, w.opened_at) == ("opened", NOW)
    assert await _count(deps, BidParticipant) == 2
    assert await _count(deps, BidAward) == 0


async def test_award_found_moves_to_final(deps, fake_g2b):
    bid_id = await _watched(deps, stage="opened")
    fake_g2b.add("opening_status", status_item(NO, "개찰완료"))
    fake_g2b.add("awards", award_item(NO, NOW))
    assert await check_due(deps, NOW) == [Change(bid_id, "final")]
    w = await _w(deps, bid_id)
    assert (w.stage, w.final_kind, w.final_at) == ("final", "awarded", NOW)
    assert await _count(deps, BidAward) == 1


async def test_award_before_opening_single_change(deps, fake_g2b):
    """한 번에 개찰과 낙찰이 다 보이면 Change(final) 하나(메일 1통에 순위·투찰가 포함)."""
    bid_id = await _watched(deps)
    fake_g2b.add("opening_status", status_item(NO, "개찰완료"))
    fake_g2b.add("opening_compt", opening_item(NO, "1111111111"))
    fake_g2b.add("awards", award_item(NO, NOW, bizno="1111111111"))
    assert await check_due(deps, NOW) == [Change(bid_id, "final")]
    w = await _w(deps, bid_id)
    assert (w.stage, w.final_kind, w.opened_at) == ("final", "awarded", None)
    assert await _count(deps, BidParticipant) == 1


async def test_no_result_reschedules(deps, fake_g2b):
    bid_id = await _watched(deps)
    assert await check_due(deps, NOW) == []
    w = await _w(deps, bid_id)
    assert (w.stage, w.checks, w.next_check_at) == ("waiting", 1, NOW + timedelta(minutes=5))


async def test_expired_after_60_days(deps, fake_g2b):
    """60일 지나면 G2B를 부르지 않고 그만(메일 없음)."""
    bid_id = await _watched(deps)
    async with deps.db.transaction() as s:
        w = await s.get_one(BidResultWatch, bid_id)
        w.opening_at = NOW - timedelta(days=61)
    assert await check_due(deps, NOW) == []
    assert (await _w(deps, bid_id)).stage == "expired"
    assert fake_g2b.calls == 0


async def test_failed_kind(deps, fake_g2b):
    bid_id = await _watched(deps)
    fake_g2b.add("opening_status", status_item(NO, "유찰"))
    assert await check_due(deps, NOW) == [Change(bid_id, "final")]
    w = await _w(deps, bid_id)
    assert (w.stage, w.final_kind) == ("final", "failed")


async def test_rebid_and_residam_keep_watching(deps, fake_g2b):
    """재입찰·재시담은 같은 공고에서 다시 개찰하므로 최종이 아니다."""
    a = await _watched(deps, "R26BK91000002")
    b = await _watched(deps, "R26BK91000003")
    fake_g2b.add("opening_status", status_item("R26BK91000002", "재입찰"))
    fake_g2b.add("opening_status", status_item("R26BK91000003", "재시담"))
    assert await check_due(deps, NOW) == []
    assert [(await _w(deps, x)).stage for x in (a, b)] == ["waiting", "waiting"]


async def test_multiple_classes_one_change(deps, fake_g2b):
    """분류 2개·재입찰 행이 있어도 Change는 하나. 한 분류라도 개찰완료면 유찰이 아니다(Review 1)."""
    bid_id = await _watched(deps)
    fake_g2b.add(
        "opening_status",
        status_item(NO, "개찰완료", clsfc="1"),
        status_item(NO, "재입찰", clsfc="2", rbid="000"),
        status_item(NO, "유찰", clsfc="2", rbid="001"),
    )
    fake_g2b.add(
        "opening_compt",
        opening_item(NO, "1111111111", clsfc="1"),
        opening_item(NO, "2222222222", clsfc="1", rank="2"),
    )
    assert await check_due(deps, NOW) == [Change(bid_id, "opened")]


async def _failed_watch(deps, failed_days_ago: float) -> int:
    bid_id = await _watched(deps, opening=NOW - timedelta(days=failed_days_ago, hours=1))
    async with deps.db.transaction() as s:
        w = await s.get_one(BidResultWatch, bid_id)
        w.stage, w.final_kind = "final", "failed"
        w.final_at = NOW - timedelta(days=failed_days_ago)
    return bid_id


async def test_renotice_found_in_db(deps, fake_g2b):
    """유찰 뒤 같은 기관·사업명 재공고가 수집되면 Change(renotice) 한 번. G2B는 안 부른다."""
    bid_id = await _failed_watch(deps, 2)
    (other_org, renotice) = await seed(
        deps,
        "regular",
        _regular("R26BK91000010", NOW + timedelta(days=7), org="조달청", renotice="Y", notice=NOW),
        _regular(
            "R26BK91000011",
            NOW + timedelta(days=7),
            title=f"(재공고) {TITLE}",
            renotice="Y",
            notice=NOW - timedelta(days=1),
        ),
    )
    assert await check_due(deps, NOW) == [Change(bid_id, "renotice")]
    w = await _w(deps, bid_id)
    assert (w.renotice_bid_id, w.renotice_at) == (renotice, NOW)
    assert other_org != renotice
    assert await check_due(deps, NOW + timedelta(minutes=5)) == []  # 한 번만
    assert fake_g2b.calls == 0


async def test_renotice_window_30_days(deps, fake_g2b):
    await _failed_watch(deps, 31)
    await seed(
        deps,
        "regular",
        _regular("R26BK91000012", NOW + timedelta(days=7), renotice="Y", notice=NOW),
    )
    assert await check_due(deps, NOW) == []


async def test_budget_exhausted_stops_cleanly(deps, fake_g2b, db):
    """결과 감시 몫이 바닥나면 거기서 멈추고, 남은 공고의 다음 확인 시각은 그대로(Review 5)."""
    first = await _watched(deps, "R26BK91000004", opening=NOW - timedelta(hours=2))
    second = await _watched(deps, "R26BK91000005")
    before = (await _w(deps, second)).next_check_at
    g2b = G2BClient(
        fake_g2b.http_client(),
        TEST_KEYS,
        retry_delays=(0, 0, 0),
        source_budgets={RESULT_WATCH_SOURCE: DbCallBudget(db, 1, sources=[RESULT_WATCH_SOURCE])},
    )
    assert await check_due(dataclasses.replace(deps, g2b=g2b), NOW) == []
    assert (await _w(deps, first)).checks == 1
    assert (await _w(deps, second)).next_check_at == before
    await g2b.http.aclose()


def test_same_title_ignores_spacing_and_renotice_marks():
    assert same_title("(재공고) 데이터 정비 용역", "데이터정비 용역")
    assert same_title("[재공고]데이터 정비 용역", "데이터 정비 용역")
    assert not same_title("데이터 정비 용역(2차)", "데이터 정비 용역")
