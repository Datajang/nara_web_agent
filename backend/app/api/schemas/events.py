"""SSE 이벤트 모양 (SPEC §6.4). OpenAPI 컴포넌트로 내보내 프론트 타입을 만든다."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field

from app.bids.cards import BidCard
from app.llm.schemas import AnalysisResult

Stage = Literal["search", "files", "extract", "summarize", "analyze", "score"]


class Progress(BaseModel):
    done: int
    total: int


class StatusEvent(BaseModel):
    type: Literal["status"]
    stage: Stage
    message: str
    progress: Progress | None = None
    cache: bool | None = None


class TokenEvent(BaseModel):
    type: Literal["token"]
    text: str


class CardsEvent(BaseModel):
    type: Literal["cards"]
    items: list[BidCard]
    run_id: int | None = None


class ResultEvent(BaseModel):
    type: Literal["result"]
    analysis_id: int
    analysis: AnalysisResult
    markdown: str
    from_cache: bool


class ActionEvent(BaseModel):
    type: Literal["action"]
    name: Literal["open_tab", "prefill_search"]
    params: dict[str, Any]


class ErrorEvent(BaseModel):
    type: Literal["error"]
    code: str
    message: str


class Usage(BaseModel):
    llm_calls: int
    g2b_calls: int
    cache: dict[str, bool]


class DoneEvent(BaseModel):
    type: Literal["done"]
    message_id: int | None = None
    usage: Usage


SseEvent = Annotated[
    StatusEvent | TokenEvent | CardsEvent | ResultEvent | ActionEvent | ErrorEvent | DoneEvent,
    Field(discriminator="type"),
]
EVENT_MODELS = (
    StatusEvent,
    TokenEvent,
    CardsEvent,
    ResultEvent,
    ActionEvent,
    ErrorEvent,
    DoneEvent,
)
SSE_RESPONSES: dict[int | str, dict[str, Any]] = {
    200: {
        "description": "SSE 스트림 (§6.4). 각 이벤트는 SseEvent 중 하나",
        "content": {"text/event-stream": {"schema": {"$ref": "#/components/schemas/SseEvent"}}},
    }
}
