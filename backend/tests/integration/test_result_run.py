"""타이머 한 번 실행의 순서 (최종 검토 수정).

지난 대기열 발송 → 감시 맞추기 → 확인 → 대기열 → 발송.
"""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import insert

from app.auth.mail import MemoryMailer
from app.db.models import BidResultMail, BidResultWatch, Bookmark
from app.results.__main__ import run_once
from tests.conftest import NOW
from tests.fakes.g2b import kst_str, opening_item, regular_item, status_item
from tests.helpers import create_user, seed


async def test_run_once_detects_and_mails(deps, fake_g2b):
    no = "R26BK94000001"
    it = regular_item(no, NOW - timedelta(days=3))
    it["opengDt"] = kst_str(NOW - timedelta(minutes=30))
    (bid_id,) = await seed(deps, "regular", it)
    uid = await create_user(deps.db, "a@corp.example")
    async with deps.db.transaction() as s:
        await s.execute(
            insert(Bookmark).values(user_id=uid, bid_id=bid_id, created_at=NOW - timedelta(days=1))
        )
    fake_g2b.add("opening_status", status_item(no, "개찰완료"))
    fake_g2b.add("opening_compt", opening_item(no, "1111111111"))
    mailer = MemoryMailer()
    assert await run_once(deps, mailer) == (1, 1, 1)
    assert [m.subject.split("]")[1].strip().split(":")[0] for m in mailer.outbox] == ["개찰 결과"]


async def test_run_once_sends_old_queue_even_if_check_fails(deps, fake_g2b):
    """지난 실행의 대기열은 확인보다 먼저 보낸다(G2B가 느려 확인이 끊겨도 메일은 나간다)."""
    no = "R26BK94000002"
    it = regular_item(no, NOW - timedelta(days=3))
    it["opengDt"] = kst_str(NOW - timedelta(hours=5))
    (bid_id,) = await seed(deps, "regular", it)
    uid = await create_user(deps.db, "b@corp.example")
    async with deps.db.transaction() as s:
        await s.execute(
            insert(Bookmark).values(user_id=uid, bid_id=bid_id, created_at=NOW - timedelta(days=1))
        )
        s.add(
            BidResultWatch(
                bid_id=bid_id,
                stage="final",
                notice_ord="000",
                opening_at=NOW - timedelta(hours=5),
                next_check_at=NOW,
                final_kind="failed",
                final_at=NOW - timedelta(minutes=5),
            )
        )
        await s.flush()
        s.add(BidResultMail(user_id=uid, bid_id=bid_id, stage="final"))
    fake_g2b.fail(*[__import__("httpx").Response(500)] * 20)
    mailer = MemoryMailer()
    await run_once(deps, mailer)
    assert [m.to for m in mailer.outbox] == ["b@corp.example"]
