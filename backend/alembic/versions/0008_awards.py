"""낙찰·경쟁사 분석 테이블 (SPEC §15.3, P8)

- 공유: companies(bizno PK), bid_awards(공고·차수·분류·재입찰 고유),
  bid_participants, bid_joint_members
- 설정: org_settings(한 행, id=1), watched_companies
고유키·컬럼은 probe 결과를 따른다(docs/decisions/2026-11-16-awards-probe.md).
개인정보·raw 컬럼 없음.
새 테이블만 만들어 이전 코드와 호환된다(§11.5).

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "bid_joint_members",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("bid_ntce_no", sa.Text(), nullable=False),
        sa.Column("bid_ntce_ord", sa.Text(), nullable=False),
        sa.Column("bizno", sa.Text(), nullable=True),
        sa.Column("member_bizno", sa.Text(), nullable=False),
        sa.Column("member_name", sa.Text(), nullable=True),
        sa.Column("role", sa.Text(), nullable=True),
        sa.Column("joint_mode", sa.Text(), nullable=True),
        sa.Column("share", sa.Numeric(precision=6, scale=2), nullable=True),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_bid_joint_members")),
        sa.UniqueConstraint(
            "bid_ntce_no",
            "bid_ntce_ord",
            "member_bizno",
            name=op.f("uq_bid_joint_members_bid_ntce_no_bid_ntce_ord_member_bizno"),
        ),
    )
    op.create_table(
        "bid_participants",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("bid_ntce_no", sa.Text(), nullable=False),
        sa.Column("bid_ntce_ord", sa.Text(), nullable=False),
        sa.Column("bid_clsfc_no", sa.Text(), nullable=False),
        sa.Column("rbid_no", sa.Text(), nullable=False),
        sa.Column("bizno", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=True),
        sa.Column("rank", sa.Integer(), nullable=True),
        sa.Column("bid_amount", sa.BigInteger(), nullable=True),
        sa.Column("bid_rate", sa.Numeric(precision=9, scale=3), nullable=True),
        sa.Column("tech_score", sa.Numeric(precision=9, scale=4), nullable=True),
        sa.Column("price_score", sa.Numeric(precision=9, scale=4), nullable=True),
        sa.Column("total_score", sa.Numeric(precision=9, scale=4), nullable=True),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_bid_participants")),
        sa.UniqueConstraint(
            "bid_ntce_no",
            "bid_ntce_ord",
            "bid_clsfc_no",
            "rbid_no",
            "bizno",
            name=op.f("uq_bid_participants_bid_ntce_no_bid_ntce_ord_bid_clsfc_no_rbid_no_bizno"),
        ),
    )
    op.create_index("ix_bid_participants_bizno", "bid_participants", ["bizno"], unique=False)
    op.create_table(
        "companies",
        sa.Column("bizno", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("name_norm", sa.Text(), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("bizno ~ '^[0-9]{10}$'", name=op.f("ck_companies_bizno")),
        sa.PrimaryKeyConstraint("bizno", name=op.f("pk_companies")),
    )
    op.create_index(
        "ix_companies_name_norm_trgm",
        "companies",
        ["name_norm"],
        unique=False,
        postgresql_using="gin",
        postgresql_ops={"name_norm": "gin_trgm_ops"},
    )
    op.create_table(
        "bid_awards",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("bid_ntce_no", sa.Text(), nullable=False),
        sa.Column("bid_ntce_ord", sa.Text(), nullable=False),
        sa.Column("bid_clsfc_no", sa.Text(), nullable=False),
        sa.Column("rbid_no", sa.Text(), nullable=False),
        sa.Column("bizno", sa.Text(), nullable=True),
        sa.Column("winner_name", sa.Text(), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("award_amount", sa.BigInteger(), nullable=True),
        sa.Column("g2b_award_rate", sa.Numeric(precision=9, scale=3), nullable=True),
        sa.Column("estimated_price", sa.BigInteger(), nullable=True),
        sa.Column("award_ratio", sa.Numeric(precision=9, scale=5), nullable=True),
        sa.Column("participant_count", sa.Integer(), nullable=True),
        sa.Column("dminstt_cd", sa.Text(), nullable=True),
        sa.Column("dminstt_name", sa.Text(), nullable=True),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("awarded_on", sa.Date(), nullable=True),
        sa.Column("registered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_joint", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "fields", sa.ARRAY(sa.Text()), server_default=sa.text("'{}'::text[]"), nullable=False
        ),
        sa.Column(
            "fetched_at",
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
        sa.ForeignKeyConstraint(
            ["bizno"], ["companies.bizno"], name=op.f("fk_bid_awards_bizno_companies")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_bid_awards")),
        sa.UniqueConstraint(
            "bid_ntce_no",
            "bid_ntce_ord",
            "bid_clsfc_no",
            "rbid_no",
            name=op.f("uq_bid_awards_bid_ntce_no_bid_ntce_ord_bid_clsfc_no_rbid_no"),
        ),
    )
    op.create_index(
        "ix_bid_awards_bizno_registered_at", "bid_awards", ["bizno", "registered_at"], unique=False
    )
    op.create_index("ix_bid_awards_dminstt_cd", "bid_awards", ["dminstt_cd"], unique=False)
    op.create_index(
        "ix_bid_awards_fields", "bid_awards", ["fields"], unique=False, postgresql_using="gin"
    )
    op.create_index("ix_bid_awards_registered_at", "bid_awards", ["registered_at"], unique=False)
    op.create_table(
        "org_settings",
        sa.Column("id", sa.SmallInteger(), server_default="1", nullable=False),
        sa.Column("our_bizno", sa.Text(), nullable=True),
        sa.Column("our_name", sa.Text(), nullable=True),
        sa.Column(
            "field_keywords",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("backfill_years", sa.SmallInteger(), server_default="5", nullable=False),
        sa.Column("updated_by", sa.BigInteger(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "our_bizno IS NULL OR our_bizno ~ '^[0-9]{10}$'", name=op.f("ck_org_settings_our_bizno")
        ),
        sa.CheckConstraint(
            "backfill_years BETWEEN 1 AND 10", name=op.f("ck_org_settings_backfill_years")
        ),
        sa.CheckConstraint("id = 1", name=op.f("ck_org_settings_single_row")),
        sa.ForeignKeyConstraint(
            ["updated_by"],
            ["users.id"],
            name=op.f("fk_org_settings_updated_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_org_settings")),
    )
    op.create_table(
        "watched_companies",
        sa.Column("bizno", sa.Text(), nullable=False),
        sa.Column("added_by", sa.BigInteger(), nullable=True),
        sa.Column(
            "added_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["added_by"],
            ["users.id"],
            name=op.f("fk_watched_companies_added_by_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["bizno"],
            ["companies.bizno"],
            name=op.f("fk_watched_companies_bizno_companies"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("bizno", name=op.f("pk_watched_companies")),
    )


def downgrade() -> None:
    op.drop_table("watched_companies")
    op.drop_table("org_settings")
    op.drop_index("ix_bid_awards_registered_at", table_name="bid_awards")
    op.drop_index("ix_bid_awards_fields", table_name="bid_awards", postgresql_using="gin")
    op.drop_index("ix_bid_awards_dminstt_cd", table_name="bid_awards")
    op.drop_index("ix_bid_awards_bizno_registered_at", table_name="bid_awards")
    op.drop_table("bid_awards")
    op.drop_index(
        "ix_companies_name_norm_trgm",
        table_name="companies",
        postgresql_using="gin",
        postgresql_ops={"name_norm": "gin_trgm_ops"},
    )
    op.drop_table("companies")
    op.drop_index("ix_bid_participants_bizno", table_name="bid_participants")
    op.drop_table("bid_participants")
    op.drop_table("bid_joint_members")
