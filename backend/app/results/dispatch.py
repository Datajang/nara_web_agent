"""결과 메일 받는 사람·발송 대기열 (설계 2026-11-25, 최종 검토 수정).

- enqueue: 결과를 감지한 그 실행에서 받을 사람을 정해 bid_result_mails에 pending으로 넣는다.
  받는 조건: 북마크 알림 켬 ∧ 계정 '결과 메일 받기' 켬 ∧ 활성 계정 ∧ 그 단계가 북마크 뒤에 감지됨 ∧
  아직 줄 없음(UNIQUE). 감지 때 꺼 두었던 사람은 나중에 켜도 지난 결과를 받지 않는다
- deliver: pending을 감지 순서(id)대로 보낸다. 보내기 직전에 다시 확인해 꺼졌으면 cancelled.
  실패는 attempts를 올리고 다음 실행에서 다시, MAX_ATTEMPTS번이면 failed(끝없이 재시도하지 않음)
"""

from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy import ColumnElement, exists, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.mail import Mailer
from app.db.models import BidResultMail, BidResultWatch, Bookmark, OrgSettings, User
from app.deps import Deps
from app.results.checker import Change
from app.results.mail import Kind, ResultView, load_view, render

log = logging.getLogger(__name__)
MAX_ATTEMPTS = 5


def _detected_at(w: BidResultWatch, stage: str) -> datetime | None:
    return {"opened": w.opened_at, "final": w.final_at, "renotice": w.renotice_at}[stage]


def _eligible(bid_id: int) -> list[ColumnElement[bool]]:
    """지금 받을 수 있는 사람 조건(북마크 알림·계정 스위치·활성)."""
    return [
        Bookmark.bid_id == bid_id,
        Bookmark.notify_result.is_(True),
        User.result_mail.is_(True),
        User.status == "active",
    ]


async def recipients(s: AsyncSession, change: Change) -> list[User]:
    w = await s.get(BidResultWatch, change.bid_id)
    at = _detected_at(w, change.stage) if w is not None else None
    if at is None:
        return []
    rows = await s.execute(
        select(User)
        .join(Bookmark, Bookmark.user_id == User.id)
        .where(
            *_eligible(change.bid_id),
            Bookmark.created_at < at,
            ~exists().where(
                BidResultMail.user_id == User.id,
                BidResultMail.bid_id == change.bid_id,
                BidResultMail.stage == change.stage,
            ),
        )
        .order_by(User.id)
    )
    return list(rows.scalars().unique())


async def enqueue(s: AsyncSession, changes: list[Change]) -> int:
    """감지한 단계마다 받을 사람을 대기열에 넣는다. 넣은 줄 수."""
    n = 0
    for change in dict.fromkeys(changes):
        for u in await recipients(s, change):
            res = await s.execute(
                insert(BidResultMail)
                .values(user_id=u.id, bid_id=change.bid_id, stage=change.stage)
                .on_conflict_do_nothing()
            )
            n += res.rowcount or 0  # type: ignore[attr-defined]
    return n


def _kind(w: BidResultWatch, stage: str) -> Kind:
    if stage == "final":
        return "failed" if w.final_kind == "failed" else "awarded"
    return "renotice" if stage == "renotice" else "opened"


async def deliver(deps: Deps, mailer: Mailer, limit: int = 500) -> int:
    """대기열을 감지 순서대로 보낸다. 보낸 메일 수."""
    settings = deps.settings
    async with deps.db.session() as s:
        queue = list(
            (
                await s.execute(
                    select(BidResultMail, User.email)
                    .join(User, User.id == BidResultMail.user_id)
                    .where(BidResultMail.status == "pending")
                    .order_by(BidResultMail.id)
                    .limit(limit)
                )
            ).all()
        )
        org = await s.get(OrgSettings, 1)
        our_bizno = org.our_bizno if org else None
    views: dict[tuple[int, str], ResultView] = {}
    sent = 0
    for row, email in queue:
        async with deps.db.transaction() as s:
            ok = await s.scalar(
                select(func.count())
                .select_from(Bookmark)
                .join(User, User.id == Bookmark.user_id)
                .where(*_eligible(row.bid_id), Bookmark.user_id == row.user_id)
            )
            if not ok:
                (await s.get_one(BidResultMail, row.id)).status = "cancelled"
                continue
            key = (row.bid_id, row.stage)
            if key not in views:
                w = await s.get_one(BidResultWatch, row.bid_id)
                views[key] = await load_view(s, row.bid_id, our_bizno, _kind(w, row.stage))
        try:
            await mailer.send(render(views[key], email, settings.app_origin, settings.service_name))
        except Exception as e:  # noqa: BLE001 — 한 사람 실패가 나머지를 막지 않게
            async with deps.db.transaction() as s:
                r = await s.get_one(BidResultMail, row.id)
                r.attempts += 1
                if r.attempts >= MAX_ATTEMPTS:
                    r.status = "failed"
            log.warning(
                "결과 메일 발송 실패 bid=%s stage=%s 시도 %d: %s",
                row.bid_id,
                row.stage,
                row.attempts + 1,
                type(e).__name__,
            )
            continue
        async with deps.db.transaction() as s:
            r = await s.get_one(BidResultMail, row.id)
            r.status, r.attempts, r.sent_at = "sent", r.attempts + 1, deps.clock()
        sent += 1
    return sent
