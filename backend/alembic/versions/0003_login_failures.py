"""로그인 실패를 이메일 해시 기준으로 센다 (P2, §9.2-4·§9.8-3 열거 방지)

users.failed_login_count·locked_until 대신 login_failures(email_hash)를 쓴다. 없는 이메일도 같은
횟수에서 잠겨 응답으로 계정 존재 여부를 알 수 없다. docs/decisions/2026-11-11-p2-auth.md.

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-11
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "login_failures",
        sa.Column("email_hash", sa.Text(), nullable=False),
        sa.Column("failures", sa.Integer(), server_default="0", nullable=False),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("email_hash", name=op.f("pk_login_failures")),
    )
    op.drop_column("users", "failed_login_count")
    op.drop_column("users", "locked_until")


def downgrade() -> None:
    op.add_column("users", sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "users",
        sa.Column("failed_login_count", sa.Integer(), server_default="0", nullable=False),
    )
    op.drop_table("login_failures")
