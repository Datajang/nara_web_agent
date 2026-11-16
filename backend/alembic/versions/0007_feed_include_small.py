"""관심 공고에 1억 미만도 보기 (2026-11-16 사용자 요청)

관심 공고는 기본으로 예산 1억 원 이상만 보여 주고, 사용자가 설정하면 1억 미만도 보여 준다.
users.feed_include_small(기본 false). 기본값이 있어 이전 코드와 호환된다(§11.5).

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-16
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("feed_include_small", sa.Boolean(), server_default=sa.false(), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("users", "feed_include_small")
