"""LLM 인터페이스. P1은 캐시 계약 검증용 최소 형태, P3에서 §8 클라이언트로 확장한다."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass
class LLMResult:
    data: dict[str, Any]
    prompt_tokens: int = 0
    completion_tokens: int = 0


class LLMClient(Protocol):
    model_id: str

    async def complete_json(self, task: str, payload: dict[str, Any]) -> LLMResult: ...
