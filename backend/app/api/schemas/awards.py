"""낙찰·회사 설정·업체 검색 요청·응답 모델 (SPEC §15.6, P9)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints, field_validator

from app.awards.mapper import normalize_bizno

FieldTag = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=30)]
FieldWord = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=30)]


def _bizno(v: str) -> str:
    b = normalize_bizno(v)
    if b is None:
        raise ValueError("사업자번호는 숫자 10자리예요.")
    return b


class BiznoIn(BaseModel):
    bizno: str

    @field_validator("bizno")
    @classmethod
    def _check(cls, v: str) -> str:
        return _bizno(v)


class CompanyLookupOut(BaseModel):
    found: bool
    bizno: str
    name: str | None = None
    award_count: int = 0


class CompanySettingsIn(BaseModel):
    our_bizno: str | None = None
    our_name: Annotated[str, StringConstraints(strip_whitespace=True, max_length=100)] | None = None
    field_keywords: dict[FieldTag, Annotated[list[FieldWord], Field(max_length=20)]] = Field(
        default_factory=dict, max_length=20
    )
    backfill_years: int = Field(default=5, ge=1, le=10)

    @field_validator("our_bizno")
    @classmethod
    def _check(cls, v: str | None) -> str | None:
        return _bizno(v) if v else None


class YearProgressOut(BaseModel):
    year: int
    ratio: float  # 0~1


class AwardCoverageOut(BaseModel):
    covered_from: datetime | None
    covered_to: datetime | None
    target_from: datetime  # backfill_years만큼 과거
    collecting: bool  # 목표 기간을 아직 다 못 채웠으면 true


class CompanyOut(BaseModel):
    """GET /company: 우리 회사 설정과 수집 현황."""

    configured: bool
    our_bizno: str | None
    our_name: str | None
    field_keywords: dict[str, list[str]]
    backfill_years: int
    updated_at: datetime | None
    coverage: AwardCoverageOut
    years: list[YearProgressOut]
    calls_today: int
    calls_budget: int
    openings_calls_today: int  # 개찰 결과 자동 수집 몫(P12)
    openings_calls_budget: int
    unidentified_count: int  # 사업자번호가 없어 업체 통계에서 뺀 낙찰 수 (§15.9)
    reclassify_started: bool = False  # PUT에서 분야 사전이 바뀌어 재분류를 시작했는가


class PeriodOut(BaseModel):
    """요청 기간과 실제로 센 기간(KST 날짜). counted_*가 null이면 수집된 부분이 없다."""

    date_from: date = Field(serialization_alias="from")
    date_to: date = Field(serialization_alias="to")
    counted_from: date | None
    counted_to: date | None
    collecting: bool  # 요청 기간 일부가 아직 수집 중(그 부분은 세지 않음)


class YearRowOut(BaseModel):
    year: int
    count: int | None  # null = 수집 중
    amount_sum: int | None
    collecting: bool


class OrgRowOut(BaseModel):
    dminstt_cd: str | None
    dminstt_name: str | None
    count: int
    amount_sum: int


class FieldRowOut(BaseModel):
    field: str
    count: int


class AwardSummaryOut(BaseModel):
    bizno: str
    name: str
    is_us: bool
    period: PeriodOut
    count: int
    amount_sum: int
    amount_avg: int | None
    org_count: int
    g2b_rate_median: float | None  # 낙찰률(G2B, 예정가격 대비 %) 중앙값
    ratio_median: float | None  # 낙찰금액/추정가격 중앙값 (계산 가능한 건만)
    ratio_known: int
    joint_count: int
    # 우리 회사 화면만: 공동수급 구성원(대표는 타사)으로 낙찰한 건수.
    # 금액은 지분만큼 더했다(2026-11-24)
    member_count: int = 0
    first_at: datetime | None
    last_at: datetime | None
    by_year: list[YearRowOut]
    by_org: list[OrgRowOut]
    by_field: list[FieldRowOut]
    fields: list[str]  # 필터에 쓸 분야 목록


class AwardOut(BaseModel):
    bid_ntce_no: str
    bid_ntce_ord: str
    title: str
    bizno: str | None
    winner_name: str | None
    award_amount: int | None
    g2b_award_rate: float | None
    estimated_price: int | None
    award_ratio: float | None
    participant_count: int | None
    dminstt_cd: str | None
    dminstt_name: str | None
    opened_at: datetime | None
    awarded_on: date | None
    registered_at: datetime
    fields: list[str]
    is_joint: bool
    bid_id: str | None  # 'b123' — 같은 공고가 공고 DB에 있을 때만
    # 우리 회사 화면만: 공동수급에서 우리 역할(대표·구성원)과 지분(%).
    # 단독 낙찰·다른 업체 화면은 None
    our_role: Literal["lead", "member"] | None = None
    our_share: float | None = None


class AwardListOut(BaseModel):
    period: PeriodOut
    total: int
    items: list[AwardOut]
    next_cursor: str | None


class CompanyHitOut(BaseModel):
    bizno: str
    name: str
    award_count: int
    last_award_at: datetime | None
    is_us: bool


class CompanySearchOut(BaseModel):
    items: list[CompanyHitOut]
