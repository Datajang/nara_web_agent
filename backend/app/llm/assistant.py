"""어시스턴트 도구 호출 루프 (SPEC §8.6). 도구는 읽기 전용이고 실제 실행은 execute 콜백이 맡는다.

규칙
1. 입력: 시스템 프롬프트(프로필 앞 500자) + 최근 12개 메시지 + 이번 질문.
2. 라운드 최대 4번. 같은 도구·같은 인자 반복은 차단, 마지막 라운드는 tool_choice='none'.
3. 한 라운드의 여러 도구 호출은 순서대로 실행.
4. 도구 결과는 <tool_result>로 감싸 압축해서 모델에 준다(도구 쪽에서 20건·URL 없음·토큰 상한).
5. ID 검증: 이번 턴 도구 결과에 나온 b-ID만 남기고, 나머지는 스트리밍 중에 지운다(IdFilter).
   카드도 남은 ID로만 만든다. 지운 ID는 warnings로 messages.parts에 남긴다.
6. 텍스트 조각만 token으로 내보내고 도구 인자·결과는 클라이언트로 보내지 않는다.
7. 도구 호출을 해석하지 못하면 도구 없이 답하게 하고 검색 탭 안내 문장을 덧붙인다.
8. 낙찰·경쟁사 도구(§15.8)를 쓴 뒤의 답은 스트리밍하지 않고 모아 두었다가 숫자를 도구 결과와
   대조한다(explain_check, 해설과 같은 검증기). 맞으면 그대로 내보내고, 틀리면 문제 문장을 보여 주고
   한 번 다시 만든다. 그래도 틀리면 걸린 문장만 빼고 안내를 붙인다(남는 게 없으면 고정 안내).
   틀린 숫자는 화면에 나가지 않는다 (2026-11-16 실제 모델: 억 단위 변환 오류·'2배' 같은 계산,
   2026-11-17 사용자 결정으로 안내만 붙이던 방식을 바꿈).
"""

from __future__ import annotations

import json
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from app.analysis.explain_check import (
    keep_supported,
    multipliers,
    strip_tool_text,
    tidy,
    unsupported,
)
from app.llm import usage
from app.llm.base import LLMClient, Message, StreamUsage, TextDelta, ToolCall, ToolCalls
from app.llm.prompts import fence, system_text
from app.llm.structured import TASKS

MAX_ROUNDS = 4
HISTORY = 12
PROFILE_CHARS = 500
FALLBACK_HINT = "도구를 쓰지 못해 일반 답변으로 대신했어요. 정확한 공고는 검색 탭에서 찾아 주세요."
NUMBER_HINT = (
    "※ 조회 결과와 맞는지 확인되지 않은 숫자가 있는 문장은 뺐어요. "
    "정확한 값은 '업체 검색'·'경쟁사' 화면에서 확인해 주세요."
)
NUMBER_FAILED = (
    "조회 결과와 맞는 숫자로 답을 만들지 못했어요. 정확한 값은 '업체 검색'·'경쟁사' 화면에서 "
    "확인해 주세요."
)
CHECK_STATUS = "답을 만들고 숫자를 조회 결과와 맞춰 보고 있어요"
NUMBER_CHECKED = frozenset({"search_companies", "get_company_awards", "compare_companies"})
_REF = re.compile(r"(\[)?(?<![A-Za-z0-9])b(\d+)(?![0-9])(?(1)\]|)")
_TAIL = re.compile(r"(\[?(?<![A-Za-z0-9])b\d*|\[)$")


def _schema(name: str, desc: str, props: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": desc,
            "parameters": {"type": "object", "properties": props, "required": required},
        },
    }


