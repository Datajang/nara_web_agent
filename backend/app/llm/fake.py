"""가짜 LLM (SPEC §8.8-6, §12.2). 실제 모델 없이 5·6장 수용 기준 테스트를 돌린다.

- 기본 출력은 프롬프트의 구분자 안 데이터에서 결정적으로 만들며 §8.4 스키마를 만족한다.
- queue(task, ...)로 다음 출력을 지정한다: 문자열(원문 그대로), 예외(발생), 함수(messages → 문자열).
- script_chat(...)으로 어시스턴트 라운드를 지정한다: 이벤트 목록, 문자열(조각으로 스트리밍), 예외.
- 개발 서버에서 LLM_BACKEND=fake로도 쓴다(운영 금지, config.check_startup).
"""

from __future__ import annotations

import asyncio
import json
import re
from collections import Counter, deque
from collections.abc import AsyncIterator, Callable
from typing import Any

from app.llm.base import (
    Completion,
    LLMUnavailable,
    Message,
    StreamEvent,
    StreamUsage,
    TextDelta,
    ToolCall,
    ToolCalls,
)
from app.llm.schemas import (
    AnalysisResult,
    BidSummary,
    Coverage,
    FileFacts,
    Fit,
    KeywordSuggestion,
    Requirement,
    Risk,
    ScoreBatch,
    ScoreItem,
)

Scripted = str | Exception | Callable[[list[Message]], str]
Events = list[StreamEvent | Exception]  # 예외를 넣으면 스트림 중간에 발생
Round = Events | str | Exception | Callable[[list[Message]], Events]
_REF = re.compile(r"\bb\d+\b")


def _tag(text: str, tag: str) -> str:
    m = re.search(rf"<{tag}>\s*(.*?)\s*</{tag}>", text, re.DOTALL)
    return m.group(1) if m else ""


def _first_user(messages: list[Message]) -> str:
    return next((str(m.get("content", "")) for m in messages if m.get("role") == "user"), "")


def _words(text: str) -> list[str]:
    return [w for w in re.findall(r"[0-9A-Za-z가-힣]+", text) if len(w) >= 2]


def _overlap_score(profile: str, text: str) -> int:
    hits = sum(1 for w in set(_words(profile)) if w in text)
    return min(100, 40 + 20 * hits)


def _file_facts(user: str) -> dict[str, Any]:
    doc = _tag(user, "document")
    m = re.search(r"파일명: (.*?) \(구분: (\w+)\)", user)
    name, kind = (m.group(1), m.group(2)) if m else (None, "other")
    line = next((x.strip() for x in doc.splitlines() if x.strip()), "")
    reqs = (
        [
            Requirement(
                text=f"요구사항: {line[:40]}", kind="functional", evidence=line[:120], source=name
            )
        ]
        if line
        else []
    )
    return FileFacts(
        doc_type="rfp" if kind == "rfp" else "spec" if kind == "spec" else "other",
        purpose=line[:60] or None,
        scope=[line[:40]] if line else [],
        requirements=reqs,
    ).model_dump()


def _bid_summary(user: str) -> dict[str, Any]:
    meta = json.loads(_tag(user, "bid_meta") or "{}")
    facts = json.loads(_tag(user, "file_facts") or "[]")
    cov = dict(re.findall(r"(\w+)=(\w+)", _tag(user, "coverage")))
    title = str(meta.get("title") or "제목 없음")
    reqs = [r for f in facts for r in f.get("requirements", [])][:10]
    return BidSummary(
        headline=title[:80],
        overview=f"{title} 공고입니다. 발주기관은 {meta.get('org') or '미상'}입니다.",
        key_requirements=[Requirement.model_validate(r) for r in reqs],
        keywords=_words(title)[:5],
        coverage=Coverage(
            files_read=int(cov.get("files_read", 0)),
            files_total=int(cov.get("files_total", 0)),
            truncated=cov.get("truncated") == "True",
            warnings=[] if facts else ["첨부 문서를 읽지 못함"],
        ),
    ).model_dump()


def _scores(user: str) -> dict[str, Any]:
    profile = _tag(user, "profile")
    items = []
    for ref, title in re.findall(r"\[(b\d+)\] 제목: (.*?)(?: / |\n|$)", _tag(user, "bids")):
        s = _overlap_score(profile, title)
        items.append(ScoreItem(bid_id=ref, score=s, reason=f"프로필 일치 점수 {s}"))
    return ScoreBatch(scores=items).model_dump()


