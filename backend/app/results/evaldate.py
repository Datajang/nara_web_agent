"""협상 공고 제안서평가 일시 맞추기 (2026-11-27, docs/decisions/2026-11-27-proposal-eval-date.md).

결과 메일 타이머가 감시 맞추기 뒤·확인 전에 부른다.
알림 켠 북마크가 있는 협상 공고의 결과 대기 감시만
나라장터 웹(공고 상세)에서 평가 일시를 읽어 `eval_at`에 두고 다음 확인 시각을 다시 정한다.
- 처음 한 번, 그 뒤 결과가 나올 때까지 하루 한 번(정정·연기 반영). 실패하면 1시간 뒤 다시
- 1초에 1건, 한 실행 최대 20건·40초. 웹 호출은 G2B Open API 몫에 세지 않는다
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timedelta

from sqlalchemy import exists, or_, select

from app.db.models import Bid, BidResultWatch, Bookmark
from app.deps import Deps
from app.results.watch import NEGOTIATED, plan_next

log = logging.getLogger(__name__)

LIMIT = 20
REFRESH = timedelta(hours=24)
RETRY = timedelta(hours=1)
DEADLINE_S = 40.0


async def _targets(deps: Deps, now: datetime, limit: int) -> list[tuple[BidResultWatch, Bid]]:
    async with deps.db.session() as s:
        rows = await s.execute(
            select(BidResultWatch, Bid)
            .join(Bid, Bid.id == BidResultWatch.bid_id)
            .where(
                BidResultWatch.stage == "waiting",
                Bid.raw["sucsfbidMthdNm"].astext.contains(NEGOTIATED),
                or_(
                    BidResultWatch.eval_checked_at.is_(None),
                    BidResultWatch.eval_checked_at <= now - REFRESH,
                ),
                exists().where(Bookmark.bid_id == Bid.id, Bookmark.notify_result.is_(True)),
            )
            .order_by(
                BidResultWatch.eval_checked_at.asc().nulls_first(),
                BidResultWatch.opening_at.desc(),
            )
            .limit(limit)
        )
        return [(w, b) for w, b in rows.all()]


async def sync_eval_dates(
    deps: Deps,
    now: datetime,
    *,
    limit: int = LIMIT,
    pause: float = 1.0,
    deadline_s: float = DEADLINE_S,
) -> int:
    """평가 일시를 읽어 갱신한 감시 수. 웹 클라이언트가 없으면 아무것도 하지 않는다."""
    web = deps.g2b_web
    if web is None:
        return 0
    updated = 0
    stop_at = time.monotonic() + deadline_s
    for i, (w, bid) in enumerate(await _targets(deps, now, limit)):
        if time.monotonic() >= stop_at:
            log.warning("협상 공고 평가 일시: 시간 상한, 남은 공고는 다음 실행에서")
            break
        if i and pause:
            await asyncio.sleep(pause)
        try:
            plan = await web.eval_date(bid.bid_no, w.notice_ord)
        except Exception as e:  # noqa: BLE001 — 웹 화면 주소가 바뀌어도 결과 메일은 돈다(30분 간격)
            log.warning("협상 공고 평가 일시 읽기 실패 %s: %s %s", bid.bid_no, type(e).__name__, e)
            async with deps.db.transaction() as s:
                row = await s.get_one(BidResultWatch, w.bid_id)
                row.eval_checked_at = now - REFRESH + RETRY
            continue
        async with deps.db.transaction() as s:
            row = await s.get_one(BidResultWatch, w.bid_id)
            if row.stage != "waiting" or row.notice_ord != w.notice_ord:
                continue  # 그사이 결과가 나왔거나 정정됨
            row.eval_at, row.eval_checked_at, row.updated_at = plan.at, now, now
            nc = plan_next(row, bid, now)
            if nc is not None:
                row.next_check_at = nc
        updated += 1
    return updated
