"""관리자: 사용량·수집기 (SPEC §6.2, §5.8)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class UsageRow(BaseModel):
    day: date
    event: str
    requests: int
    g2b_calls: int
    llm_calls: int
    prompt_tokens: int
    completion_tokens: int
    hit_rate: dict[str, float | None]


class UsageOut(BaseModel):
    items: list[UsageRow]


class CollectorRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source: str
    mode: str
    window_from: datetime
    window_to: datetime
    status: str
    fetched: int
    inserted: int
    updated: int
    g2b_calls: int
    error: str | None
    started_at: datetime
    finished_at: datetime | None


class CoverageOut(BaseModel):
    source: str
    covered_from: datetime
    covered_to: datetime
    updated_at: datetime


class CollectorRunList(BaseModel):
    items: list[CollectorRunOut]
    coverage: list[CoverageOut]  # 소스별 수집 범위 (§7.9)


class CollectorRunIn(BaseModel):
    mode: Literal["incremental", "backfill"] = "incremental"
    source: Literal["regular", "prespec"]
    days: int = Field(default=7, ge=1, le=90)  # backfill에만 쓴다
