"""/api/v1 비교·경쟁사 레이더·관심 경쟁사 (SPEC §15.6, P10). DB만 읽는다. 판정은 LLM 없이 규칙으로.

- GET /compare/{bizno}
- GET /competitors/candidates
- GET /competitors/watch, PUT·DELETE /competitors/watch/{bizno}
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Path, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.analysis.competitors import compare
from app.api.deps import ActiveUser, Ctx, DbSession
from app.api.routers.awards import company_not_found, not_configured, period_out
from app.api.schemas.competitors import (
    CandidateListOut,
    CandidateOut,
    CompanyRefOut,
    CompareCoverageOut,
    CompareOut,
    CompareYearOut,
    HeadToHeadOut,
    SharedOrgOut,
    VerdictOut,
    WatchedListOut,
    WatchedOut,
)
from app.awards import competitors as comp
from app.awards import service as svc
from app.deps import Deps
from app.errors import ApiError

router = APIRouter(tags=["competitors"])
Bizno = Annotated[str, Path(pattern=r"^\d{10}$")]
NOTE = "두 회사 모두 수집 완료된 기간"


async def _us(s: AsyncSession, deps: Deps) -> tuple[svc.OrgConfig, str, str]:
    org = await svc.load_org(s, deps.settings.awards_backfill_years_default)
    if org.our_bizno is None:
        raise not_configured()
    return org, org.our_bizno, org.our_name or org.our_bizno


@router.get("/compare/{bizno}")
async def get_compare(_: ActiveUser, s: DbSession, ctx: Ctx, bizno: Bizno) -> CompareOut:
    org, us, us_name = await _us(s, ctx.deps)
    if bizno == us:
        raise ApiError(400, "bad_request", "우리 회사와 같은 업체예요. 다른 업체를 골라 주세요.")
    them = await svc.get_company(s, bizno)
    if them is None:
        raise company_not_found()
    period, _cov = await svc.award_period(s, org.backfill_years, ctx.deps.clock())
    us_rows = await comp.load_facts(s, us, period)
    them_rows = await comp.load_facts(s, bizno, period)
    shared = await comp.shared_notices(s, us, bizno, period)
    c = compare(us_rows, them_rows, shared)
    years_us = await svc.count_by_year(s, us, period)
    years_them = {y.year: y for y in await svc.count_by_year(s, bizno, period)}
    return CompareOut(
        period=period_out(period),
        note=NOTE,
        us=CompanyRefOut(bizno=us, name=us_name),
        them=CompanyRefOut(bizno=bizno, name=them.name),
        verdicts=[
            VerdictOut(
                key=v.key,
                label=v.label,
                us=v.us,
                them=v.them,
                verdict=v.verdict,
                rule=v.rule,
                small_sample=v.small_sample,
            )
            for v in c.verdicts
        ],
        strengths=c.strengths,
        weaknesses=c.weaknesses,
        coverage=CompareCoverageOut(
            complete_from=svc.kst_date(period.eff_from) if period.eff_from else None,
            collecting=period.collecting,
        ),
        head_to_head=HeadToHeadOut(
            matched=c.head_to_head.matched,
            us_wins=c.head_to_head.us_wins,
            them_wins=c.head_to_head.them_wins,
        ),
        by_year=[
            CompareYearOut(
                year=y.year, us=y.count, them=years_them[y.year].count, collecting=y.collecting
            )
            for y in years_us
        ],
        shared_orgs=[SharedOrgOut(**vars(o)) for o in await comp.shared_orgs(s, us, bizno, period)],
        watched=await comp.is_watched(s, bizno),
    )


@router.get("/competitors/candidates")
async def get_candidates(
    _: ActiveUser,
    s: DbSession,
    ctx: Ctx,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    field: Annotated[str | None, Query(max_length=30)] = None,
    org: Annotated[str | None, Query(max_length=20)] = None,
) -> CandidateListOut:
    cfg, us, us_name = await _us(s, ctx.deps)
    period, _cov = await svc.award_period(s, cfg.backfill_years, ctx.deps.clock())
    items = await comp.candidates(
        s, us, period, field_tag=field or None, org=org or None, limit=limit
    )
    our_count = len(await comp.load_facts(s, us, period))
    return CandidateListOut(
        period=period_out(period),
        us=CompanyRefOut(bizno=us, name=us_name),
        our_count=our_count,
        items=[CandidateOut(**vars(c)) for c in items],
    )


async def _watched_out(s: AsyncSession, deps: Deps) -> list[WatchedOut]:
    cfg = await svc.load_org(s, deps.settings.awards_backfill_years_default)
    period, _cov = await svc.award_period(s, cfg.backfill_years, deps.clock())
    return [WatchedOut(**vars(w)) for w in await comp.list_watched(s, period)]


@router.get("/competitors/watch")
async def get_watched(_: ActiveUser, s: DbSession, ctx: Ctx) -> WatchedListOut:
    return WatchedListOut(items=await _watched_out(s, ctx.deps))


@router.put("/competitors/watch/{bizno}")
async def put_watched(user: ActiveUser, s: DbSession, ctx: Ctx, bizno: Bizno) -> WatchedListOut:
    """관심 경쟁사 등록(서비스 전체 공유, 이미 있으면 그대로)."""
    if await svc.get_company(s, bizno) is None:
        raise company_not_found()
    await comp.watch(s, bizno, user.id)
    await s.commit()
    return WatchedListOut(items=await _watched_out(s, ctx.deps))


@router.delete("/competitors/watch/{bizno}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_watched(_: ActiveUser, s: DbSession, bizno: Bizno) -> Response:
    await comp.unwatch(s, bizno)
    await s.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
