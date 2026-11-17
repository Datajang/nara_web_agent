"""우리 투찰 결과: 개찰 결과 비고 (P12, docs/decisions/2026-11-17-p12a-opening-ranks.md)

- bid_participants.remark: 개찰완료 목록의 비고(rmrk). 순위가 빈 행은 부적격·탈락이고 사유가
  여기 있다('낙찰하한선 미달', '협상평가부적격자' 등). 개인정보가 아니다

Revision ID: 0011
Revises: 0010
Create Date: 2026-11-17
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("bid_participants", sa.Column("remark", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("bid_participants", "remark")
