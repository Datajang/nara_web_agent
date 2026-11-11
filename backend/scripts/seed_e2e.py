"""E2E 스모크용 시험 데이터 (SPEC §12.8 main 병합 게이트). 개발·CI 전용, 운영에서는 거부한다.

    E2E_ADMIN=e2e@corp.example E2E_ADMIN_PW=... NARA_ENV_FILE=.env uv run python -m scripts.seed_e2e

- 관리자 1명(활성·인증됨), 가짜 공고 몇 건, 두 소스의 수집 범위(지금 + 1일까지)를 넣는다.
  범위가 검색 창을 덮으므로 검색이 G2B를 부르지 않는다(외부 호출 없음, 규칙 3).
- 공고 형식은 테스트 가짜(tests.fakes.g2b)를 실제 매퍼로 넣어 운영과 같은 경로를 탄다.
- 여러 번 실행해도 결과가 같다.
"""

from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime, timedelta

from sqlalchemy.dialects.postgresql import insert

from app.cli import create_admin
from app.collector.upsert import upsert_bids
from app.config import get_settings
from app.db.models import CollectorCoverage
from app.db.session import Database
from app.deps import utcnow
from app.g2b.mapper import to_record
from tests.fakes.g2b import regular_item

TITLES = [
    "E2E 클라우드 전환 컨설팅 용역",
    "E2E 공공 클라우드 기반 민원 분석 시스템 구축",
    "E2E 도로 유지보수 공사",
    "E2E AI 데이터 플랫폼 고도화",
]


def guard() -> None:
    if os.environ.get("ENV", get_settings().env) == "production":
        raise SystemExit("seed_e2e는 운영(ENV=production)에서 실행하지 않습니다")


async def seed(db: Database, email: str, password: str, *, now: datetime | None = None) -> None:
    now = now or utcnow()
    await create_admin(db, email, password)
    items = [
        regular_item(f"R26BKE2E{i:05d}", now - timedelta(hours=6 * (i + 1)), title=title)
        for i, title in enumerate(TITLES)
    ]
    async with db.transaction() as s:
        await upsert_bids(s, [to_record("regular", it) for it in items])
        for source in ("regular", "prespec"):
            values = {
                "source": source,
                "covered_from": now - timedelta(days=100),
                "covered_to": now + timedelta(days=1),
            }
            await s.execute(
                insert(CollectorCoverage)
                .values(**values)
                .on_conflict_do_update(index_elements=["source"], set_=values)
            )


async def _main() -> int:
    guard()
    email, password = os.environ.get("E2E_ADMIN"), os.environ.get("E2E_ADMIN_PW")
    if not email or not password:
        print("E2E_ADMIN, E2E_ADMIN_PW가 필요합니다", file=sys.stderr)
        return 2
    settings = get_settings()
    db = Database(settings.database_url, pool_size=2, lock_pool_size=1)
    try:
        await seed(db, email, password)
    finally:
        await db.dispose()
    print(f"seeded {len(TITLES)} bids")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
