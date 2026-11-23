"""관심 경쟁사를 계정별로 (2026-11-23, docs/decisions/2026-11-23-watch-per-user.md)

- watched_companies: 서비스 전체 공유(PK bizno) → 계정별(PK user_id, bizno)
- 기존 행은 추가한 사람(added_by)의 개인 목록으로 옮기고,
  추가한 사람을 모르는 행은 지운다(사용자 결정)
- 팀 목록은 따로 저장하지 않는다: 팀원(users.team_id)의 개인 목록을 모아 보여 준다
- 이전 코드와는 호환되지 않는다(PK가 바뀜). 롤백하면 관심 경쟁사 추가만 실패하므로
  함께 내리지 않는다

Revision ID: 0012
Revises: 0011
Create Date: 2026-11-23
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

T = "watched_companies"


def upgrade() -> None:
    op.execute(sa.text(f"DELETE FROM {T} WHERE added_by IS NULL"))
    op.drop_constraint(f"fk_{T}_added_by_users", T, type_="foreignkey")
    op.drop_constraint(f"pk_{T}", T, type_="primary")
    op.alter_column(T, "added_by", new_column_name="user_id", nullable=False)
    op.create_foreign_key(
        f"fk_{T}_user_id_users", T, "users", ["user_id"], ["id"], ondelete="CASCADE"
    )
    op.create_primary_key(f"pk_{T}", T, ["user_id", "bizno"])
    op.create_index(f"ix_{T}_bizno", T, ["bizno"])


def downgrade() -> None:
    op.drop_index(f"ix_{T}_bizno", T)
    op.drop_constraint(f"pk_{T}", T, type_="primary")
    op.drop_constraint(f"fk_{T}_user_id_users", T, type_="foreignkey")
    # 같은 회사를 여러 명이 담았으면 가장 먼저 담은 한 행만 남긴다
    op.execute(
        sa.text(
            f"DELETE FROM {T} w USING {T} o WHERE w.bizno = o.bizno "
            "AND (w.added_at, w.user_id) > (o.added_at, o.user_id)"
        )
    )
    op.alter_column(T, "user_id", new_column_name="added_by", nullable=True)
    op.create_foreign_key(
        f"fk_{T}_added_by_users", T, "users", ["added_by"], ["id"], ondelete="SET NULL"
    )
    op.create_primary_key(f"pk_{T}", T, ["bizno"])
