"""/api/v1/admin (SPEC §6.2, §7.9). 관리자 경로는 users·usage·collector만 (§9.4)."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import asdict
from datetime import date, datetime, time, timedelta, timezone
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Query, status
from sqlalchemy import select

from app.api.deps import AdminUser, Ctx, DbSession
from app.api.schemas import AcceptedOut, AdminUserList, AdminUserOut, AdminUserPatch, UserStatus
from app.api.schemas.admin import (
    CollectorRunIn,
    CollectorRunList,
    CollectorRunOut,
    CoverageOut,
    UsageOut,
    UsageRow,
)
from app.auth.admin import list_users, update_user
from app.collector import runner
from app.db.models import CollectorCoverage, CollectorRun
from app.errors import ApiError
from app.usage.stats import daily_usage

log = logging.getLogger(__name__)
KST = timezone(timedelta(hours=9))
_jobs: set[asyncio.Task[Any]] = set()

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/users")
async def get_users(
    _: AdminUser,
    s: DbSession,
    status: UserStatus | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AdminUserList:
    users, total = await list_users(s, status, limit, offset)
    return AdminUserList(items=[AdminUserOut.model_validate(u) for u in users], total=total)


@router.patch("/users/{user_id}")
async def patch_user(
    user_id: int, body: AdminUserPatch, admin: AdminUser, s: DbSession, ctx: Ctx
) -> AdminUserOut:
    user = await update_user(
        s, admin, user_id, status=body.status, role=body.role, now=ctx.deps.clock()
    )
    return AdminUserOut.model_validate(user)


@router.get("/usage")
async def get_usage(
    _: AdminUser,
    s: DbSession,
    ctx: Ctx,
    date_from: Annotated[date | None, Query(alias="from")] = None,
    date_to: Annotated[date | None, Query(alias="to")] = None,
    group: Literal["day"] = "day",
) -> UsageOut:
    """§5.8: 일별·이벤트별 요청 수, 캐시 계층별 적중률, G2B 호출, LLM 호출·토큰."""
    start = date_from or (ctx.deps.clock().astimezone(KST).date() - timedelta(days=13))
    rows = await daily_usage(s, datetime.combine(start, time(), KST))
    return UsageOut(
        items=[UsageRow(**asdict(r)) for r in rows if date_to is None or r.day <= date_to]
    )


@router.get("/collector/runs")
async def get_collector_runs(
    _: AdminUser, s: DbSession, limit: Annotated[int, Query(ge=1, le=100)] = 20
) -> CollectorRunList:
    rows = (
        await s.execute(select(CollectorRun).order_by(CollectorRun.id.desc()).limit(limit))
    ).scalars()
    items = [CollectorRunOut.model_validate(r) for r in rows]
    covs = (await s.execute(select(CollectorCoverage).order_by(CollectorCoverage.source))).scalars()
    return CollectorRunList(
        items=items,
        coverage=[
            CoverageOut(
                source=c.source,
                covered_from=c.covered_from,
                covered_to=c.covered_to,
                updated_at=c.updated_at,
            )
            for c in covs
        ],
    )


@router.post("/collector/run", status_code=status.HTTP_202_ACCEPTED)
async def post_collector_run(body: CollectorRunIn, admin: AdminUser, ctx: Ctx) -> AcceptedOut:
    """수동 수집. 백그라운드로 돌리고 바로 202. 결과는 collector/runs에서 본다."""
    deps = ctx.deps
    if deps.g2b is None:
        raise ApiError(503, "g2b_unavailable", "G2B 클라이언트가 설정되지 않았어요.")

    async def job() -> None:
        try:
            if body.mode == "backfill":
                await runner.backfill(deps, body.source, body.days)
            else:
                await runner.incremental(deps, body.source)
        except Exception:
            log.exception("manual collector run failed")

    task = asyncio.ensure_future(job())
    _jobs.add(task)
    task.add_done_callback(_jobs.discard)
    log.info("admin.collector_run user_id=%s mode=%s source=%s", admin.id, body.mode, body.source)
    return AcceptedOut()
