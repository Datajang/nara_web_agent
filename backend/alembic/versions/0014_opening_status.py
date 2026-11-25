"""마감 공고 사유: 개찰결과 진행 상태 (2026-11-26)

설계 docs/superpowers/specs/2026-11-26-closed-bid-reason-design.md

- bid_opening_status: 공고·차수·분류·재입찰마다 개찰결과 목록의 상태(개찰완료·유찰·재입찰·재시담)
- 테이블 추가만이라 이전 코드와 호환된다(§11.5)

Revision ID: 0014
Revises: 0013
Create Date: 2026-11-26
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TS = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "bid_opening_status",
        sa.Column("bid_ntce_no", sa.Text(), nullable=False),
        sa.Column("bid_ntce_ord", sa.Text(), nullable=False),
        sa.Column("bid_clsfc_no", sa.Text(), nullable=False),
        sa.Column("rbid_no", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("opened_at", TS, nullable=True),
        sa.Column("input_at", TS, nullable=True),
        sa.Column("participant_count", sa.Integer(), nullable=True),
        sa.Column("result_text", sa.Text(), nullable=True),
        sa.Column("top_name", sa.Text(), nullable=True),
        sa.Column("top_bizno", sa.Text(), nullable=True),
        sa.Column("updated_at", TS, server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint(
            "bid_ntce_no",
            "bid_ntce_ord",
            "bid_clsfc_no",
            "rbid_no",
            name=op.f("pk_bid_opening_status"),
        ),
    )


def downgrade() -> None:
    op.drop_table("bid_opening_status")
