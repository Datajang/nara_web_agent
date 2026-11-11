"""개인 계층 (user_id 있음). SPEC §4. 인증 로직은 P2."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    PrimaryKeyConstraint,
    SmallInteger,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import CITEXT, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, pk, ts_now


def _ts() -> Mapped[datetime | None]:
    return mapped_column(DateTime(timezone=True))


def _user_fk() -> Mapped[int]:
    return mapped_column(ForeignKey("users.id", ondelete="CASCADE"))


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("role IN ('member','admin')", name="role"),
        CheckConstraint(
            "status IN ('pending_verification','pending_approval','active','disabled')",
            name="status",
        ),
    )

    id: Mapped[int] = pk()
    email: Mapped[str] = mapped_column(CITEXT, unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
    display_name: Mapped[str] = mapped_column(Text, server_default="")
    role: Mapped[str] = mapped_column(Text, server_default="member")
    status: Mapped[str] = mapped_column(Text, server_default="pending_verification")
    email_verified_at: Mapped[datetime | None] = _ts()
    failed_login_count: Mapped[int] = mapped_column(Integer, server_default="0")
    locked_until: Mapped[datetime | None] = _ts()
    last_login_at: Mapped[datetime | None] = _ts()
    created_at: Mapped[datetime] = ts_now()


class EmailToken(Base):
    __tablename__ = "email_tokens"
    __table_args__ = (CheckConstraint("purpose IN ('verify','reset')", name="purpose"),)

    id: Mapped[int] = pk()
    user_id: Mapped[int] = _user_fk()
    purpose: Mapped[str] = mapped_column(Text)
    token_hash: Mapped[str] = mapped_column(Text)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = _ts()


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[int] = pk()
    user_id: Mapped[int] = _user_fk()
    token_hash: Mapped[str] = mapped_column(Text, unique=True)
    family_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    rotated_at: Mapped[datetime | None] = _ts()
    revoked_at: Mapped[datetime | None] = _ts()
    created_at: Mapped[datetime] = ts_now()
    user_agent: Mapped[str | None] = mapped_column(Text)


class Profile(Base):
    __tablename__ = "profiles"

    id: Mapped[int] = pk()
    user_id: Mapped[int] = _user_fk()
    name: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text, server_default="")
    keywords: Mapped[list[Any]] = mapped_column(server_default=text("'[]'::jsonb"))
    profile_hash: Mapped[str] = mapped_column(Text)
    is_default: Mapped[bool] = mapped_column(Boolean, server_default="false")
    created_at: Mapped[datetime] = ts_now()
    updated_at: Mapped[datetime] = ts_now()


class SearchRun(Base):
    __tablename__ = "search_runs"
    __table_args__ = (
        CheckConstraint("kind IN ('search','recommend')", name="kind"),
        Index("ix_search_runs_user_created", "user_id", text("created_at DESC")),
    )

    id: Mapped[int] = pk()
    user_id: Mapped[int] = _user_fk()
    profile_id: Mapped[int | None] = mapped_column(ForeignKey("profiles.id", ondelete="SET NULL"))
    kind: Mapped[str] = mapped_column(Text)
    query: Mapped[dict[str, Any]]
    result_count: Mapped[int] = mapped_column(Integer)
    data_as_of: Mapped[datetime | None] = _ts()
    cache_hit: Mapped[bool] = mapped_column(Boolean)
    created_at: Mapped[datetime] = ts_now()


class SearchRunItem(Base):
    __tablename__ = "search_run_items"
    __table_args__ = (PrimaryKeyConstraint("run_id", "bid_id"),)

    run_id: Mapped[int] = mapped_column(ForeignKey("search_runs.id", ondelete="CASCADE"))
    bid_id: Mapped[int] = mapped_column(ForeignKey("bids.id", ondelete="CASCADE"))
    rank: Mapped[int] = mapped_column(Integer)
    score: Mapped[int | None] = mapped_column(SmallInteger)
    reason: Mapped[str | None] = mapped_column(Text)


class UserAnalysis(Base):
    __tablename__ = "user_analyses"
    __table_args__ = (UniqueConstraint("user_id", "analysis_id"),)

    id: Mapped[int] = pk()
    user_id: Mapped[int] = _user_fk()
    analysis_id: Mapped[int] = mapped_column(ForeignKey("analyses.id", ondelete="CASCADE"))
    profile_id: Mapped[int | None] = mapped_column(ForeignKey("profiles.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = ts_now()


class Bookmark(Base):
    __tablename__ = "bookmarks"
    __table_args__ = (
        UniqueConstraint("user_id", "bid_id"),
        Index("ix_bookmarks_user_created", "user_id", text("created_at DESC")),
    )

    id: Mapped[int] = pk()
    user_id: Mapped[int] = _user_fk()
    bid_id: Mapped[int] = mapped_column(ForeignKey("bids.id", ondelete="CASCADE"))
    analysis_id: Mapped[int | None] = mapped_column(ForeignKey("analyses.id", ondelete="SET NULL"))
    note: Mapped[str] = mapped_column(Text, server_default="")
    created_at: Mapped[datetime] = ts_now()


class Conversation(Base):
    __tablename__ = "conversations"
    __table_args__ = (Index("ix_conversations_user_updated", "user_id", text("updated_at DESC")),)

    id: Mapped[int] = pk()
    user_id: Mapped[int] = _user_fk()
    profile_id: Mapped[int | None] = mapped_column(ForeignKey("profiles.id", ondelete="SET NULL"))
    title: Mapped[str] = mapped_column(Text, server_default="")
    created_at: Mapped[datetime] = ts_now()
    updated_at: Mapped[datetime] = ts_now()


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        CheckConstraint("role IN ('user','assistant','tool')", name="role"),
        Index("ix_messages_conversation_id_id", "conversation_id", "id"),
    )

    id: Mapped[int] = pk()
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"))
    role: Mapped[str] = mapped_column(Text)
    content: Mapped[str] = mapped_column(Text)
    parts: Mapped[dict[str, Any] | None]
    created_at: Mapped[datetime] = ts_now()


class UsageLog(Base):
    __tablename__ = "usage_logs"
    __table_args__ = (
        CheckConstraint(
            "event IN ('search','recommend','analyze','assistant_turn','collector')", name="event"
        ),
        Index("ix_usage_logs_created_at", "created_at"),
    )

    id: Mapped[int] = pk()
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    event: Mapped[str] = mapped_column(Text)
    cache: Mapped[dict[str, Any]] = mapped_column(server_default=text("'{}'::jsonb"))
    g2b_calls: Mapped[int] = mapped_column(Integer, server_default="0")
    llm_calls: Mapped[int] = mapped_column(Integer, server_default="0")
    prompt_tokens: Mapped[int] = mapped_column(Integer, server_default="0")
    completion_tokens: Mapped[int] = mapped_column(Integer, server_default="0")
    duration_ms: Mapped[int] = mapped_column(Integer, server_default="0")
    created_at: Mapped[datetime] = ts_now()


class Feedback(Base):
    __tablename__ = "feedback"
    __table_args__ = (
        CheckConstraint(
            "target_type IN ('analysis','assistant_message','search_run')", name="target_type"
        ),
        CheckConstraint("rating IN (-1, 1)", name="rating"),
    )

    id: Mapped[int] = pk()
    user_id: Mapped[int] = _user_fk()
    target_type: Mapped[str] = mapped_column(Text)
    target_id: Mapped[int] = mapped_column(BigInteger)
    rating: Mapped[int] = mapped_column(SmallInteger)
    comment: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
