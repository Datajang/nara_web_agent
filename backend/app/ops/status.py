"""수집 상태 조회. /readyz와 경보 점검이 같이 쓴다 (§11.7)."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Literal

from sqlalchemy import func, select

from app.db.models import CollectorRun
from app.deps import Deps

CollectorState = Literal["ok", "stale", "never"]


async def last_collector_ok(deps: Deps) -> datetime | None:
    async with deps.db.session() as s:
        last: datetime | None = await s.scalar(
            select(func.max(CollectorRun.finished_at)).where(CollectorRun.status == "ok")
        )
    return last


def collector_state(deps: Deps, last_ok: datetime | None) -> CollectorState:
    if last_ok is None:
        return "never"
    limit = timedelta(hours=deps.settings.alert_collector_stale_h)
    return "ok" if deps.clock() - last_ok <= limit else "stale"
