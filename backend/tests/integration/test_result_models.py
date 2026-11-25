"""결과 메일 테이블·컬럼 (계획 Task 2, 설계 docs/superpowers/specs/2026-11-25-bid-result-mail-design.md)."""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError


async def _user_bid(s) -> tuple[int, int]:
    uid = (
        await s.execute(
            text("INSERT INTO users (email, password_hash) VALUES ('a@x.kr', 'h') RETURNING id")
        )
    ).scalar_one()
    bid = (
        await s.execute(
            text(
                "INSERT INTO bids (bid_key, source, bid_no, title, content_hash, raw)"
                " VALUES ('regular:R26BK1', 'regular', 'R26BK1', '시험 사업', 'h', '{}')"
                " RETURNING id"
            )
        )
    ).scalar_one()
    return uid, bid


async def test_existing_bookmark_defaults_on(db):
    """컬럼을 모르는 이전 코드가 넣은 북마크·계정도 결과 메일 켬으로 읽힌다(설계: 기존 북마크도 켜짐)."""
    async with db.transaction() as s:
        uid, bid = await _user_bid(s)
        await s.execute(
            text("INSERT INTO bookmarks (user_id, bid_id) VALUES (:u, :b)"), {"u": uid, "b": bid}
        )
    async with db.session() as s:
        on = (await s.execute(text("SELECT notify_result FROM bookmarks"))).scalar_one()
        mail = (await s.execute(text("SELECT result_mail FROM users"))).scalar_one()
    assert on is True
    assert mail is True


async def test_result_mail_unique_per_stage(db):
    """같은 사람·공고·단계 메일 기록은 하나뿐(중복 발송 방지)."""
    async with db.transaction() as s:
        uid, bid = await _user_bid(s)
        q = text("INSERT INTO bid_result_mails (user_id, bid_id, stage) VALUES (:u, :b, :st)")
        await s.execute(q, {"u": uid, "b": bid, "st": "opened"})
        await s.execute(q, {"u": uid, "b": bid, "st": "final"})
    with pytest.raises(IntegrityError):
        async with db.transaction() as s:
            await s.execute(q, {"u": uid, "b": bid, "st": "opened"})


async def test_watch_stage_checked(db):
    """감시 단계·결과 종류는 정해진 값만."""
    async with db.transaction() as s:
        _, bid = await _user_bid(s)
    with pytest.raises(IntegrityError):
        async with db.transaction() as s:
            await s.execute(
                text(
                    "INSERT INTO bid_result_watch (bid_id, stage, notice_ord, opening_at,"
                    " next_check_at) VALUES (:b, 'done', '000', now(), now())"
                ),
                {"b": bid},
            )
