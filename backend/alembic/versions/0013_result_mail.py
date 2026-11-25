"""북마크 공고 결과 메일 (2026-11-25, docs/superpowers/specs/2026-11-25-bid-result-mail-design.md)

- bookmarks.notify_result, users.result_mail: 기본 켬(기존 행도 켬)
- bid_result_watch: 공고별 결과 감시 상태(5분 타이머)
- bid_result_mails: 결과 메일 발송 대기열(사람·공고·단계마다 한 줄, pending → sent/failed/cancelled)
- 컬럼·테이블 추가만이라 이전 코드와 호환된다(§11.5)

Revision ID: 0013
Revises: 0012
Create Date: 2026-11-25
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TS = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.add_column(
        "bookmarks",
        sa.Column("notify_result", sa.Boolean(), server_default="true", nullable=False),
    )
    op.add_column(
        "users", sa.Column("result_mail", sa.Boolean(), server_default="true", nullable=False)
    )
    op.create_table(
        "bid_result_watch",
        sa.Column("bid_id", sa.BigInteger(), nullable=False),
        sa.Column("stage", sa.Text(), server_default="waiting", nullable=False),
        sa.Column("notice_ord", sa.Text(), nullable=False),
        sa.Column("opening_at", TS, nullable=False),
        sa.Column("next_check_at", TS, nullable=False),
        sa.Column("opened_at", TS, nullable=True),
        sa.Column("final_kind", sa.Text(), nullable=True),
        sa.Column("final_at", TS, nullable=True),
        sa.Column("renotice_bid_id", sa.BigInteger(), nullable=True),
        sa.Column("renotice_at", TS, nullable=True),
        sa.Column("checks", sa.Integer(), server_default="0", nullable=False),
        sa.Column("updated_at", TS, server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "stage IN ('waiting','opened','final','expired')",
            name=op.f("ck_bid_result_watch_stage"),
        ),
        sa.CheckConstraint(
            "final_kind IS NULL OR final_kind IN ('awarded','failed')",
            name=op.f("ck_bid_result_watch_final_kind"),
        ),
        sa.ForeignKeyConstraint(
            ["bid_id"],
            ["bids.id"],
            name=op.f("fk_bid_result_watch_bid_id_bids"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["renotice_bid_id"],
            ["bids.id"],
            name=op.f("fk_bid_result_watch_renotice_bid_id_bids"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("bid_id", name=op.f("pk_bid_result_watch")),
    )
    op.create_index(
        "ix_bid_result_watch_due",
        "bid_result_watch",
        ["next_check_at"],
        postgresql_where=sa.text("stage IN ('waiting','opened')"),
    )
    op.create_table(
        "bid_result_mails",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("bid_id", sa.BigInteger(), nullable=False),
        sa.Column("stage", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), server_default="pending", nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", TS, server_default=sa.text("now()"), nullable=False),
        sa.Column("sent_at", TS, nullable=True),
        sa.CheckConstraint(
            "stage IN ('opened','final','renotice')", name=op.f("ck_bid_result_mails_stage")
        ),
        sa.CheckConstraint(
            "status IN ('pending','sent','failed','cancelled')",
            name=op.f("ck_bid_result_mails_status"),
        ),
        sa.ForeignKeyConstraint(
            ["bid_id"],
            ["bids.id"],
            name=op.f("fk_bid_result_mails_bid_id_bids"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_bid_result_mails_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_bid_result_mails")),
        sa.UniqueConstraint(
            "user_id", "bid_id", "stage", name=op.f("uq_bid_result_mails_user_id_bid_id_stage")
        ),
    )

    op.create_index(
        "ix_bid_result_mails_pending",
        "bid_result_mails",
        ["id"],
        postgresql_where=sa.text("status = 'pending'"),
    )


def downgrade() -> None:
    op.drop_index("ix_bid_result_mails_pending", table_name="bid_result_mails")
    op.drop_table("bid_result_mails")
    op.drop_index("ix_bid_result_watch_due", table_name="bid_result_watch")
    op.drop_table("bid_result_watch")
    op.drop_column("users", "result_mail")
    op.drop_column("bookmarks", "notify_result")
