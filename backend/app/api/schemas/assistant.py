"""어시스턴트 대화 (SPEC §6.2, §8.6)."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, StringConstraints

from app.bids.cards import BidCard

Title = Annotated[str, StringConstraints(strip_whitespace=True, max_length=100)]


class ConversationIn(BaseModel):
    title: Title = ""
    profile_id: int | None = None


class ConversationPatch(BaseModel):
    """주지 않은 필드는 그대로. profile_id: null이면 프로필 연결 해제 (§7.6)."""

    title: Title | None = None
    profile_id: int | None = None


class ConversationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    profile_id: int | None
    created_at: datetime
    updated_at: datetime


class ConversationList(BaseModel):
    items: list[ConversationOut]


class MessageIn(BaseModel):
    content: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]


class MessageOut(BaseModel):
    id: int
    role: Literal["user", "assistant"]
    content: str
    cards: list[BidCard]
    created_at: datetime


class MessageList(BaseModel):
    items: list[MessageOut]
