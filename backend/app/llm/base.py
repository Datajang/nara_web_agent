"""LLM 인터페이스 (SPEC §8). 실제 구현은 client.py(vLLM), 테스트·개발은 fake.py.

구조화 출력의 검증·repair는 structured.py가 맡고, 클라이언트는 원문 텍스트만 돌려준다.
그래서 가짜 LLM으로도 실제 repair 경로를 시험할 수 있다.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Protocol

Message = dict[str, Any]


class LLMError(Exception):
    """LLM 호출 실패의 공통 부모."""


class LLMUnavailable(LLMError):
    """서버 불가·타임아웃·재시도 소진 (§8.7). API는 503 llm_unavailable."""


class LLMContextTooLong(LLMError):
    """컨텍스트 초과(400). 호출자가 청크를 절반으로 줄여 1회 재시도한다 (§8.7)."""


class LLMInvalidOutput(LLMError):
    """repair 1회 뒤에도 스키마 검증 실패."""


@dataclass
class Completion:
    text: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    finish_reason: str = "stop"  # 'length'면 max_tokens에서 잘림


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: str  # 모델이 만든 JSON 문자열(파싱 전)


@dataclass
class TextDelta:
    text: str


@dataclass
class ToolCalls:
    calls: list[ToolCall] = field(default_factory=list)


@dataclass
class StreamUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0


StreamEvent = TextDelta | ToolCalls | StreamUsage


class LLMClient(Protocol):
    model_id: str  # PROMPT_VERSION 접미사·캐시 키에 쓰는 모델 식별자 (예: q35-9b)

    async def complete(
        self,
        task: str,
        messages: list[Message],
        *,
        json_schema: dict[str, Any] | None,
        temperature: float,
        max_tokens: int,
    ) -> Completion: ...

    def chat_stream(
        self,
        messages: list[Message],
        *,
        tools: list[dict[str, Any]],
        tool_choice: str,
        temperature: float,
        max_tokens: int,
    ) -> AsyncIterator[StreamEvent]: ...

    async def health(self) -> bool: ...
