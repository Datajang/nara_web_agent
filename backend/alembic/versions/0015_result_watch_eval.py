"""결과 감시: 협상 공고 제안서평가 일시 (2026-11-27)

docs/decisions/2026-11-27-proposal-eval-date.md

- bid_result_watch.eval_at: 나라장터 웹 공고 상세의 제안서평가 시작(없으면 NULL)
- bid_result_watch.eval_checked_at: 마지막으로 웹에서 읽은 시각(하루 한 번 다시 읽는다)
- NULL 허용 열 추가만이라 이전 코드와 호환된다(§11.5)

Revision ID: 0015
Revises: 0014
Create Date: 2026-11-27
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TS = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.add_column("bid_result_watch", sa.Column("eval_at", TS, nullable=True))
    op.add_column("bid_result_watch", sa.Column("eval_checked_at", TS, nullable=True))


def downgrade() -> None:
    op.drop_column("bid_result_watch", "eval_checked_at")
    op.drop_column("bid_result_watch", "eval_at")
