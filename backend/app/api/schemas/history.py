"""내 기록(검색 기록·분석 기록·북마크)과 피드백 (SPEC §6.2)."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, StringConstraints

from app.bids.cards import BidCard
from app.llm.schemas import AnalysisResult


class SearchRunOut(BaseModel):
    id: int
    kind: Literal["search", "recommend"]
    profile_id: int | None
    query: dict[str, Any]
    result_count: int
    data_as_of: datetime | None
    from_cache: bool
    created_at: datetime


class SearchRunList(BaseModel):
    items: list[SearchRunOut]
    total: int


class SearchRunDetail(SearchRunOut):
    items: list[BidCard]
    offset: int
    limit: int


class AnalysisSummaryOut(BaseModel):
    analysis_id: int
    bid: BidCard
    profile_id: int | None
    profile_name: str | None  # 프로필을 지웠으면 null (§7.7)
    fit_score: int
    verdict: Literal["strong", "possible", "weak"]
    created_at: datetime


class AnalysisList(BaseModel):
    items: list[AnalysisSummaryOut]
    total: int


class AnalysisDetail(BaseModel):
    analysis_id: int
    bid_id: str
    profile_id: int | None
    analysis: AnalysisResult
    markdown: str
    created_at: datetime


class BookmarkIn(BaseModel):
    note: Annotated[str, StringConstraints(max_length=1000)] = ""
    analysis_id: int | None = None


class BookmarkOut(BaseModel):
    bid: BidCard
    note: str
    analysis_id: int | None
    created_at: datetime


class BookmarkList(BaseModel):
    items: list[BookmarkOut]


class FeedbackIn(BaseModel):
    target_type: Literal["analysis", "assistant_message", "search_run"]
    target_id: int
    rating: Literal[-1, 1]
    comment: Annotated[str, StringConstraints(max_length=1000)] | None = None


class FeedbackOut(BaseModel):
    id: int


class KeywordsIn(BaseModel):
    description: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)
    ]


class KeywordsOut(BaseModel):
    keywords: list[str] = Field(max_length=10)
