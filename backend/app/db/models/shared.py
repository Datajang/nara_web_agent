"""공유 계층 (user_id 없음, 공고 단위). SPEC §4."""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, pk, ts_now


def _now() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Bid(Base):
    __tablename__ = "bids"
    __table_args__ = (
        CheckConstraint("source IN ('regular','prespec')", name="source"),
        Index(
            "ix_bids_title_trgm",
            "title",
            postgresql_using="gin",
            postgresql_ops={"title": "gin_trgm_ops"},
        ),
        Index("ix_bids_source_notice_at", "source", text("notice_at DESC")),
        Index("ix_bids_deadline_at", "deadline_at"),
        Index(
            "ix_bids_prespec_reg_no",
            "prespec_reg_no",
            postgresql_where=text("prespec_reg_no IS NOT NULL"),
        ),
    )

    id: Mapped[int] = pk()
    bid_key: Mapped[str] = mapped_column(Text, unique=True)
    source: Mapped[str] = mapped_column(Text)
    bid_no: Mapped[str] = mapped_column(Text)
    revision: Mapped[int] = mapped_column(Integer, server_default="1")
    prespec_reg_no: Mapped[str | None] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    org_name: Mapped[str | None] = mapped_column(Text)
    budget: Mapped[int | None] = mapped_column(BigInteger)
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notice_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    detail_url: Mapped[str | None] = mapped_column(Text)
    files: Mapped[list[Any]] = mapped_column(server_default=text("'[]'::jsonb"))
    content_hash: Mapped[str] = mapped_column(Text)
    raw: Mapped[dict[str, Any]]
    first_seen_at: Mapped[datetime] = _now()
    last_seen_at: Mapped[datetime] = _now()
    updated_at: Mapped[datetime] = _now()


class BidFile(Base):
    __tablename__ = "bid_files"
    __table_args__ = (
        UniqueConstraint("bid_id", "url_hash"),
        CheckConstraint("kind IN ('rfp','spec','other')", name="kind"),
        CheckConstraint("origin IN ('notice','eorder','prespec')", name="origin"),
        CheckConstraint("status IN ('new','ok','failed','unsupported')", name="status"),
    )

    id: Mapped[int] = pk()
    bid_id: Mapped[int] = mapped_column(ForeignKey("bids.id", ondelete="CASCADE"))
    url: Mapped[str] = mapped_column(Text)
    url_hash: Mapped[str] = mapped_column(Text)
    name: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(Text)
    origin: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, server_default="new")
    error: Mapped[str | None] = mapped_column(Text)
    sha256: Mapped[str | None] = mapped_column(Text)
    size_bytes: Mapped[int | None] = mapped_column(Integer)
    # §5.1 "failed는 24시간 뒤 최대 3회 재시도"를 위해 필요 (§4 표에는 없음, 결정 기록 참고)
    attempts: Mapped[int] = mapped_column(Integer, server_default="0")
    downloaded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class FileText(Base):
    __tablename__ = "file_texts"

    sha256: Mapped[str] = mapped_column(Text, primary_key=True)
    text: Mapped[str] = mapped_column(Text)
    char_count: Mapped[int] = mapped_column(Integer)
    extractor_version: Mapped[str] = mapped_column(Text)
    extracted_at: Mapped[datetime] = _now()


class BidSummary(Base):
    __tablename__ = "bid_summaries"
    __table_args__ = (UniqueConstraint("bid_id", "source_hash", "prompt_version"),)

    id: Mapped[int] = pk()
    bid_id: Mapped[int] = mapped_column(ForeignKey("bids.id", ondelete="CASCADE"))
    source_hash: Mapped[str] = mapped_column(Text)
    prompt_version: Mapped[str] = mapped_column(Text)
    model_id: Mapped[str] = mapped_column(Text)
    summary: Mapped[dict[str, Any]]
    input_tokens: Mapped[int] = mapped_column(Integer, server_default="0")
    output_tokens: Mapped[int] = mapped_column(Integer, server_default="0")
    created_at: Mapped[datetime] = ts_now()


class BidScore(Base):
    __tablename__ = "bid_scores"
    __table_args__ = (UniqueConstraint("bid_id", "profile_hash", "prompt_version"),)

    id: Mapped[int] = pk()
    bid_id: Mapped[int] = mapped_column(ForeignKey("bids.id", ondelete="CASCADE"))
    profile_hash: Mapped[str] = mapped_column(Text)
    prompt_version: Mapped[str] = mapped_column(Text)
    bid_content_hash: Mapped[str] = mapped_column(Text)
    model_id: Mapped[str] = mapped_column(Text)
    score: Mapped[int] = mapped_column(SmallInteger)
    reason: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = ts_now()


class Analysis(Base):
    __tablename__ = "analyses"
    __table_args__ = (UniqueConstraint("bid_id", "summary_id", "profile_hash", "prompt_version"),)

    id: Mapped[int] = pk()
    bid_id: Mapped[int] = mapped_column(ForeignKey("bids.id", ondelete="CASCADE"))
    summary_id: Mapped[int] = mapped_column(ForeignKey("bid_summaries.id", ondelete="CASCADE"))
    profile_hash: Mapped[str] = mapped_column(Text)
    prompt_version: Mapped[str] = mapped_column(Text)
    model_id: Mapped[str] = mapped_column(Text)
    result: Mapped[dict[str, Any]]
    markdown: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = ts_now()


class CollectorRun(Base):
    __tablename__ = "collector_runs"
    __table_args__ = (
        CheckConstraint("mode IN ('backfill','incremental','fill')", name="mode"),
        CheckConstraint("status IN ('running','ok','failed')", name="status"),
    )

    id: Mapped[int] = pk()
    source: Mapped[str] = mapped_column(Text)
    mode: Mapped[str] = mapped_column(Text)
    window_from: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    window_to: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(Text, server_default="running")
    fetched: Mapped[int] = mapped_column(Integer, server_default="0")
    inserted: Mapped[int] = mapped_column(Integer, server_default="0")
    updated: Mapped[int] = mapped_column(Integer, server_default="0")
    g2b_calls: Mapped[int] = mapped_column(Integer, server_default="0")
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = _now()
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CollectorCoverage(Base):
    __tablename__ = "collector_coverage"
    __table_args__ = (CheckConstraint("covered_from <= covered_to", name="range"),)

    source: Mapped[str] = mapped_column(Text, primary_key=True)
    covered_from: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    covered_to: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = _now()
