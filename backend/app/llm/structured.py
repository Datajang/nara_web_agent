"""구조화 출력 생성: json_schema 강제 + Pydantic 검증 + repair 1회 (SPEC §8.1-1).

호출 종류별 온도·최대 출력 토큰은 §8.1 표를 따른다.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from app.llm import usage
from app.llm.base import LLMClient, LLMInvalidOutput, Message

log = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)


@dataclass(frozen=True)
class TaskSpec:
    temperature: float
    max_tokens: int


TASKS: dict[str, TaskSpec] = {
    "summarize_file": TaskSpec(0.1, 4000),  # §8.3 출력 예산 (2026-11-12, strict 스키마)
    "summarize_bid": TaskSpec(0.1, 4000),
    "score_bids": TaskSpec(0.1, 1500),
    "analyze_bid": TaskSpec(0.2, 3500),
    "suggest_keywords": TaskSpec(0.2, 300),
    "assistant": TaskSpec(0.3, 1500),
}


def strict_schema(node: Any) -> Any:
    """모델에 보낼 스키마: 모든 object의 모든 필드를 required로 (사본).

    기본값 있는 필드가 선택이면 json_schema 강제 디코딩에서 모델이 필드를 통째로 빼먹는다
    (2026-11-12 골든셋, docs/decisions/2026-11-12-p3a2-real-llm.md). null·빈 목록은 그대로 허용된다.
    """
    if isinstance(node, list):
        return [strict_schema(v) for v in node]
    if not isinstance(node, dict):
        return node
    out = {k: strict_schema(v) for k, v in node.items()}
    if isinstance(out.get("properties"), dict):
        out["required"] = list(out["properties"])
    return out


def _parse(text: str, schema: type[T]) -> T:
    s = text.strip()
    if s.startswith("```"):  # 코드 펜스로 감싼 경우만 벗긴다
        s = s.strip("`").removeprefix("json").strip()
    return schema.model_validate(json.loads(s))


async def generate(llm: LLMClient, task: str, messages: list[Message], schema: type[T]) -> T:
    spec = TASKS[task]
    js = strict_schema(schema.model_json_schema())
    msgs = list(messages)
    for attempt in range(2):
        out = await llm.complete(
            task, msgs, json_schema=js, temperature=spec.temperature, max_tokens=spec.max_tokens
        )
        usage.record_llm(out.prompt_tokens, out.completion_tokens)
        try:
            return _parse(out.text, schema)
        except (ValueError, ValidationError) as e:
            err = str(e)[:800]
            log.warning("llm.invalid_output task=%s attempt=%d", task, attempt + 1)
            msgs = [
                *messages,
                {"role": "assistant", "content": out.text[:4000]},
                {
                    "role": "user",
                    "content": "위 출력이 JSON 스키마 검증에 실패했습니다. 오류를 고쳐 "
                    f"스키마에 맞는 JSON만 다시 출력하세요.\n오류: {err}",
                },
            ]
    raise LLMInvalidOutput(task)
