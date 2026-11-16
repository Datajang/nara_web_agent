"""SSE 이벤트 모양 (SPEC §6.4). OpenAPI 컴포넌트로 내보내 프론트 타입을 만든다."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field

from app.bids.cards import BidCard
from app.llm.schemas import AnyAnalysis, CompareExplain

Stage = Literal["search", "files", "extract", "summarize", "analyze", "score", "explain"]


class Progress(BaseModel):
    done: int
    total: int


class StatusEvent(BaseModel):
    type: Literal["status"]
    stage: Stage
    message: str
    progress: Progress | None = None
    cache: bool | None = None
    expected_s: int | None = None  # 분석 단계 예상 시간(초), 로딩바용 (summarize·analyze)
    waiting: bool | None = None  # 다른 요청이 같은 작업을 처리 중이라 기다리는 중


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
    analysis: AnyAnalysis
    markdown: str
    from_cache: bool


class ExplainEvent(BaseModel):
    """비교 AI 해설 (§15.8). explanation=null이면 숫자 검증에 두 번 실패해 해설 없이 표만."""

    type: Literal["explain"]
    explanation: CompareExplain | None
    verified: bool  # 해설의 모든 숫자가 입력(비교 표)에 있음


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
    StatusEvent
    | TokenEvent
    | CardsEvent
    | ResultEvent
    | ExplainEvent
    | ActionEvent
    | ErrorEvent
    | DoneEvent,
    Field(discriminator="type"),
]
EVENT_MODELS = (
    StatusEvent,
    TokenEvent,
    CardsEvent,
    ResultEvent,
    ExplainEvent,
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
