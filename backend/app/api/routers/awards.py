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
    AwardOut,
    AwardSummaryOut,
    BiznoIn,
    CompanyHitOut,
    CompanyLookupOut,
    CompanyOut,
    CompanySearchOut,
    CompanySettingsIn,
    FieldRowOut,
    OrgRowOut,
    PeriodOut,
    YearProgressOut,
    YearRowOut,
)
from app.awards import service as svc
from app.awards.fields import clean_keywords
from app.awards.mapper import normalize_bizno
from app.awards.reclassify import reclassify
from app.db.models import OrgSettings, UsageLog
from app.deps import Deps
from app.errors import ApiError

log = logging.getLogger(__name__)
router = APIRouter(tags=["awards"])
_jobs: set[asyncio.Task[Any]] = set()

Bizno = Annotated[str, Path(pattern=r"^\d{10}$")]
DateFrom = Annotated[date | None, Query(alias="from")]
DateTo = Annotated[date | None, Query(alias="to")]


def not_configured() -> ApiError:
    return ApiError(
        404,
        "not_configured",
        "우리 회사가 아직 설정되지 않았어요. 관리자에게 회사 설정을 요청해 주세요.",
    )


def company_not_found() -> ApiError:
    return ApiError(404, "not_found", "수집된 낙찰에서 이 업체를 찾을 수 없어요.")


def period_out(p: svc.Period) -> PeriodOut:
    return PeriodOut(
        date_from=svc.kst_date(p.req_from),
        date_to=svc.kst_date(p.req_to),
        counted_from=svc.kst_date(p.eff_from) if p.eff_from else None,
        counted_to=svc.kst_date(p.eff_to) if p.eff_to else None,
        collecting=p.collecting,
    )


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


async def _summary_out(
    s: AsyncSession, deps: Deps, bizno: str, name: str, date_from: date | None, date_to: date | None
) -> AwardSummaryOut:
    org = await svc.load_org(s, deps.settings.awards_backfill_years_default)
    period, _cov = await svc.award_period(s, org.backfill_years, deps.clock(), date_from, date_to)
    sm = await svc.summarize(s, bizno, period)
    return AwardSummaryOut(
        bizno=bizno,
        name=name,
        is_us=bizno == org.our_bizno,
        period=period_out(period),
        count=sm.count,
        amount_sum=sm.amount_sum,
        amount_avg=sm.amount_avg,
        org_count=sm.org_count,
        g2b_rate_median=sm.g2b_rate_median,
        ratio_median=sm.ratio_median,
        ratio_known=sm.ratio_known,
        joint_count=sm.joint_count,
        first_at=sm.first_at,
        last_at=sm.last_at,
        by_year=[YearRowOut(**vars(y)) for y in sm.by_year],
        by_org=[OrgRowOut(**vars(o)) for o in sm.by_org],
        by_field=[FieldRowOut(**vars(f)) for f in sm.by_field],
        fields=svc.known_fields(org.field_keywords, sm.by_field),
    )


async def resolve_target(s: AsyncSession, deps: Deps, bizno: str | None) -> tuple[str, str]:
    """(bizno, 표시 이름). bizno가 없으면 우리 회사."""
    if bizno is None:
        org = await svc.load_org(s, deps.settings.awards_backfill_years_default)
        if org.our_bizno is None:
            raise not_configured()
        return org.our_bizno, org.our_name or org.our_bizno
    company = await svc.get_company(s, bizno)
    if company is None:
        raise company_not_found()
    return bizno, company.name


@router.get("/awards/summary")
async def get_awards_summary(
    _: ActiveUser,
    s: DbSession,
    ctx: Ctx,
    bizno: Annotated[str | None, Query(pattern=r"^\d{10}$")] = None,
    date_from: DateFrom = None,
    date_to: DateTo = None,
) -> AwardSummaryOut:
    b, name = await resolve_target(s, ctx.deps, bizno)
    return await _summary_out(s, ctx.deps, b, name, date_from, date_to)


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
    b, _name = await resolve_target(s, ctx.deps, bizno)
    org_cfg = await svc.load_org(s, ctx.deps.settings.awards_backfill_years_default)
    period, _cov = await svc.award_period(
        s, org_cfg.backfill_years, ctx.deps.clock(), date_from, date_to
    )
    cur = svc.decode_cursor(cursor) if cursor else None
    if cursor and cur is None:
        raise ApiError(
            400, "bad_request", "목록 위치가 올바르지 않아요. 처음부터 다시 불러와 주세요."
        )
    page = await svc.list_awards(
        s, b, period, field_tag=field or None, org=org or None, cursor=cur, limit=limit
    )
    return AwardListOut(
        period=period_out(period),
        total=page.total,
        next_cursor=page.next_cursor,
        items=[_award_out(i) for i in page.items],
    )


def _award_out(i: svc.AwardItem) -> AwardOut:
    a = i.award
    return AwardOut(
        bid_ntce_no=a.bid_ntce_no,
        bid_ntce_ord=a.bid_ntce_ord,
        title=a.title,
        bizno=a.bizno,
        winner_name=a.winner_name,
        award_amount=a.award_amount,
        g2b_award_rate=float(a.g2b_award_rate) if a.g2b_award_rate is not None else None,
        estimated_price=a.estimated_price,
        award_ratio=float(a.award_ratio) if a.award_ratio is not None else None,
        participant_count=a.participant_count,
        dminstt_cd=a.dminstt_cd,
        dminstt_name=a.dminstt_name,
        opened_at=a.opened_at,
        awarded_on=a.awarded_on,
        registered_at=a.registered_at,
        fields=list(a.fields or []),
        is_joint=a.is_joint,
        bid_id=f"b{i.bid_id}" if i.bid_id is not None else None,
    )


@router.get("/companies/search")
async def search_companies(
    user: ActiveUser,
    s: DbSession,
    ctx: Ctx,
    q: Annotated[str, Query(min_length=1, max_length=100)],
) -> CompanySearchOut:
    key = svc.search_key(q)
    if key is None:
        raise ApiError(
            422,
            "validation_error",
            "업체명은 두 글자 이상, 사업자번호는 숫자 10자리로 찾아 주세요.",
            details=[{"field": "q", "reason": "too_short"}],
        )
    ctx.limiter.hit(f"company-search:{user.id}", 60, 60)
    hits = await svc.search_companies(s, key)
    org = await svc.load_org(s, ctx.deps.settings.awards_backfill_years_default)
    # §15.9: 업체 검색은 usage_logs에 남긴다. 검색어 대신 방식과 결과 수만
    s.add(
        UsageLog(
            user_id=user.id,
            event="company_search",
            cache={"by": key[0], "results": len(hits)},
        )
    )
    await s.commit()
    return CompanySearchOut(
        items=[
            CompanyHitOut(
                bizno=h.bizno,
                name=h.name,
                award_count=h.award_count,
                last_award_at=h.last_award_at,
                is_us=h.bizno == org.our_bizno,
            )
            for h in hits
        ]
    )


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
        raise company_not_found()
    return await _summary_out(s, ctx.deps, company.bizno, company.name, date_from, date_to)
