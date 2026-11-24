"""우리 투찰 결과(낙찰·탈락) 응답 모델 (P12, docs/decisions/2026-11-17-p12a-opening-ranks.md)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.api.schemas.competition import ParticipantOut


class MyBidOut(BaseModel):
    bid_ntce_no: str
    bid_ntce_ord: str
    bid_clsfc_no: str
    rbid_no: str
    title: str
    dminstt_name: str | None
    registered_at: datetime  # 낙찰 등록일시
    opened_at: datetime | None
    # won: 우리가 낙찰 / lost: 순위 있는 탈락 / disqualified: 순위 없음(부적격, 사유는 remark)
    result: Literal["won", "lost", "disqualified"]
    our_rank: int | None
    valid_count: int | None  # 순위 있는 업체 수. 개찰 결과를 안 불러왔으면 null
    participant_count: int | None  # 개찰 결과의 참가 업체 수, 없으면 낙찰 응답의 참가 수
    our_bid_amount: int | None
    our_bid_rate: float | None
    our_total_score: float | None
    remark: str | None  # 우리 행의 비고
    winner_bizno: str | None
    winner_name: str | None
    award_amount: int | None
    fetched: bool  # 개찰 결과를 불러온 공고인가
    bid_id: str | None  # bids에 있으면 b123
    # 공동수급에서 우리 역할(대표·구성원)과 지분(%). 구성원 낙찰도 result='won' (2026-11-24)
    our_role: Literal["lead", "member"] | None = None
    our_share: float | None = None


class MyBidCountsOut(BaseModel):
    all: int
    won: int
    lost: int  # 순위 있는 탈락 + 부적격


class OpeningScanOut(BaseModel):
    """개찰 결과 자동 수집 현황: 탈락 공고는 받은 공고 안에서만 보인다."""

    since: datetime | None  # 개찰 결과를 처음 받은 시각
    fetched_notices: int  # 개찰 결과를 받은 공고 수
    award_notices: int  # 수집된 낙찰 공고 수


class MyBidListOut(BaseModel):
    items: list[MyBidOut]
    next_cursor: str | None
    counts: MyBidCountsOut
    scan: OpeningScanOut


class MyBidParticipantOut(ParticipantOut):
    award_count: int  # 수집된 낙찰 수(경쟁사 정보 한 줄)


class MyBidDetailOut(BaseModel):
    item: MyBidOut
    estimated_price: int | None
    award_ratio: float | None
    g2b_award_rate: float | None
    is_joint: bool
    # null = 개찰 결과를 아직 못 불러옴(오늘 몫 소진·G2B 오류). 빈 목록 = 불러왔지만 0행
    participants: list[MyBidParticipantOut] | None
    budget_exhausted: bool
    failed: bool
