"""/api/v1 낙찰·회사 설정·업체 검색 (SPEC §15.6, P9). DB만 읽는다(G2B 호출 없음).

- GET /company, POST /admin/company/lookup, PUT /admin/company
- GET /awards/summary, GET /awards
- GET /companies/search, GET /companies/{bizno}
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Path, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import ActiveUser, AdminUser, Ctx, DbSession
from app.api.schemas.awards import (
    AwardCoverageOut,
    AwardListOut,
    AwardSummaryOut,
    BiznoIn,
    CompanyLookupOut,
    CompanyOut,
    CompanySearchOut,
    CompanySettingsIn,
    YearProgressOut,
)
from app.awards import service as svc
from app.awards import views
from app.awards.fields import clean_keywords
from app.awards.mapper import normalize_bizno
from app.awards.reclassify import reclassify
from app.db.models import OrgSettings
from app.deps import Deps
from app.errors import ApiError
from app.g2b.client import OPENINGS_SOURCE

log = logging.getLogger(__name__)
router = APIRouter(tags=["awards"])
_jobs: set[asyncio.Task[Any]] = set()

Bizno = Annotated[str, Path(pattern=r"^\d{10}$")]
DateFrom = Annotated[date | None, Query(alias="from")]
DateTo = Annotated[date | None, Query(alias="to")]


async def _company_out(s: AsyncSession, deps: Deps, reclassify_started: bool = False) -> CompanyOut:
    org = await svc.load_org(s, deps.settings.awards_backfill_years_default)
    now = deps.clock()
    period, cov = await svc.award_period(s, org.backfill_years, now)
    target_from = period.req_from
    return CompanyOut(
        configured=org.our_bizno is not None,
        our_bizno=org.our_bizno,
        our_name=org.our_name,
        field_keywords=org.field_keywords,
        backfill_years=org.backfill_years,
        updated_at=org.updated_at,
        coverage=AwardCoverageOut(
            covered_from=cov.covered_from if cov else None,
            covered_to=cov.covered_to if cov else None,
            target_from=target_from,
            collecting=cov is None or cov.covered_from > target_from + svc.FROM_SLACK,
        ),
        years=[
            YearProgressOut(year=y.year, ratio=y.ratio)
            for y in svc.year_progress(cov, target_from, now)
        ],
        calls_today=await svc.award_calls_today(s, now),
        calls_budget=deps.settings.g2b_awards_daily_budget,
        openings_calls_today=await svc.award_calls_today(s, now, frozenset({OPENINGS_SOURCE})),
        openings_calls_budget=deps.settings.g2b_openings_daily_budget,
        unidentified_count=await svc.unidentified_count(s),
        reclassify_started=reclassify_started,
    )


@router.get("/company")
async def get_company_settings(_: ActiveUser, s: DbSession, ctx: Ctx) -> CompanyOut:
    return await _company_out(s, ctx.deps)


@router.post("/admin/company/lookup")
async def lookup_company(body: BiznoIn, _: AdminUser, s: DbSession) -> CompanyLookupOut:
    name, n = await svc.lookup_name(s, body.bizno)
    return CompanyLookupOut(found=name is not None, bizno=body.bizno, name=name, award_count=n)


@router.put("/admin/company")
async def put_company_settings(
    body: CompanySettingsIn, admin: AdminUser, s: DbSession, ctx: Ctx
) -> CompanyOut:
    """저장. 백필 범위는 수집기가 매번 backfill_years로 다시 계획하므로 다음 실행부터 반영된다.
    분야 사전이 바뀌면 재분류(DB만)를 백그라운드로 시작한다."""
    name = body.our_name or None
    if body.our_bizno and not name:
        name, _ = await svc.lookup_name(s, body.our_bizno)
        if not name:
            raise ApiError(
                422,
                "validation_error",
                "수집된 낙찰에 없는 사업자번호예요. 회사 이름을 직접 입력해 주세요.",
                details=[{"field": "our_name", "reason": "required"}],
            )
    keywords = clean_keywords(body.field_keywords)
    row = await s.get(OrgSettings, 1)
    before = clean_keywords(row.field_keywords) if row is not None else {}
    changed = before != keywords
    if row is None:
        row = OrgSettings(id=1)
        s.add(row)
    row.our_bizno = body.our_bizno
    row.our_name = name if body.our_bizno else None
    row.field_keywords = keywords
    row.backfill_years = body.backfill_years
    row.updated_by = admin.id
    row.updated_at = ctx.deps.clock()
    await s.commit()
    if changed:
        task = asyncio.create_task(_reclassify(ctx.deps))
        _jobs.add(task)
        task.add_done_callback(_jobs.discard)
    return await _company_out(s, ctx.deps, reclassify_started=changed)


async def _reclassify(deps: Deps) -> None:
    try:
        r = await reclassify(deps.db)
        log.info("낙찰 분야 재분류: %s건 중 %s건 변경", r.scanned, r.fields_changed)
    except Exception:
        log.exception("낙찰 분야 재분류 실패")


@router.get("/awards/summary")
async def get_awards_summary(
    _: ActiveUser,
    s: DbSession,
    ctx: Ctx,
    bizno: Annotated[str | None, Query(pattern=r"^\d{10}$")] = None,
    date_from: DateFrom = None,
    date_to: DateTo = None,
) -> AwardSummaryOut:
    b, name = await views.resolve_target(s, ctx.deps, bizno)
    return await views.summary_out(s, ctx.deps, b, name, date_from, date_to)


@router.get("/awards")
async def get_awards(
    _: ActiveUser,
    s: DbSession,
    ctx: Ctx,
    bizno: Annotated[str | None, Query(pattern=r"^\d{10}$")] = None,
    date_from: DateFrom = None,
    date_to: DateTo = None,
    field: Annotated[str | None, Query(max_length=30)] = None,
    org: Annotated[str | None, Query(max_length=20)] = None,
    cursor: Annotated[str | None, Query(max_length=200)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> AwardListOut:
    b, _name = await views.resolve_target(s, ctx.deps, bizno)
    return await views.award_list(
        s,
        ctx.deps,
        b,
        date_from=date_from,
        date_to=date_to,
        field_tag=field or None,
        org=org or None,
        cursor=cursor,
        limit=limit,
    )


@router.get("/companies/search")
async def search_companies(
    user: ActiveUser,
    s: DbSession,
    ctx: Ctx,
    q: Annotated[str, Query(min_length=1, max_length=100)],
) -> CompanySearchOut:
    if svc.search_key(q) is None:
        raise views.bad_query()
    ctx.limiter.hit(f"company-search:{user.id}", 60, 60)
    return await views.company_search(s, ctx.deps, user.id, q)


@router.get("/companies/{bizno}")
async def get_company(
    _: ActiveUser,
    s: DbSession,
    ctx: Ctx,
    bizno: Bizno,
    date_from: DateFrom = None,
    date_to: DateTo = None,
) -> AwardSummaryOut:
    b = normalize_bizno(bizno)
    company = await svc.get_company(s, b) if b else None
    if company is None:
        raise views.company_not_found()
    return await views.summary_out(s, ctx.deps, company.bizno, company.name, date_from, date_to)