_SOURCE = {"type": "string", "enum": ["regular", "prespec", "all"]}
TOOLS: list[dict[str, Any]] = [
    _schema(
        "search_bids",
        "DB에 수집된 나라장터 공고를 제목 키워드로 검색한다",
        {
            "keywords": {"type": "array", "items": {"type": "string"}, "maxItems": 10},
            "match": {"type": "string", "enum": ["all", "any"]},
            "source": _SOURCE,
            "days": {"type": "integer", "minimum": 1, "maximum": 90},
            "status": {"type": "string", "enum": ["open", "all"]},
            "budget_min": {"type": "integer"},
            "budget_max": {"type": "integer"},
            "org": {"type": "string"},
            "sort": {"type": "string", "enum": ["notice_desc", "deadline_asc", "budget_desc"]},
            "limit": {"type": "integer", "minimum": 1, "maximum": 20},
        },
        [],
    ),
    _schema(
        "get_bid",
        "공고 하나의 메타와 (있으면) 요약을 본다",
        {"bid_id": {"type": "string"}},
        ["bid_id"],
    ),
    _schema(
        "analyze_bid",
        "대화의 프로필로 공고를 상세 분석한다",
        {"bid_id": {"type": "string"}},
        ["bid_id"],
    ),
    _schema(
        "recommend_bids",
        "대화의 프로필로 맞춤 공고를 추천한다",
        {
            "days": {"type": "integer", "minimum": 1, "maximum": 90},
            "source": _SOURCE,
            "top_n": {"type": "integer", "minimum": 1, "maximum": 10},
        },
        [],
    ),
    _schema("list_bookmarks", "내 북마크 목록을 본다", {}, []),
    _schema(
        "search_companies",
        "수집된 나라장터 낙찰에서 업체를 찾는다(업체명 두 글자 이상 또는 사업자번호 10자리)",
        {"q": {"type": "string", "maxLength": 100}},
        ["q"],
    ),
    _schema(
        "get_company_awards",
        "업체의 낙찰 요약과 최근 낙찰 목록을 본다. 업체는 bizno(사업자번호) 또는 name(업체명). "
        "둘 다 빼면 우리 회사",
        {
            "bizno": {"type": "string", "pattern": "^[0-9]{10}$"},
            "name": {"type": "string", "maxLength": 100},
            "limit": {"type": "integer", "minimum": 1, "maximum": 20},
        },
        [],
    ),
    _schema(
        "compare_companies",
        "우리 회사(설정돼 있어 따로 주지 않음)와 다른 업체의 낙찰을 비교한 항목별 판정"
        "(규칙으로 계산)을 본다. 상대 업체는 bizno(사업자번호) 또는 name(업체명)",
        {
            "bizno": {"type": "string", "pattern": "^[0-9]{10}$"},
            "name": {"type": "string", "maxLength": 100},
        },
        [],
    ),
    _schema(
        "navigate",
        "화면 탭을 연다(데이터는 바꾸지 않음)",
        {
            "tab": {"type": "string", "enum": ["search", "recommend", "library", "settings"]},
            "params": {"type": "object"},
        },
        ["tab"],
    ),
]
TOOL_NAMES = {t["function"]["name"] for t in TOOLS}
STAGE = {"search_bids": "search", "recommend_bids": "score", "analyze_bid": "analyze"}
STATUS_TEXT = {
    "search_bids": "공고를 찾고 있어요",
    "get_bid": "공고 정보를 확인하고 있어요",
    "analyze_bid": "공고를 분석하고 있어요",
    "recommend_bids": "맞춤 공고를 고르고 있어요",
    "list_bookmarks": "북마크를 확인하고 있어요",
    "search_companies": "업체를 찾고 있어요",
    "get_company_awards": "낙찰 현황을 확인하고 있어요",
    "compare_companies": "두 회사의 낙찰을 비교하고 있어요",
    "navigate": "화면을 준비하고 있어요",
}


class IdFilter:
    """스트리밍 텍스트에서 허용되지 않은 b-ID 참조를 지운다.

    조각 경계에 걸친 ID(예: "b1" + "23")는 다음 조각이 올 때까지 내보내지 않는다.
    """

    def __init__(self, allowed: set[int]) -> None:
        self.allowed = allowed
        self.removed: list[str] = []
        self._buf = ""

    def _clean(self, text: str) -> str:
        def repl(m: re.Match[str]) -> str:
            if int(m.group(2)) in self.allowed:
                return m.group(0)
            ref = f"b{m.group(2)}"
            if ref not in self.removed:
                self.removed.append(ref)
            return ""

        return _REF.sub(repl, text)

    def feed(self, text: str) -> str:
        self._buf += text
        m = _TAIL.search(self._buf)
        cut = m.start() if m else len(self._buf)
        ready, self._buf = self._buf[:cut], self._buf[cut:]
        return self._clean(ready)

    def flush(self) -> str:
        ready, self._buf = self._buf, ""
        return self._clean(ready)


