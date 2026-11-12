"""회원이 만드는 팀·관심 키워드·팀 프로필 (P6, SPEC §13 P6)

- teams(name, invite_code UNIQUE)
- users.team_id·team_role·team_joined_at(한 계정 한 팀), users.interest_keywords
- profiles.team_id, profiles.user_id NULL 허용, 둘 중 정확히 하나만 값
모두 NULL 허용·기본값이 있어 이전 코드와 호환된다(§11.5). 기존 프로필은 개인 프로필로 남는다.

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "teams",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("invite_code", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_teams")),
        sa.UniqueConstraint("invite_code", name=op.f("uq_teams_invite_code")),
    )
    op.add_column("users", sa.Column("team_id", sa.BigInteger(), nullable=True))
    op.add_column("users", sa.Column("team_role", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("team_joined_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "users",
        sa.Column(
            "interest_keywords",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    op.create_foreign_key(
        op.f("fk_users_team_id_teams"), "users", "teams", ["team_id"], ["id"], ondelete="SET NULL"
    )
    op.create_check_constraint(
        op.f("ck_users_team_role"), "users", "team_role IS NULL OR team_role IN ('owner','member')"
    )
    op.create_check_constraint(
        op.f("ck_users_team_pair"), "users", "(team_id IS NULL) = (team_role IS NULL)"
    )
    op.create_index(op.f("ix_users_team_id"), "users", ["team_id"])

    op.add_column("profiles", sa.Column("team_id", sa.BigInteger(), nullable=True))
    op.create_foreign_key(
        op.f("fk_profiles_team_id_teams"),
        "profiles",
        "teams",
        ["team_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.alter_column("profiles", "user_id", nullable=True)
    op.create_check_constraint(
        op.f("ck_profiles_owner"), "profiles", "(user_id IS NULL) <> (team_id IS NULL)"
    )
    op.create_index(op.f("ix_profiles_team_id"), "profiles", ["team_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_profiles_team_id"), table_name="profiles")
    op.drop_constraint(op.f("ck_profiles_owner"), "profiles", type_="check")
    op.execute("DELETE FROM profiles WHERE user_id IS NULL")
    op.alter_column("profiles", "user_id", nullable=False)
    op.drop_constraint(op.f("fk_profiles_team_id_teams"), "profiles", type_="foreignkey")
    op.drop_column("profiles", "team_id")
    op.drop_index(op.f("ix_users_team_id"), table_name="users")
    op.drop_constraint(op.f("ck_users_team_pair"), "users", type_="check")
    op.drop_constraint(op.f("ck_users_team_role"), "users", type_="check")
    op.drop_constraint(op.f("fk_users_team_id_teams"), "users", type_="foreignkey")
    for col in ("interest_keywords", "team_joined_at", "team_role", "team_id"):
        op.drop_column("users", col)
    op.drop_table("teams")
