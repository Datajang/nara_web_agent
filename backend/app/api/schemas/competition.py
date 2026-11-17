"""공고 상세 '경쟁 구도' 응답 모델 (SPEC §15.6 GET /bids/{bidId}/competition, P11)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from app.api.schemas.awards import PeriodOut


class ParticipantOut(BaseModel):
    rank: int | None
    bizno: str
    name: str | None
    bid_amount: int | None  # 투찰금액
    bid_rate: float | None  # 투찰률(%)
    tech_score: float | None  # 기술평가
    price_score: float | None  # 가격평가
    total_score: float | None  # 총점
    remark: str | None = None  # 비고. 순위가 비면 부적격·탈락 사유(낙찰하한선 미달 등, P12)
    is_winner: bool
    is_us: bool


class CompetitionAwardOut(BaseModel):
    bid_ntce_no: str
    bid_ntce_ord: str
    title: str
    bizno: str | None
    winner_name: str | None
    award_amount: int | None
    g2b_award_rate: float | None
    award_ratio: float | None
    participant_count: int | None
    registered_at: datetime
    is_joint: bool
    bid_id: str | None  # bids에 있으면 b123
    similarity: float | None  # 이 공고와 공고명 비슷함(0~1+분야 가산). 이 공고 자체는 null
    participants: list[ParticipantOut] | None  # null = 개찰 결과를 아직 불러오지 않음
    us_participated: bool


class SpreadOut(BaseModel):
    n: int  # 값이 있는 건수
    min: float
    median: float
    max: float


class CompetitionDistributionOut(BaseModel):
    g2b_rate: SpreadOut | None  # 낙찰률(G2B, 예정가격 대비 %)
    award_ratio: SpreadOut | None  # 낙찰금액/추정가격(0~1)
    basis: int  # 분포를 낸 비슷한 낙찰 수


class ParticipantsStatusOut(BaseModel):
    requested: int  # 개찰 결과가 필요한 공고 수
    loaded: int  # 불러와 있는 공고 수
    fetched_now: int  # 이번 요청에서 새로 불러온 공고 수(최대 6)
    partial: bool  # '일부만 불러왔어요'
    failed: bool  # G2B 오류로 멈춤
    budget_exhausted: bool  # 오늘 낙찰 몫 호출 예산을 다 씀


class CompetitionUsOut(BaseModel):
    bizno: str
    name: str
    org_awards: int  # 이 수요기관에서 우리가 낙찰한 수(기간 안)
    participated: int  # 불러온 개찰 결과 중 이 수요기관 공고에 참가한 수
    won: int  # 그중 낙찰한 수


class CompetitionOrgOut(BaseModel):
    code: str | None
    name: str | None


class CompetitionOut(BaseModel):
    bid_id: str
    org: CompetitionOrgOut
    period: PeriodOut
    this_award: CompetitionAwardOut | None  # 이 공고가 이미 개찰·낙찰됐으면
    similar: list[CompetitionAwardOut]  # 같은 수요기관의 비슷한 과거 사업 낙찰(기본 5)
    similar_total: int  # 비슷한 낙찰 수(최대 50)
    distribution: CompetitionDistributionOut
    participants_status: ParticipantsStatusOut
    us: CompetitionUsOut | None  # 우리 회사 미설정이면 null
