"""G2B 일일 호출 예산 (SPEC §5.2). 오늘(KST) usage_logs.g2b_calls 합 + 아직 기록 안 된 호출 수로
판단한다.

usage_logs를 기록하는 쪽이 G2BClient.settle(n)으로 '진행 중' 수를 덜어 이중 집계를 막는다.
다른 프로세스(수집기 timer와 API)의 진행 중 호출은 기록된 뒤에만 보인다 — 약간 초과할 수 있음.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from app.db.models import UsageLog
from app.db.session import Database
from app.g2b.client import G2BBudgetExceeded

KST = timezone(timedelta(hours=9))


class DbCallBudget:
    def __init__(self, db: Database, limit: int) -> None:
        self.db, self.limit = db, limit
        self.pending = 0

    async def used_today(self) -> int:
        start = datetime.now(KST).replace(hour=0, minute=0, second=0, microsecond=0)
        async with self.db.session() as s:
            logged = await s.scalar(
                select(func.coalesce(func.sum(UsageLog.g2b_calls), 0)).where(
                    UsageLog.created_at >= start
                )
            )
        return int(logged or 0) + self.pending

    async def reserve(self) -> None:
        if await self.used_today() >= self.limit:
            raise G2BBudgetExceeded(f"G2B 일일 호출 예산 {self.limit}회 소진")
        self.pending += 1

    def settle(self, n: int) -> None:
        self.pending = max(0, self.pending - n)