@dataclass
class ToolOutcome:
    text: str  # 모델에 줄 결과(JSON). URL 없음
    bid_ids: list[int] = field(default_factory=list)
    summary: str = ""  # messages.parts에 남길 한 줄
    action: dict[str, Any] | None = None


class ToolArgError(ValueError):
    """인자 검증 실패. 모델에 오류를 돌려줘 고치게 한다."""


ToolExec = Callable[[str, dict[str, Any]], Awaitable[ToolOutcome]]
Emit = Callable[[dict[str, Any]], None]


@dataclass
class TurnResult:
    content: str
    card_ids: list[int]
    warnings: list[str]
    tool_log: list[dict[str, Any]]
    actions: list[dict[str, Any]]


def _tool_message(call_id: str, payload: str) -> Message:
    return {
        "role": "tool",
        "tool_call_id": call_id,
        "content": f"<tool_result>{fence(payload)}</tool_result>",
    }


def number_problems(text: str, checked: list[Any]) -> list[str]:
    """도구 결과에 없는 숫자와 글로 쓴 배수."""
    return [*unsupported([text], checked), *multipliers([text])]


def number_retry_message(text: str, bad: list[str]) -> str:
    """걸린 숫자·표현과 그 문장을 보여 준다(해설 재생성과 같은 방식)."""
    lines = [ln.strip() for ln in text.split("\n") if any(b in ln for b in bad)]
    quoted = "\n".join(f"- {ln}" for ln in lines[:5])
    return (
        f"위 답에 조회 결과에 없는 숫자나 표현이 있습니다: {', '.join(bad[:10])}\n"
        f"문제가 된 줄:\n{quoted}\n"
        "조회 결과에 있는 숫자만 그대로(금액은 쉼표를 넣은 원 단위) 쓰도록 고치거나 "
        "그 문장을 빼고, 도구는 다시 부르지 말고 위 조회 결과만으로 답 전체를 다시 쓰세요. "
        "차이·비율·배수를 계산하거나 목록 개수를 세지 마세요."
    )


def _parse(call: ToolCall) -> dict[str, Any] | None:
    if call.name not in TOOL_NAMES:
        return None
    try:
        args = json.loads(call.arguments or "{}")
    except ValueError:
        return None
    return args if isinstance(args, dict) else None


