"""낙찰·비교 API 응답 만들기 (SPEC §15.6).

라우터와 어시스턴트 도구(§15.8)가 같은 함수·같은 스키마를 쓴다.

DB만 읽는다. 판정은 app.analysis.competitors(LLM 없음).
"""

from __future__ import annotations

from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.analysis.competitors import compare
from app.api.schemas.awards import (
    AwardListOut,
    AwardOut,
    AwardSummaryOut,
    CompanyHitOut,
    CompanySearchOut,
    FieldRowOut,
    OrgRowOut,
    PeriodOut,
    YearRowOut,
)
from app.api.schemas.competitors import (
    CompanyRefOut,
    CompareCoverageOut,
    CompareJointOut,
    CompareOut,
    CompareYearOut,
    HeadToHeadOut,
    JointPartnerOut,
    SharedOrgOut,
    VerdictOut,
)
from app.awards import competitors as comp
from app.awards import service as svc
from app.collector import coverage
from app.db.models import UsageLog
from app.deps import Deps
from app.errors import ApiError

COMPARE_NOTE = "두 회사 모두 수집 완료된 기간"


def not_configured() -> ApiError:
    return ApiError(
        404,
        "not_configured",
        "우리 회사가 아직 설정되지 않았어요. 관리자에게 회사 설정을 요청해 주세요.",
    )


def company_not_found() -> ApiError:
    return ApiError(404, "not_found", "수집된 낙찰에서 이 업체를 찾을 수 없어요.")


def bad_query() -> ApiError:
    return ApiError(
        422,
        "validation_error",
        "업체명은 두 글자 이상, 사업자번호는 숫자 10자리로 찾아 주세요.",
        details=[{"field": "q", "reason": "too_short"}],
    )


def period_out(p: svc.Period) -> PeriodOut:
    return PeriodOut(
        date_from=svc.kst_date(p.req_from),
        date_to=svc.kst_date(p.req_to),
        counted_from=svc.kst_date(p.eff_from) if p.eff_from else None,
        counted_to=svc.kst_date(p.eff_to) if p.eff_to else None,
        collecting=p.collecting,
    )


async def org_config(s: AsyncSession, deps: Deps) -> svc.OrgConfig:
    return await svc.load_org(s, deps.settings.awards_backfill_years_default)


async def resolve_target(s: AsyncSession, deps: Deps, bizno: str | None) -> tuple[str, str]:
    """(bizno, 표시 이름). bizno가 없으면 우리 회사."""
    if bizno is None:
        org = await org_config(s, deps)
        if org.our_bizno is None:
            raise not_configured()
        return org.our_bizno, org.our_name or org.our_bizno
    company = await svc.get_company(s, bizno)
    if company is None:
        raise company_not_found()
    return bizno, company.name


async def summary_out(
    s: AsyncSession,
    deps: Deps,
    bizno: str,
    name: str,
    date_from: date | None = None,
    date_to: date | None = None,
) -> AwardSummaryOut:
    org = await org_config(s, deps)
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


def award_out(i: svc.AwardItem) -> AwardOut:
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


async def award_list(
    s: AsyncSession,
    deps: Deps,
    bizno: str,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    field_tag: str | None = None,
    org: str | None = None,
    q: str | None = None,
    cursor: str | None = None,
    limit: int = 50,
) -> AwardListOut:
    org_cfg = await org_config(s, deps)
    period, _cov = await svc.award_period(
        s, org_cfg.backfill_years, deps.clock(), date_from, date_to
    )
    cur = svc.decode_cursor(cursor) if cursor else None
    if cursor and cur is None:
        raise ApiError(
            400, "bad_request", "목록 위치가 올바르지 않아요. 처음부터 다시 불러와 주세요."
        )
    page = await svc.list_awards(
        s, bizno, period, field_tag=field_tag, org=org, q=q, cursor=cur, limit=limit
    )
    return AwardListOut(
        period=period_out(period),
        total=page.total,
        next_cursor=page.next_cursor,
        items=[award_out(i) for i in page.items],
    )


async def company_search(
    s: AsyncSession, deps: Deps, user_id: int | None, q: str
) -> CompanySearchOut:
    """업체명 일부 또는 사업자번호. §15.9: usage_logs에 검색어 대신 방식과 결과 수만 남긴다."""
    key = svc.search_key(q)
    if key is None:
        raise bad_query()
    hits = await svc.search_companies(s, key)
    org = await org_config(s, deps)
    s.add(
        UsageLog(
            user_id=user_id, event="company_search", cache={"by": key[0], "results": len(hits)}
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


async def us_config(s: AsyncSession, deps: Deps) -> tuple[svc.OrgConfig, str, str]:
    org = await org_config(s, deps)
    if org.our_bizno is None:
        raise not_configured()
    return org, org.our_bizno, org.our_name or org.our_bizno


def _partners(rows: list[comp.JointPartner]) -> list[JointPartnerOut]:
    return [JointPartnerOut(bizno=r.bizno, name=r.name, count=r.count) for r in rows]


async def compare_out(
    s: AsyncSession, deps: Deps, bizno: str, user_id: int | None = None
) -> CompareOut:
    """user_id가 있으면 그 계정의 관심 여부를 채운다(관심 경쟁사는 계정별, 2026-11-23)."""
    org, us, us_name = await us_config(s, deps)
    if bizno == us:
        raise ApiError(400, "bad_request", "우리 회사와 같은 업체예요. 다른 업체를 골라 주세요.")
    them = await svc.get_company(s, bizno)
    if them is None:
        raise company_not_found()
    period, _cov = await svc.award_period(s, org.backfill_years, deps.clock())
    us_rows = await comp.load_facts(s, us, period)
    them_rows = await comp.load_facts(s, bizno, period)
    shared = await comp.shared_notices(s, us, bizno, period)
    c = compare(us_rows, them_rows, shared)
    years_us = await svc.count_by_year(s, us, period)
    years_them = {y.year: y for y in await svc.count_by_year(s, bizno, period)}
    return CompareOut(
        period=period_out(period),
        note=COMPARE_NOTE,
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
        joint=CompareJointOut(
            collected=await coverage.get(s, "contracts") is not None,
            us=_partners(await comp.joint_partners(s, us, period)),
            them=_partners(await comp.joint_partners(s, bizno, period)),
        ),
        watched=user_id is not None and await comp.is_watched(s, bizno, user_id),
    )
