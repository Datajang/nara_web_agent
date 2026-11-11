"""대화 리포지토리 (SPEC §6.1). user_id 조건 강제, 남의 대화는 404."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Conversation, Message, Profile
from app.history.repo import not_found


async def _own_profile(s: AsyncSession, user_id: int, profile_id: int | None) -> None:
    if profile_id is None:
        return
    found = await s.scalar(
        select(Profile.id).where(Profile.id == profile_id, Profile.user_id == user_id)
    )
    if found is None:
        raise not_found("프로필")


async def list_conversations(s: AsyncSession, user_id: int) -> list[Conversation]:
    rows = await s.execute(
        select(Conversation)
        .where(Conversation.user_id == user_id)
        .order_by(Conversation.updated_at.desc(), Conversation.id.desc())
        .limit(100)
    )
    return list(rows.scalars())


async def create(
    s: AsyncSession, user_id: int, title: str, profile_id: int | None, now: datetime
) -> Conversation:
    await _own_profile(s, user_id, profile_id)
    c = Conversation(
        user_id=user_id, title=title, profile_id=profile_id, created_at=now, updated_at=now
    )
    s.add(c)
    await s.commit()
    await s.refresh(c)
    return c


async def get(s: AsyncSession, user_id: int, conversation_id: int) -> Conversation:
    c = await s.scalar(
        select(Conversation).where(
            Conversation.id == conversation_id, Conversation.user_id == user_id
        )
    )
    if c is None:
        raise not_found("대화")
    return c


async def rename(
    s: AsyncSession, user_id: int, conversation_id: int, title: str, now: datetime
) -> Conversation:
    c = await get(s, user_id, conversation_id)
    c.title = title
    c.updated_at = now
    await s.commit()
    await s.refresh(c)
    return c


async def remove(s: AsyncSession, user_id: int, conversation_id: int) -> None:
    await get(s, user_id, conversation_id)
    await s.execute(
        delete(Conversation).where(
            Conversation.id == conversation_id, Conversation.user_id == user_id
        )
    )
    await s.commit()


async def messages(s: AsyncSession, conversation_id: int, limit: int = 200) -> list[Message]:
    rows = await s.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id, Message.role != "tool")
        .order_by(Message.id.desc())
        .limit(limit)
    )
    return list(reversed(list(rows.scalars())))


async def add_message(
    s: AsyncSession,
    conversation: Conversation,
    role: str,
    content: str,
    parts: dict[str, Any] | None,
    now: datetime,
) -> Message:
    m = Message(
        conversation_id=conversation.id, role=role, content=content, parts=parts, created_at=now
    )
    s.add(m)
    conversation.updated_at = now
    if not conversation.title and role == "user":
        conversation.title = content[:30]
    await s.commit()
    await s.refresh(m)
    return m