def _analysis(user: str) -> dict[str, Any]:
    profile = _tag(user, "profile")
    summary = json.loads(_tag(user, "summary") or "{}")
    meta = json.loads(_tag(user, "bid_meta") or "{}")
    score = _overlap_score(profile, f"{meta.get('title', '')} {summary.get('overview', '')}")
    return AnalysisResult(
        overview=summary.get("overview") or "문서에서 확인되지 않음",
        requirements=summary.get("key_requirements", []),
        evaluation=summary.get("evaluation", {}),
        schedule=summary.get("schedule", []),
        budget_contract=summary.get("budget_contract", {}),
        risks=[Risk(text=r) for r in summary.get("risks", [])],
        fit=Fit(score=score, verdict="possible", reasoning="프로필과 공고 제목의 일치도로 판단"),
        next_actions=["제안요청서 확인", "참가자격 확인", "제출 일정 확인"],
        warnings=summary.get("coverage", {}).get("warnings", []),
    ).model_dump()


def _keywords(user: str) -> dict[str, Any]:
    words = list(dict.fromkeys(_words(_tag(user, "profile"))))[:10] or ["공고"]
    return KeywordSuggestion(keywords=words).model_dump()


_DEFAULTS: dict[str, Callable[[str], dict[str, Any]]] = {
    "summarize_file": _file_facts,
    "summarize_bid": _bid_summary,
    "score_bids": _scores,
    "analyze_bid": _analysis,
    "suggest_keywords": _keywords,
}


def text_round(text: str, size: int = 3) -> list[StreamEvent]:
    return [TextDelta(text[i : i + size]) for i in range(0, len(text), size)]


def tool_round(name: str, args: dict[str, Any], call_id: str = "call_1") -> list[StreamEvent]:
    return [ToolCalls([ToolCall(call_id, name, json.dumps(args, ensure_ascii=False))])]


def _default_chat(messages: list[Message]) -> Events:
    last_user = max(i for i, m in enumerate(messages) if m.get("role") == "user")
    tool_msgs = [m for m in messages[last_user:] if m.get("role") == "tool"]
    if not tool_msgs:
        words = _words(str(messages[last_user].get("content", "")))
        return list(tool_round("search_bids", {"keywords": words[:1], "limit": 5}))
    refs = list(dict.fromkeys(r for m in tool_msgs for r in _REF.findall(str(m["content"]))))
    if not refs:
        return list(text_round("조건에 맞는 공고를 찾지 못했어요."))
    return list(text_round(f"찾은 공고예요: {', '.join(refs[:5])}."))


class FakeLLM:
    def __init__(self, model_id: str = "fake-1", delay_s: float = 0.0) -> None:
        self.model_id = model_id
        self.delay_s = delay_s
        self.down = False
        self.calls: Counter[str] = Counter()
        self.payloads: list[tuple[str, list[Message]]] = []
        self.requests: list[dict[str, Any]] = []
        self._queues: dict[str, deque[Scripted]] = {}
        self._rounds: deque[Round] = deque()

    def queue(self, task: str, *outputs: Scripted) -> None:
        self._queues.setdefault(task, deque()).extend(outputs)

    def script_chat(self, *rounds: Round) -> None:
        self._rounds.extend(rounds)

    async def complete(
        self,
        task: str,
        messages: list[Message],
        *,
        json_schema: dict[str, Any] | None,
        temperature: float,
        max_tokens: int,
    ) -> Completion:
        self.calls[task] += 1
        self.payloads.append((task, list(messages)))
        self.requests.append(
            {
                "task": task,
                "json_schema": json_schema,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
        )
        if self.delay_s:
            await asyncio.sleep(self.delay_s)
        if self.down:
            raise LLMUnavailable(task)
        q = self._queues.get(task)
        if q:
            item = q.popleft()
            if isinstance(item, Exception):
                raise item
            if isinstance(item, Completion):  # finish_reason 등을 직접 지정
                return item
            text = item if isinstance(item, str) else item(messages)
        else:
            text = json.dumps(_DEFAULTS[task](_first_user(messages)), ensure_ascii=False)
        return Completion(
            text=text, prompt_tokens=10 + len(str(messages)) // 10, completion_tokens=5
        )

    async def chat_stream(
        self,
        messages: list[Message],
        *,
        tools: list[dict[str, Any]],
        tool_choice: str,
        temperature: float,
        max_tokens: int,
    ) -> AsyncIterator[StreamEvent]:
        self.calls["assistant"] += 1
        self.payloads.append(("assistant", list(messages)))
        self.requests.append({"task": "assistant", "tools": tools, "tool_choice": tool_choice})
        if self.delay_s:
            await asyncio.sleep(self.delay_s)
        if self.down:
            raise LLMUnavailable("assistant")
        item: Round = self._rounds.popleft() if self._rounds else _default_chat
        if isinstance(item, Exception):
            raise item
        if isinstance(item, str):
            events: Events = list(text_round(item))
        elif callable(item):
            events = item(messages)
        else:
            events = item
        if tool_choice == "none":
            events = [e for e in events if not isinstance(e, ToolCalls)] or list(
                text_round("답변이에요.")
            )
        for e in events:
            if isinstance(e, Exception):
                raise e
            yield e
            await asyncio.sleep(0)
        yield StreamUsage(10, 5)

    async def health(self) -> bool:
        return not self.down
