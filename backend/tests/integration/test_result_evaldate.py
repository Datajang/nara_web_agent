"""협상 공고 제안서평가 일시 맞추기 (2026-11-27, docs/decisions/2026-11-27-proposal-eval-date.md).

웹은 가짜(FakeG2BWeb). 협상 공고의 결과 대기 감시만 부르고, 평가 전에는 G2B를 부르지 않는다.
"""

from __future__ import annotations

import dataclasses
from datetime import timedelta

from sqlalchemy import insert, update

from app.db.models import Bid, BidResultWatch, Bookmark
from app.g2b.web import EvalPlan, G2BWebError
from app.results.checker import check_due
from app.results.evaldate import sync_eval_dates
from app.results.watch import ensure_watch, sync_watches
from tests.conftest import NOW
from tests.fakes.g2b import kst_str, regular_item
from tests.fakes.g2b_web import FakeG2BWeb
from tests.helpers import create_user, seed

NEGO = "협상에의한계약-협상에 의한 낙찰자 결정(SW사업)"


async def _bookmarked(deps, no: str, *, method: str = NEGO, notify: bool = True) -> int:
    it = regular_item(no, NOW - timedelta(days=10))
    it.update(opengDt=kst_str(NOW - timedelta(days=1)), sucsfbidMthdNm=method)
    (bid_id,) = await seed(deps, "regular", it)
    uid = await create_user(deps.db, f"{no.lower()}@corp.example")
    async with deps.db.transaction() as s:
        await s.execute(insert(Bookmark).values(user_id=uid, bid_id=bid_id, notify_result=notify))
        await sync_watches(s, NOW)
    return bid_id


async def _w(deps, bid_id: int) -> BidResultWatch:
    async with deps.db.session() as s:
        return await s.get_one(BidResultWatch, bid_id)


def _with_web(deps):
    web = FakeG2BWeb()
    return dataclasses.replace(deps, g2b_web=web), web


async def test_eval_date_sets_next_check(deps):
    deps, web = _with_web(deps)
    nego = await _bookmarked(deps, "R26BK92000001")
    await _bookmarked(deps, "R26BK92000002", method="적격심사-추정가격 고시금액 미만")
    web.plans["R26BK92000001"] = EvalPlan(at=NOW + timedelta(days=5), host="조달청")
    assert await sync_eval_dates(deps, NOW, pause=0) == 1
    assert web.calls == [("R26BK92000001", "000")]  # 협상 공고만
    w = await _w(deps, nego)
    assert (w.eval_at, w.eval_checked_at) == (NOW + timedelta(days=5), NOW)
    assert w.next_check_at == NOW + timedelta(days=5)


async def test_no_eval_date_checks_every_30_minutes(deps):
    deps, web = _with_web(deps)
    bid_id = await _bookmarked(deps, "R26BK92000003")
    web.plans["R26BK92000003"] = EvalPlan(at=None, host="수요기관")
    await sync_eval_dates(deps, NOW, pause=0)
    w = await _w(deps, bid_id)
    assert (w.eval_at, w.eval_checked_at) == (None, NOW)
    assert w.next_check_at == NOW + timedelta(minutes=30)


async def test_refreshes_once_a_day(deps):
    """정정으로 평가 일시가 바뀌어도 하루 안에 따라간다."""
    deps, web = _with_web(deps)
    bid_id = await _bookmarked(deps, "R26BK92000004")
    web.plans["R26BK92000004"] = EvalPlan(at=NOW + timedelta(days=5), host="조달청")
    await sync_eval_dates(deps, NOW, pause=0)
    assert await sync_eval_dates(deps, NOW + timedelta(hours=23), pause=0) == 0
    web.plans["R26BK92000004"] = EvalPlan(at=NOW + timedelta(days=6), host="조달청")
    later = NOW + timedelta(hours=24)
    assert await sync_eval_dates(deps, later, pause=0) == 1
    w = await _w(deps, bid_id)
    assert (w.eval_at, w.next_check_at) == (NOW + timedelta(days=6), NOW + timedelta(days=6))
    assert len(web.calls) == 2


async def test_web_error_retries_in_an_hour(deps):
    deps, web = _with_web(deps)
    bid_id = await _bookmarked(deps, "R26BK92000005")
    web.plans["R26BK92000005"] = G2BWebError("시스템 접근 안내")
    assert await sync_eval_dates(deps, NOW, pause=0) == 0
    w = await _w(deps, bid_id)
    assert w.eval_at is None
    assert await sync_eval_dates(deps, NOW + timedelta(minutes=30), pause=0) == 0
    assert len(web.calls) == 1
    web.plans["R26BK92000005"] = EvalPlan(at=NOW + timedelta(days=2), host="조달청")
    assert await sync_eval_dates(deps, NOW + timedelta(hours=1), pause=0) == 1


async def test_notify_off_or_opened_not_called(deps):
    deps, web = _with_web(deps)
    await _bookmarked(deps, "R26BK92000006", notify=False)
    opened = await _bookmarked(deps, "R26BK92000007")
    async with deps.db.transaction() as s:
        await s.execute(
            update(BidResultWatch).where(BidResultWatch.bid_id == opened).values(stage="opened")
        )
    assert await sync_eval_dates(deps, NOW, pause=0) == 0
    assert web.calls == []


async def test_no_g2b_call_before_evaluation(deps, fake_g2b):
    deps, web = _with_web(deps)
    bid_id = await _bookmarked(deps, "R26BK92000008")
    web.plans["R26BK92000008"] = EvalPlan(at=NOW + timedelta(days=2), host="조달청")
    await sync_eval_dates(deps, NOW, pause=0)
    assert await check_due(deps, NOW + timedelta(days=1)) == []
    assert fake_g2b.calls == 0
    at = NOW + timedelta(days=2)
    assert await check_due(deps, at) == []  # 평가 시작: 확인, 결과는 아직
    assert fake_g2b.calls == 1
    assert (await _w(deps, bid_id)).next_check_at == at + timedelta(minutes=5)


async def test_notice_correction_clears_eval_date(deps):
    deps, web = _with_web(deps)
    bid_id = await _bookmarked(deps, "R26BK92000009")
    web.plans["R26BK92000009"] = EvalPlan(at=NOW + timedelta(days=2), host="조달청")
    await sync_eval_dates(deps, NOW, pause=0)
    async with deps.db.transaction() as s:
        bid = await s.get_one(Bid, bid_id)
        bid.raw = {**bid.raw, "bidNtceOrd": "001"}
        await ensure_watch(s, bid, NOW)
    w = await _w(deps, bid_id)
    assert (w.notice_ord, w.eval_at, w.eval_checked_at) == ("001", None, None)


async def test_without_web_client_is_noop(deps):
    await _bookmarked(deps, "R26BK92000010")
    assert await sync_eval_dates(deps, NOW, pause=0) == 0
