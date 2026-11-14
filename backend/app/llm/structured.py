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
    # 2026-11-14: 0.2에서 같은 입력의 적합도가 최대 60점 흔들림 → 0 + 점수 기준표 (analyze_bid.md)
    "analyze_bid": TaskSpec(0.0, 3500),
    "suggest_keywords": TaskSpec(0.2, 300),
    "assistant": TaskSpec(0.3, 1500),
}


@dataclass(frozen=True)
class Cap:
    items: int | None = None  # 목록 최대 개수 (maxItems)
    chars: int | None = None  # 문자열(목록이면 각 원소) 최대 글자 수 (maxLength)
    pattern: str | None = None  # 문자열 형식 (정규식)
    enum: tuple[str, ...] | None = None  # 보기 중 하나만


# 모델에 보내는 스키마에만 거는 길이 상한 (2026-11-12 실측: summarize_file 실패 9/25건이
# 모두 4,000토큰에서 잘린 JSON). vLLM 강제 디코딩이 maxItems·maxLength를 지키므로 꽉 채운
# 최악의 출력도 max_tokens 안에 든다(tests/unit/test_llm_structured.py). Pydantic 검증·API
# 스키마는 그대로라 저장된 값은 길어도 읽힌다. 키는 '모델명.필드명', 공통 부품은 분석에도 적용.
# 계약(낙찰) 방식 보기 (2026-11-13: 칸 혼동으로 대금 조건·장비명이 들어감).
# 원문에 없는 보기는 원문 대조(pipeline/grounding.py)에서 비운다
CONTRACT_METHODS = (
    "협상에 의한 계약",
    "적격심사",
    "최저가",
    "2단계 경쟁",
    "규격·가격 동시입찰",
    "종합심사",
    "수의계약",
)

# 평가(낙찰자 결정) 방식 보기 (2026-11-13 v5: 분석 기법명 'Atera in situ'가 들어감).
# 원문 대조는 계약 방식과 같다
EVAL_METHODS = (*CONTRACT_METHODS, "종합평가")

CAPS: dict[str, Cap] = {
    "Requirement.text": Cap(chars=80),
    "Requirement.evidence": Cap(chars=100),  # §8.5 '120자 이내' 안
    "Requirement.source": Cap(chars=30),
    "EvalItem.name": Cap(chars=30),
    "EvalItem.note": Cap(chars=40),
    "Evaluation.method": Cap(chars=20, enum=EVAL_METHODS),
    "Evaluation.items": Cap(items=10),
    "ScheduleItem.label": Cap(chars=30),
    # 날짜가 아니면 null (2026-11-12 예시: '협상 후' 같은 글이 들어가 마감일 추출 0/16)
    "ScheduleItem.date": Cap(chars=10, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    "ScheduleItem.raw": Cap(chars=40),
    "BudgetContract.budget_text": Cap(chars=80),
    "BudgetContract.contract_method": Cap(chars=20, enum=CONTRACT_METHODS),
    "BudgetContract.payment_terms": Cap(chars=80),
    "BudgetContract.period": Cap(chars=80),
    "FileFacts.purpose": Cap(chars=150),
    "FileFacts.scope": Cap(items=5, chars=60),
    "FileFacts.requirements": Cap(items=8),
    "FileFacts.schedule": Cap(items=8),
    "FileFacts.eligibility": Cap(items=5, chars=80),
    "FileFacts.risks": Cap(items=4, chars=80),
    "BidSummary.headline": Cap(chars=80),  # §8.5
    "BidSummary.overview": Cap(chars=300),
    "BidSummary.key_requirements": Cap(items=8),
    "BidSummary.schedule": Cap(items=8),
    "BidSummary.eligibility": Cap(items=4, chars=80),
    "BidSummary.risks": Cap(items=4, chars=80),
    "BidSummary.keywords": Cap(items=10, chars=20),
    "Coverage.warnings": Cap(items=3, chars=60),
}


def _branch(prop: dict[str, Any], type_: str) -> dict[str, Any] | None:
    if prop.get("type") == type_:
        return prop
    return next((b for b in prop.get("anyOf", []) if b.get("type") == type_), None)


def _apply_caps(node: Any) -> None:
    """Pydantic 스키마(사본)의 각 모델 노드에 CAPS를 단다."""
    if isinstance(node, list):
        for v in node:
            _apply_caps(v)
        return
    if not isinstance(node, dict):
        return
    props = node.get("properties")
    if isinstance(props, dict):
        for name, prop in props.items():
            cap = CAPS.get(f"{node.get('title')}.{name}")
            if cap is None:
                continue
            arr = _branch(prop, "array")
            if cap.items is not None and arr is not None:
                arr["maxItems"] = cap.items
            text = _branch(arr["items"], "string") if arr is not None else _branch(prop, "string")
            if cap.chars is not None and text is not None:
                text["maxLength"] = cap.chars
            if cap.pattern is not None and text is not None:
                text["pattern"] = cap.pattern
            if cap.enum is not None and text is not None:
                text["enum"] = list(cap.enum)
    for v in node.values():
        _apply_caps(v)


def model_schema(schema: type[BaseModel]) -> dict[str, Any]:
    """모델에 보낼 json_schema: 길이 상한(CAPS)을 달고 모든 필드를 required로."""
    js = strict_schema(schema.model_json_schema())
    _apply_caps(js)
    return js


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
    js = model_schema(schema)
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
            log.warning(
                "llm.invalid_output task=%s attempt=%d finish=%s",
                task,
                attempt + 1,
                out.finish_reason,
            )
            if out.finish_reason == "length":
                # 잘린 출력은 고칠 수 없다: 되돌려 보내지 않고 처음부터 더 짧게 쓰게 한다
                msgs = [
                    *messages,
                    {
                        "role": "user",
                        "content": "앞선 답이 출력 길이 제한에 걸려 잘렸습니다. 목록은 중요한 것만 "
                        "남기고 문장은 짧게 줄여, 스키마에 맞는 JSON 전체를 다시 출력하세요.",
                    },
                ]
                continue
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
