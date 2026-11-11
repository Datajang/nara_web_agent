"""피드백에 사유 코드·모델·프롬프트 버전 (P4, SPEC §12.7-1)

파일럿 게이트("👎 사유 상위 3개 조치")에 필요하다. 모두 NULL 허용이라 이전 코드와 호환된다
(§11.5 마이그레이션 호환 규칙). docs/decisions/2026-11-11-p4-ops.md.

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-11
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

REASONS = "('wrong','missing','irrelevant','too_long','other')"


def upgrade() -> None:
    op.add_column("feedback", sa.Column("reason", sa.Text(), nullable=True))
    op.add_column("feedback", sa.Column("model", sa.Text(), nullable=True))
    op.add_column("feedback", sa.Column("prompt_version", sa.Text(), nullable=True))
    op.create_check_constraint(
        op.f("ck_feedback_reason"), "feedback", f"reason IS NULL OR reason IN {REASONS}"
    )
    op.create_check_constraint(
        op.f("ck_feedback_reason_only_down"), "feedback", "reason IS NULL OR rating = -1"
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_feedback_reason_only_down"), "feedback", type_="check")
    op.drop_constraint(op.f("ck_feedback_reason"), "feedback", type_="check")
    op.drop_column("feedback", "prompt_version")
    op.drop_column("feedback", "model")
    op.drop_column("feedback", "reason")
