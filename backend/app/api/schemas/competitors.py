"""비교·경쟁사 레이더·관심 경쟁사 응답 모델 (SPEC §15.6, P10)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel

from app.api.schemas.awards import PeriodOut


class CompanyRefOut(BaseModel):
    bizno: str
    name: str


class VerdictOut(BaseModel):
    key: str  # count, amount_sum, amount_avg, org_count, field:<태그>, head_to_head, …
    label: str
    us: float | None
    them: float | None
    verdict: Literal["up", "same", "down", "info"]  # 앞섬·비슷·뒤처짐·참고
    rule: Literal["ratio_20", "field_2x", "head_to_head", "info"]
    small_sample: bool  # 표본 적음


class CompareCoverageOut(BaseModel):
    complete_from: date | None  # 두 회사 모두 수집 완료된 기간의 시작
    collecting: bool


class HeadToHeadOut(BaseModel):
    matched: int  # 두 회사가 모두 참가한 공고(개찰 결과를 조회한 것만)
    us_wins: int
    them_wins: int


class CompareYearOut(BaseModel):
    year: int
    us: int | None  # null = 수집 중
    them: int | None
    collecting: bool


class SharedOrgOut(BaseModel):
    dminstt_cd: str
    dminstt_name: str | None
    us: int
    them: int


class CompareOut(BaseModel):
    period: PeriodOut
    note: str  # '두 회사 모두 수집 완료된 기간'
    us: CompanyRefOut
    them: CompanyRefOut
    verdicts: list[VerdictOut]
    strengths: list[str]  # 앞섬 항목 key, |차이| 큰 순 최대 5
    weaknesses: list[str]  # 뒤처짐 항목 key
    coverage: CompareCoverageOut
    head_to_head: HeadToHeadOut
    by_year: list[CompareYearOut]
    shared_orgs: list[SharedOrgOut]
    watched: bool


class CandidateOut(BaseModel):
    bizno: str
    name: str
    overlap: float  # 0~100
    org_overlap: float  # 0~1
    field_overlap: float  # 0~1
    award_count: int
    last_award_at: datetime | None
    watched: bool


class CandidateListOut(BaseModel):
    period: PeriodOut
    us: CompanyRefOut
    our_count: int
    items: list[CandidateOut]


class WatchedOut(BaseModel):
    bizno: str
    name: str
    added_at: datetime
    award_count: int  # 비교 기간 안
    last_award_at: datetime | None


class WatchedListOut(BaseModel):
    items: list[WatchedOut]