async def run_turn(
    llm: LLMClient,
    *,
    profile: str | None,
    history: list[Message],
    user_text: str,
    execute: ToolExec,
    emit: Emit,
) -> TurnResult:
    spec = TASKS["assistant"]
    profile_text = (profile or "")[:PROFILE_CHARS] or "(프로필 없음)"
    messages: list[Message] = [
        {"role": "system", "content": system_text("assistant", profile=profile_text)},
        *history[-HISTORY:],
        {"role": "user", "content": user_text},
    ]
    seen: dict[int, None] = {}  # 이번 턴 도구 결과에 나온 공고 (순서 유지)
    done_calls: set[str] = set()
    tool_log: list[dict[str, Any]] = []
    actions: list[dict[str, Any]] = []
    removed: list[str] = []
    emitted: list[str] = []
    checked: list[Any] = []  # 숫자를 대조할 도구 결과(낙찰·경쟁사)
    held: list[str] = []  # 낙찰 도구를 쓴 뒤의 답: 검증 뒤에 내보낸다
    fallback = False

    def out(text: str) -> None:
        if text:
            emitted.append(text)
            emit({"type": "token", "text": text})

    async def stream(final: bool, sink: Callable[[str], None]) -> tuple[str, list[ToolCall]]:
        flt = IdFilter(set(seen))
        raw: list[str] = []
        calls: list[ToolCall] = []
        got_usage = False
        async for ev in llm.chat_stream(
            messages,
            tools=TOOLS,
            tool_choice="none" if final else "auto",
            temperature=spec.temperature,
            max_tokens=spec.max_tokens,
        ):
            if isinstance(ev, TextDelta):
                raw.append(ev.text)
                sink(flt.feed(ev.text))
            elif isinstance(ev, ToolCalls):
                calls = ev.calls
            elif isinstance(ev, StreamUsage):
                got_usage = True
                usage.record_llm(ev.prompt_tokens, ev.completion_tokens)
        sink(flt.flush())
        if not got_usage:
            usage.record_llm(0, 0)
        removed.extend(r for r in flt.removed if r not in removed)
        return "".join(raw), calls

    for rnd in range(MAX_ROUNDS):
        final = fallback or rnd == MAX_ROUNDS - 1
        if checked and not held:
            emit({"type": "status", "stage": "explain", "message": CHECK_STATUS})
        raw_text, calls = await stream(final, held.append if checked else out)
        if final or not calls:
            break

        messages.append(
            {
                "role": "assistant",
                "content": raw_text or None,
                "tool_calls": [
                    {
                        "id": c.id,
                        "type": "function",
                        "function": {"name": c.name, "arguments": c.arguments},
                    }
                    for c in calls
                ],
            }
        )
        for call in calls:
            args = _parse(call)
            if args is None:
                fallback = True
                messages.append(
                    _tool_message(call.id, '{"error": "도구 호출을 해석하지 못했어요"}')
                )
                tool_log.append({"name": call.name, "args": None, "summary": "해석 실패"})
                continue
            key = f"{call.name}:{json.dumps(args, sort_keys=True, ensure_ascii=False)}"
            if key in done_calls:
                messages.append(
                    _tool_message(
                        call.id, '{"error": "같은 호출을 반복했어요. 이미 받은 결과로 답하세요."}'
                    )
                )
                continue
            done_calls.add(key)
            emit(
                {
                    "type": "status",
                    "stage": STAGE.get(call.name, "search"),
                    "message": STATUS_TEXT[call.name],
                }
            )
            try:
                outcome = await execute(call.name, args)
            except ToolArgError as e:
                outcome = ToolOutcome(
                    text=json.dumps({"error": f"인자 오류: {e}"}, ensure_ascii=False),
                    summary=f"{call.name}: 인자 오류",
                )
            for bid_id in outcome.bid_ids:
                seen.setdefault(bid_id, None)
            if outcome.action is not None:
                actions.append(outcome.action)
            tool_log.append({"name": call.name, "args": args, "summary": outcome.summary})
            if call.name in NUMBER_CHECKED:
                try:
                    checked.append(json.loads(outcome.text))
                except ValueError:
                    checked.append(outcome.text)
            messages.append(_tool_message(call.id, outcome.text))

    number_warnings: list[str] = []
    hint = ""
    if checked:
        answer = strip_tool_text("".join(held))
        bad = number_problems(answer, checked)
        if bad or not answer:
            number_warnings.append(f"조회 결과에 없는 숫자·표현: {', '.join(bad[:10]) or '빈 답'}")
            messages.append({"role": "assistant", "content": answer or "(빈 답)"})
            messages.append({"role": "user", "content": number_retry_message(answer, bad)})
            again: list[str] = []
            await stream(True, again.append)
            retry = strip_tool_text("".join(again))
            bad = number_problems(retry, checked)
            if retry and not bad:
                answer = retry
            else:
                # 다시 만든 답이 비었거나 도구 호출 글뿐이면 첫 답에서 문장을 뺀다
                base = retry or answer
                answer, dropped = keep_supported(base, checked)
                left = number_problems(base, checked)
                number_warnings.append(
                    f"답에서 문장 {dropped}개 뺌: {', '.join(left[:10]) or '빈 답'}"
                )
                hint = NUMBER_HINT if answer else ""
                answer = answer or NUMBER_FAILED
        out(tidy(answer))
    if fallback:
        out(f"\n\n{FALLBACK_HINT}")
    if hint:
        out(f"\n\n{hint}")
    content = "".join(emitted)
    cards = [int(m.group(2)) for m in _REF.finditer(content) if int(m.group(2)) in seen]
    return TurnResult(
        content=content,
        card_ids=list(dict.fromkeys(cards)),
        warnings=[f"존재하지 않는 공고 ID 제거: {r}" for r in removed] + number_warnings,
        tool_log=tool_log,
        actions=actions,
    )
