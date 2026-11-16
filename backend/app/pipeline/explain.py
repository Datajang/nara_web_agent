"""비교 AI 해설 (SPEC §15.8). 입력은 GET /compare 응답 JSON뿐, 출력은 {summary, points}.

1. 구조화 출력(json_schema + repair 1회, structured.generate)
2. 숫자 검증(analysis.explain_check): 모든 숫자가 입력에 있어야 하고 권유·예측 표현이 없어야 한다
3. 실패하면 문제가 된 숫자·표현과 그 문장을 보여 주고 한 번 다시 만든다
4. 그래도 실패하면: 요약은 깨끗하고 걸린 것이 points 일부뿐이며 깨끗한 point가 2개 이상 남으면
   그 point만 빼고 보여 준다(공식 사실 원칙의 '그 문장만 뺀다'와 같음, 2026-11-16 실제 모델에서
   목록 개수를 세는 문장 하나 때문에 해설 전체가 버려짐). 아니면 해설 없이(None) — 화면은 표만.
   어느 쪽이든 사용자에게 나가는 숫자는 모두 입력에 있다(수용 기준 6)
"""

from __future__ import annotations

import json
import logging
import re
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
    first_rejected: list[str] = field(default_factory=list)  # 첫 시도에서 걸린 것(평가용)
    last: CompareExplain | None = None  # 검증에 걸린 마지막 글(사용자에게 안 나감, 평가·로그용)
    trimmed: int = 0  # 마지막에 뺀 point 수


def model_input(compare: dict[str, Any]) -> dict[str, Any]:
    """비교 응답에서 화면 상태를 빼고, 기간은 실제로 센 범위만 남긴다.

    요청 기간(from·to, 기본 5년)을 주면 수집이 30일뿐이어도 '2021년부터'라고 쓴다
    (2026-11-16 실제 모델). 센 범위(counted_from~counted_to)만 주어 오해를 막는다.
    """
    out = {k: v for k, v in compare.items() if k not in _DROP}
    period = out.get("period")
    if isinstance(period, dict):
        out["period"] = {
            k: period.get(k) for k in ("counted_from", "counted_to", "collecting") if k in period
        }
    return out


_UNIT_GAP = re.compile(r"(\d)\s+(?=(?:건|곳|개|원|년|월|일|회|억|천만|백만|만|천|%))")


def tidy(text: str) -> str:
    """'14 건', '2026 년' → '14건', '2026년'. 숫자 값은 바꾸지 않는다(실제 모델이 띄어 씀)."""
    return _UNIT_GAP.sub(r"\1", text)


def problems(out: CompareExplain, payload: dict[str, Any]) -> list[str]:
    texts = [out.summary, *out.points]
    return [*unsupported(texts, payload), *banned_phrases(texts)]


MIN_POINTS = 2


def trim(out: CompareExplain, payload: dict[str, Any]) -> CompareExplain | None:
    """걸린 point만 뺀 해설. 요약이 걸렸거나 깨끗한 point가 MIN_POINTS개 미만이면 None."""
    if problems(CompareExplain(summary=out.summary), payload):
        return None
    clean = [p for p in out.points if not problems(CompareExplain(summary="", points=[p]), payload)]
    return CompareExplain(summary=out.summary, points=clean) if len(clean) >= MIN_POINTS else None


def retry_message(out: CompareExplain, bad: list[str]) -> str:
    """걸린 숫자·표현과 그 문장을 보여 준다. 숫자만 알려 주면 실제 모델이 같은 문장을 다시 쓴다."""
    lines = [s for s in (out.summary, *out.points) if any(b in s for b in bad)]
    quoted = "\n".join(f"- {s}" for s in lines[:5])
    return (
        f"위 해설에 입력 JSON에 없는 숫자나 쓰면 안 되는 표현이 있습니다: {', '.join(bad[:10])}\n"
        f"문제가 된 문장:\n{quoted}\n"
        "이 문장들은 입력에 있는 숫자만 그대로 쓰도록 고치거나 빼세요. 목록의 개수를 세거나 "
        "차이·비율을 계산한 숫자, 권유·예측은 쓰지 않습니다. 같은 형식의 JSON만 다시 출력하세요."
    )


async def explain(llm: LLMClient, compare: dict[str, Any]) -> ExplainResult:
    payload = model_input(compare)
    base = render(TASK, compare_json=json.dumps(payload, ensure_ascii=False, indent=1))
    messages: list[Message] = list(base)
    bad: list[str] = []
    first: list[str] = []
    for attempt in range(1, MAX_ATTEMPTS + 1):
        out = await generate(llm, TASK, messages, CompareExplain)
        bad = problems(out, payload)
        if attempt == 1:
            first = bad
        if not bad:
            out = CompareExplain(summary=tidy(out.summary), points=[tidy(x) for x in out.points])
            return ExplainResult(out, attempt, first_rejected=first)
        log.info("compare_explain: 검증 실패 attempt=%d 항목=%d", attempt, len(bad))
        messages = [
            *base,
            {"role": "assistant", "content": out.model_dump_json()},
            {"role": "user", "content": retry_message(out, bad)},
        ]
    kept = trim(out, payload)
    if kept is not None:
        shown = CompareExplain(summary=tidy(kept.summary), points=[tidy(x) for x in kept.points])
        removed = len(out.points) - len(kept.points)
        log.info("compare_explain: 걸린 point %d개를 빼고 보여 줌", removed)
        return ExplainResult(shown, MAX_ATTEMPTS, bad, first, last=out, trimmed=removed)
    return ExplainResult(None, MAX_ATTEMPTS, bad, first, last=out)
