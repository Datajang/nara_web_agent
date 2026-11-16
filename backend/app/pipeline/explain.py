"""비교 AI 해설 (SPEC §15.8). 입력은 GET /compare 응답 JSON뿐, 출력은 {summary, points}.

1. 구조화 출력(json_schema + repair 1회, structured.generate)
2. 숫자 검증(analysis.explain_check): 모든 숫자가 입력에 있어야 하고 권유·예측 표현이 없어야 한다
3. 실패하면 어떤 숫자·표현이 문제인지 알려 주고 한 번 다시 만든다
4. 그래도 실패하면 해설 없이(None) — 화면은 표만 보여 준다(수용 기준 6)
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from app.analysis.explain_check import banned_phrases, unsupported
from app.llm.base import LLMClient, Message
from app.llm.prompts import render
from app.llm.schemas import CompareExplain
from app.llm.structured import generate

log = logging.getLogger(__name__)
TASK = "compare_explain"
MAX_ATTEMPTS = 2
# 모델에 주지 않는 필드: 화면 상태(관심 경쟁사)
_DROP = ("watched",)


@dataclass
class ExplainResult:
    explanation: CompareExplain | None
    attempts: int
    rejected: list[str] = field(default_factory=list)  # 마지막 시도에서 걸린 숫자·표현


def model_input(compare: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in compare.items() if k not in _DROP}


def problems(out: CompareExplain, payload: dict[str, Any]) -> list[str]:
    texts = [out.summary, *out.points]
    return [*unsupported(texts, payload), *banned_phrases(texts)]


async def explain(llm: LLMClient, compare: dict[str, Any]) -> ExplainResult:
    payload = model_input(compare)
    base = render(TASK, compare_json=json.dumps(payload, ensure_ascii=False, indent=1))
    messages: list[Message] = list(base)
    bad: list[str] = []
    for attempt in range(1, MAX_ATTEMPTS + 1):
        out = await generate(llm, TASK, messages, CompareExplain)
        bad = problems(out, payload)
        if not bad:
            return ExplainResult(out, attempt)
        log.info("compare_explain: 검증 실패 attempt=%d 항목=%d", attempt, len(bad))
        messages = [
            *base,
            {"role": "assistant", "content": out.model_dump_json()},
            {
                "role": "user",
                "content": "위 해설에 입력 JSON에 없는 숫자나 쓰면 안 되는 표현이 있습니다: "
                f"{', '.join(bad[:10])}. 입력에 있는 숫자만 그대로 쓰고, 계산한 숫자·권유·예측을 "
                "빼서 같은 형식의 JSON만 다시 출력하세요.",
            },
        ]
    return ExplainResult(None, MAX_ATTEMPTS, bad)
