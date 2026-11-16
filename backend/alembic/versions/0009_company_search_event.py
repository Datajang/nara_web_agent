"""업체 검색 기록 (SPEC §15.9 '업체 검색은 usage_logs에 기록', P9)

usage_logs.event에 'company_search'를 더한다. 제약만 바꾸므로 이전 코드와 호환된다(§11.5).

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-16
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD = "event IN ('search','recommend','analyze','assistant_turn','collector')"
NEW = "event IN ('search','recommend','analyze','assistant_turn','collector','company_search')"


def upgrade() -> None:
    op.drop_constraint(op.f("ck_usage_logs_event"), "usage_logs", type_="check")
    op.create_check_constraint(op.f("ck_usage_logs_event"), "usage_logs", NEW)


def downgrade() -> None:
    op.execute("DELETE FROM usage_logs WHERE event = 'company_search'")
    op.drop_constraint(op.f("ck_usage_logs_event"), "usage_logs", type_="check")
    op.create_check_constraint(op.f("ck_usage_logs_event"), "usage_logs", OLD)
