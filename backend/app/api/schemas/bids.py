"""공고 검색·상세·분석·추천 요청·응답 (SPEC §6.2, §6.3)."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from app.bids.cards import BidCard
from app.bids.facts import DocBudget, OfficialFacts
from app.llm.schemas import BidSummary
from app.search.query import Keyword, SearchQuery

__all__ = [
    "BidCard",
    "SearchQuery",
    "SearchResultOut",
    "FileOut",
    "BidDetail",
    "FileTextOut",
    "LookupOut",
    "AnalyzeIn",
    "RecommendIn",
]


class SearchResultOut(BaseModel):
    run_id: int
    data_as_of: datetime | None
    incomplete: bool
    collecting: bool  # 커버리지 밖이라 백그라운드 수집 중 (P1 결정 '수집 중')
    from_cache: bool
    total: int
    truncated: bool
    items: list[BidCard]


class FileOut(BaseModel):
    file_id: int
    name: str
    kind: Literal["rfp", "spec", "other"]
    status: Literal["new", "ok", "failed", "unsupported"]


class BidDetail(BidCard):
    prespec_reg_no: str | None
    related_bid_id: str | None  # 같은 사전규격 등록번호로 이어지는 다른 구분의 공고 (§7.5)
    files: list[FileOut]
    summary: BidSummary | None
    my_analysis_id: int | None
    team_analysis_id: int | None = None  # 팀 프로필로 만든 팀원의 최근 분석 (§13 P6)
    official: OfficialFacts  # G2B 공고 정보 그대로 (AI를 거치지 않음, §7.5-3)
    doc_budgets: list[DocBudget] = []  # 첨부 문서의 사업 금액 중 G2B 값과 다른 것


class FileTextOut(BaseModel):
    file_id: int
    name: str
    text: str
    char_count: int
    truncated: bool


class LookupOut(BaseModel):
    bid_id: str


class AnalyzeIn(BaseModel):
    profile_id: int


class RecommendIn(BaseModel):
    profile_id: int
    days: int = Field(default=14, ge=1, le=90)
    source: Literal["regular", "prespec", "all"] = "all"
    top_n: int = Field(default=20, ge=1, le=50)
    keywords: Annotated[list[Keyword], Field(max_length=10)] | None = None
