"""결과 메일 받는 사람·발송 (설계 2026-11-25).

받는 조건: 북마크 알림 켬 ∧ 계정 '결과 메일 받기' 켬 ∧ 활성 계정
∧ 그 단계가 북마크 뒤에 감지됨 ∧ 아직 안 보냄.
사람마다 발송에 성공한 뒤 bid_result_mails에 남긴다(UNIQUE로 중복 방지).
실패는 로그만 남기고 다음 사람.
pending: 감지 뒤 7일 안의 단계를 다시 모은다 — 지난 실행에서 SMTP가 실패한 사람에게 다시 보낸다.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from sqlalchemy import exists, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.mail import Mailer
from app.db.models import BidResultMail, BidResultWatch, Bookmark, OrgSettings, User
from app.deps import Deps
from app.results.checker import Change, Stage
from app.results.mail import Kind, load_view, render

log = logging.getLogger(__name__)
RETRY_WINDOW = timedelta(days=7)


def _detected_at(w: BidResultWatch, stage: str) -> datetime | None:
    return {"opened": w.opened_at, "final": w.final_at, "renotice": w.renotice_at}[stage]


async def recipients(s: AsyncSession, change: Change) -> list[User]:
    w = await s.get(BidResultWatch, change.bid_id)
    at = _detected_at(w, change.stage) if w is not None else None
    if at is None:
        return []
    rows = await s.execute(
        select(User)
        .join(Bookmark, Bookmark.user_id == User.id)
        .where(
            Bookmark.bid_id == change.bid_id,
            Bookmark.notify_result.is_(True),
            Bookmark.created_at < at,
            User.result_mail.is_(True),
            User.status == "active",
            ~exists().where(
                BidResultMail.user_id == User.id,
                BidResultMail.bid_id == change.bid_id,
                BidResultMail.stage == change.stage,
            ),
        )
        .order_by(User.id)
    )
    return list(rows.scalars().unique())


async def pending(s: AsyncSession, now: datetime) -> list[Change]:
    """감지 뒤 7일 안의 (공고, 단계). 보낼 사람이 남았는지는 recipients가 가른다."""
    since = now - RETRY_WINDOW
    rows = await s.execute(
        select(BidResultWatch).where(
            or_(
                BidResultWatch.opened_at >= since,
                BidResultWatch.final_at >= since,
                BidResultWatch.renotice_at >= since,
            )
        )
    )
    out: list[Change] = []
    for w in rows.scalars():
        stages: tuple[Stage, ...] = ("opened", "final", "renotice")
        for stage in stages:
            at = _detected_at(w, stage)
            if at is not None and at >= since:
                out.append(Change(w.bid_id, stage))
    return sorted(out, key=lambda c: (c.bid_id, c.stage))


def _kind(w: BidResultWatch, stage: str) -> Kind:
    if stage == "final":
        return "failed" if w.final_kind == "failed" else "awarded"
    return "renotice" if stage == "renotice" else "opened"


async def dispatch(deps: Deps, mailer: Mailer, changes: list[Change]) -> int:
    """보낸 메일 수."""
    sent = 0
    settings = deps.settings
    for change in dict.fromkeys(changes):
        async with deps.db.session() as s:
            users = await recipients(s, change)
            if not users:
                continue
            w = await s.get_one(BidResultWatch, change.bid_id)
            org = await s.get(OrgSettings, 1)
            view = await load_view(
                s, change.bid_id, org.our_bizno if org else None, _kind(w, change.stage)
            )
            targets = [(u.id, u.email) for u in users]
        for uid, email in targets:
            try:
                await mailer.send(render(view, email, settings.app_origin, settings.service_name))
            except Exception as e:  # noqa: BLE001 — 한 사람 실패가 나머지를 막지 않게
                log.warning(
                    "결과 메일 발송 실패 bid=%s stage=%s: %s", change.bid_id, change.stage, e
                )
                continue
            async with deps.db.transaction() as s:
                await s.execute(
                    insert(BidResultMail)
                    .values(user_id=uid, bid_id=change.bid_id, stage=change.stage)
                    .on_conflict_do_nothing()
                )
            sent += 1
    return sent
