"""마이그레이션과 모델이 어긋나지 않는다 (규칙 5: DB 변경은 Alembic으로만)."""

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext

from app.db.base import Base


async def test_migrations_match_models(db):
    def diff(conn):
        return compare_metadata(MigrationContext.configure(conn), Base.metadata)

    async with db.engine.connect() as conn:
        assert await conn.run_sync(diff) == []
