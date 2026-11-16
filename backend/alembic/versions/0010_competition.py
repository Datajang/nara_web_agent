"""경쟁 구도·AI 해설·공동수급 (SPEC §15.4·§15.8, P11)

- bid_participant_fetches: 개찰완료 목록(OpengCompt)을 이미 불러온 공고(차수). 결과가 0행이어도
  다시 부르지 않게 표시한다(온디맨드 캐시, 한 요청 6건 상한)
- bid_joint_members(member_bizno) 색인: 공동수급 파트너 조회
- usage_logs.event에 'competition'(온디맨드 G2B 호출), 'compare_explain'(AI 해설)을 더한다

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-16
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD = "event IN ('search','recommend','analyze','assistant_turn','collector','company_search')"
NEW = (
    "event IN ('search','recommend','analyze','assistant_turn','collector','company_search',"
    "'competition','compare_explain')"
)


def upgrade() -> None:
    op.create_table(
        "bid_participant_fetches",
        sa.Column("bid_ntce_no", sa.Text(), nullable=False),
        sa.Column("bid_ntce_ord", sa.Text(), nullable=False),
        sa.Column("row_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "fetched_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint(
            "bid_ntce_no", "bid_ntce_ord", name=op.f("pk_bid_participant_fetches")
        ),
    )
    op.create_index(
        op.f("ix_bid_joint_members_member_bizno"), "bid_joint_members", ["member_bizno"]
    )
    op.create_index(
        op.f("ix_bid_participants_notice"),
        "bid_participants",
        ["bid_ntce_no", "bid_ntce_ord"],
    )
    op.drop_constraint(op.f("ck_usage_logs_event"), "usage_logs", type_="check")
    op.create_check_constraint(op.f("ck_usage_logs_event"), "usage_logs", NEW)


def downgrade() -> None:
    op.execute("DELETE FROM usage_logs WHERE event IN ('competition','compare_explain')")
    op.drop_constraint(op.f("ck_usage_logs_event"), "usage_logs", type_="check")
    op.create_check_constraint(op.f("ck_usage_logs_event"), "usage_logs", OLD)
    op.drop_index(op.f("ix_bid_participants_notice"), table_name="bid_participants")
    op.drop_index(op.f("ix_bid_joint_members_member_bizno"), table_name="bid_joint_members")
    op.drop_table("bid_participant_fetches")
