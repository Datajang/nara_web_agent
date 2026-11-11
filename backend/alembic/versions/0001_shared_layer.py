"""공유 계층 테이블 (SPEC §4): bids, bid_files, file_texts, bid_summaries, bid_scores,
analyses, collector_runs, collector_coverage

Revision ID: 0001
Revises:
Create Date: 2026-11-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute("CREATE EXTENSION IF NOT EXISTS citext")
    op.create_table(
        "bids",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("bid_key", sa.Text(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("bid_no", sa.Text(), nullable=False),
        sa.Column("revision", sa.Integer(), server_default="1", nullable=False),
        sa.Column("prespec_reg_no", sa.Text(), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("org_name", sa.Text(), nullable=True),
        sa.Column("budget", sa.BigInteger(), nullable=True),
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notice_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("detail_url", sa.Text(), nullable=True),
        sa.Column(
            "files",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("content_hash", sa.Text(), nullable=False),
        sa.Column("raw", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("source IN ('regular','prespec')", name=op.f("ck_bids_source")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_bids")),
        sa.UniqueConstraint("bid_key", name=op.f("uq_bids_bid_key")),
    )
    op.create_index("ix_bids_deadline_at", "bids", ["deadline_at"], unique=False)
    op.create_index(
        "ix_bids_prespec_reg_no",
        "bids",
        ["prespec_reg_no"],
        unique=False,
        postgresql_where=sa.text("prespec_reg_no IS NOT NULL"),
    )
    op.create_index(
        "ix_bids_source_notice_at",
        "bids",
        ["source", sa.literal_column("notice_at DESC")],
        unique=False,
    )
    op.create_index(
        "ix_bids_title_trgm",
        "bids",
        ["title"],
        unique=False,
        postgresql_using="gin",
        postgresql_ops={"title": "gin_trgm_ops"},
    )
    op.create_table(
        "collector_coverage",
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("covered_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("covered_to", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("covered_from <= covered_to", name=op.f("ck_collector_coverage_range")),
        sa.PrimaryKeyConstraint("source", name=op.f("pk_collector_coverage")),
    )
    op.create_table(
        "collector_runs",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("mode", sa.Text(), nullable=False),
        sa.Column("window_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_to", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.Text(), server_default="running", nullable=False),
        sa.Column("fetched", sa.Integer(), server_default="0", nullable=False),
        sa.Column("inserted", sa.Integer(), server_default="0", nullable=False),
        sa.Column("updated", sa.Integer(), server_default="0", nullable=False),
        sa.Column("g2b_calls", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "mode IN ('backfill','incremental','fill')", name=op.f("ck_collector_runs_mode")
        ),
        sa.CheckConstraint(
            "status IN ('running','ok','failed')", name=op.f("ck_collector_runs_status")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_collector_runs")),
    )
    op.create_table(
        "file_texts",
        sa.Column("sha256", sa.Text(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("char_count", sa.Integer(), nullable=False),
        sa.Column("extractor_version", sa.Text(), nullable=False),
        sa.Column(
            "extracted_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("sha256", name=op.f("pk_file_texts")),
    )
    op.create_table(
        "bid_files",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("bid_id", sa.BigInteger(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("url_hash", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("origin", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), server_default="new", nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("sha256", sa.Text(), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=True),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("downloaded_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("kind IN ('rfp','spec','other')", name=op.f("ck_bid_files_kind")),
        sa.CheckConstraint(
            "origin IN ('notice','eorder','prespec')", name=op.f("ck_bid_files_origin")
        ),
        sa.CheckConstraint(
            "status IN ('new','ok','failed','unsupported')", name=op.f("ck_bid_files_status")
        ),
        sa.ForeignKeyConstraint(
            ["bid_id"], ["bids.id"], name=op.f("fk_bid_files_bid_id_bids"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_bid_files")),
        sa.UniqueConstraint("bid_id", "url_hash", name=op.f("uq_bid_files_bid_id_url_hash")),
    )
    op.create_table(
        "bid_scores",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("bid_id", sa.BigInteger(), nullable=False),
        sa.Column("profile_hash", sa.Text(), nullable=False),
        sa.Column("prompt_version", sa.Text(), nullable=False),
        sa.Column("bid_content_hash", sa.Text(), nullable=False),
        sa.Column("model_id", sa.Text(), nullable=False),
        sa.Column("score", sa.SmallInteger(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["bid_id"], ["bids.id"], name=op.f("fk_bid_scores_bid_id_bids"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_bid_scores")),
        sa.UniqueConstraint(
            "bid_id",
            "profile_hash",
            "prompt_version",
            name=op.f("uq_bid_scores_bid_id_profile_hash_prompt_version"),
        ),
    )
    op.create_table(
        "bid_summaries",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("bid_id", sa.BigInteger(), nullable=False),
        sa.Column("source_hash", sa.Text(), nullable=False),
        sa.Column("prompt_version", sa.Text(), nullable=False),
        sa.Column("model_id", sa.Text(), nullable=False),
        sa.Column("summary", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("input_tokens", sa.Integer(), server_default="0", nullable=False),
        sa.Column("output_tokens", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["bid_id"], ["bids.id"], name=op.f("fk_bid_summaries_bid_id_bids"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_bid_summaries")),
        sa.UniqueConstraint(
            "bid_id",
            "source_hash",
            "prompt_version",
            name=op.f("uq_bid_summaries_bid_id_source_hash_prompt_version"),
        ),
    )
    op.create_table(
        "analyses",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("bid_id", sa.BigInteger(), nullable=False),
        sa.Column("summary_id", sa.BigInteger(), nullable=False),
        sa.Column("profile_hash", sa.Text(), nullable=False),
        sa.Column("prompt_version", sa.Text(), nullable=False),
        sa.Column("model_id", sa.Text(), nullable=False),
        sa.Column("result", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("markdown", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["bid_id"], ["bids.id"], name=op.f("fk_analyses_bid_id_bids"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["summary_id"],
            ["bid_summaries.id"],
            name=op.f("fk_analyses_summary_id_bid_summaries"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_analyses")),
        sa.UniqueConstraint(
            "bid_id",
            "summary_id",
            "profile_hash",
            "prompt_version",
            name=op.f("uq_analyses_bid_id_summary_id_profile_hash_prompt_version"),
        ),
    )


def downgrade() -> None:
    op.drop_table("analyses")
    op.drop_table("bid_summaries")
    op.drop_table("bid_scores")
    op.drop_table("bid_files")
    op.drop_table("file_texts")
    op.drop_table("collector_runs")
    op.drop_table("collector_coverage")
    op.drop_table("bids")
