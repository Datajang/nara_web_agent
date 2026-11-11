"""LLM 출력 스키마 (SPEC §8.4 그대로). AnalysisResult 필드 순서 = §7.5 화면 순서."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


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


class BidSummary(BaseModel):
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


class Fit(BaseModel):
    score: int = Field(ge=0, le=100)
    verdict: Literal["strong", "possible", "weak"]
    strengths: list[str] = []
    gaps: list[str] = []
    reasoning: str


class AnalysisResult(BaseModel):  # 순서 = 7.5 화면 순서
    overview: str  # 사업 개요
    requirements: list[Requirement]  # 핵심 요구사항
    evaluation: Evaluation  # 평가 기준·배점
    schedule: list[ScheduleItem]  # 일정
    budget_contract: BudgetContract  # 예산·계약 조건
    risks: list[Risk]  # 리스크·유의사항
    fit: Fit  # 우리 팀 적합도
    next_actions: list[str]  # 다음 할 일 제안 (3~5개)
    warnings: list[str] = []


class KeywordSuggestion(BaseModel):
    keywords: list[str] = Field(min_length=1, max_length=10)


def verdict_for(score: int) -> Literal["strong", "possible", "weak"]:
    """§8.4: verdict는 서버가 score에서 다시 계산한다."""
    if score >= 80:
        return "strong"
    return "possible" if score >= 60 else "weak"
