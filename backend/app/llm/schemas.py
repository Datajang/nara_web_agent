"""LLM 출력 스키마 (SPEC §8.4 그대로). AnalysisResult 필드 순서 = §7.5 화면 순서."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Requirement(BaseModel):
    text: str
    kind: Literal["functional", "technical", "staffing", "legal", "other"] = "other"
    evidence: str | None = None  # 원문 발췌 120자 이내
    source: str | None = None  # 근거 파일명


class EvalItem(BaseModel):
    name: str
    points: float | None = None  # 배점. 원문에 없으면 None
    note: str | None = None


class Evaluation(BaseModel):
    method: str | None = None  # 예: 협상에 의한 계약, 적격심사 (원문 표기)
    items: list[EvalItem] = []


class ScheduleItem(BaseModel):
    label: str  # 예: 제안서 제출 마감
    date: str | None = None  # YYYY-MM-DD, 알 수 없으면 None
    raw: str | None = None  # 원문 표기


class BudgetContract(BaseModel):
    budget_text: str | None = None  # 원문 표기 그대로
    contract_method: str | None = None
    payment_terms: str | None = None
    period: str | None = None


class FileFacts(BaseModel):
    doc_type: Literal["rfp", "spec", "other"] = "other"
    purpose: str | None = None
    scope: list[str] = []
    requirements: list[Requirement] = []
    evaluation: Evaluation = Evaluation()
    schedule: list[ScheduleItem] = []
    budget_contract: BudgetContract = BudgetContract()
    eligibility: list[str] = []
    risks: list[str] = []


class Coverage(BaseModel):
    files_read: int
    files_total: int
    truncated: bool = False
    warnings: list[str] = []


class BidSummaryDraft(BaseModel):  # reduce(summarize_bid) LLM 출력. CAPS는 BidSummary 이름으로
    model_config = ConfigDict(title="BidSummary")

    headline: str  # 80자 이내
    overview: str  # 3~5문장
    key_requirements: list[Requirement] = []
    evaluation: Evaluation = Evaluation()
    schedule: list[ScheduleItem] = []
    budget_contract: BudgetContract = BudgetContract()
    eligibility: list[str] = []
    risks: list[str] = []
    keywords: list[str] = []
    coverage: Coverage


class BidSummary(BidSummaryDraft):  # 저장·API 모양
    scope: list[
        str
    ] = []  # 과업 범위·주요 기능: 조각별 FileFacts.scope를 서버가 합침 (분석 입력, v10)


class ScoreItem(BaseModel):
    bid_id: str  # 예: b101
    score: int = Field(ge=0, le=100)
    reason: str  # 80자 이내 한 줄


class ScoreBatch(BaseModel):
    scores: list[ScoreItem]


class Risk(BaseModel):
    text: str
    severity: Literal["high", "mid", "low"] = "mid"
    source: str | None = None


class Understanding(BaseModel):  # 사업 이해 (v10)
    purpose: str  # 목적·배경
    scope: list[str] = []  # 과업 범위·주요 기능
    conditions: list[str] = []  # 수행 조건(산출물·투입 인력·기간). 금액·날짜는 요약 카드에


class Fit(BaseModel):
    score: int = Field(ge=0, le=100)
    verdict: Literal["strong", "possible", "weak"]
    reasoning: str


class TeamNeeds(BaseModel):  # 우리 팀에 필요한 것 (프로필에 적힌 사실만 근거)
    have: list[str] = []  # 이미 갖춘 것
    need: list[str] = []  # 보완할 것


class AnalysisOut(BaseModel):  # LLM 출력. 순서 = §7.5 화면 순서 (v10, 2026-11-16)
    understanding: Understanding
    fit: Fit
    team_needs: TeamNeeds
    profile_missing: list[str] = []  # 이 공고 판단에 필요한데 프로필에 없는 정보
    risks: list[Risk]
    next_actions: list[str]  # 다음 할 일 제안 (3~5개)
    warnings: list[str] = []


class AnalysisResult(AnalysisOut):  # 저장·API 모양
    profile_brief: bool = False  # 팀 소개가 짧아 간략 분석(서버가 정함)


class LegacyFit(BaseModel):
    score: int = Field(ge=0, le=100)
    verdict: Literal["strong", "possible", "weak"]
    strengths: list[str] = []
    gaps: list[str] = []
    reasoning: str


class LegacyAnalysisResult(BaseModel):  # v9 이하에 저장된 분석 (내 기록에서 계속 열림)
    overview: str
    requirements: list[Requirement]
    evaluation: Evaluation
    schedule: list[ScheduleItem]
    budget_contract: BudgetContract
    risks: list[Risk]
    fit: LegacyFit
    next_actions: list[str]
    warnings: list[str] = []


AnyAnalysis = AnalysisResult | LegacyAnalysisResult


class KeywordSuggestion(BaseModel):
    keywords: list[str] = Field(min_length=1, max_length=10)


class CompareExplain(BaseModel):
    """AI 해설 (§15.8). 입력은 GET /compare 응답뿐, 숫자는 입력에 있는 값만(서버가 검증)."""

    summary: str
    points: list[str] = []


def verdict_for(score: int) -> Literal["strong", "possible", "weak"]:
    """§8.4: verdict는 서버가 score에서 다시 계산한다."""
    if score >= 80:
        return "strong"
    return "possible" if score >= 60 else "weak"
