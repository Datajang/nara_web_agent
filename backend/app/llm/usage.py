"""요청 단위 사용량·캐시 적중·진행 상태 (SPEC §5.8, §6.4, §8.1-6).

ContextVar에 가변 객체를 두므로, single-flight가 만든 자식 태스크의 LLM 호출도 같은 요청에
합산된다. 진행 상태 콜백(on_status)은 SSE 라우터가 넣고, 파이프라인은 stage만 알린다.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable, Iterator
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any

StatusFn = Callable[[dict[str, Any]], None]


@dataclass
class RunStats:
    llm_calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cache: dict[str, bool] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    on_status: StatusFn | None = None
    parent: RunStats | None = None

    def chain(self) -> Iterator[RunStats]:
        node: RunStats | None = self
        while node is not None:
            yield node
            node = node.parent


_run: ContextVar[RunStats | None] = ContextVar("llm_run", default=None)


@contextlib.contextmanager
def track(on_status: StatusFn | None = None) -> Iterator[RunStats]:
    """요청(또는 하위 작업) 단위 집계. 바깥 track이 있으면 그쪽에도 합산된다."""
    run = RunStats(on_status=on_status, parent=_run.get())
    token = _run.set(run)
    try:
        yield run
    finally:
        _run.reset(token)


def current() -> RunStats | None:
    return _run.get()


def record_llm(prompt_tokens: int, completion_tokens: int) -> None:
    if (run := _run.get()) is not None:
        for r in run.chain():
            r.llm_calls += 1
            r.prompt_tokens += prompt_tokens
            r.completion_tokens += completion_tokens


def set_cache(layer: str, hit: bool) -> None:
    """같은 계층이 여러 번 보고되면(파일 여러 개) 하나라도 미적중이면 미적중."""
    if (run := _run.get()) is not None:
        for r in run.chain():
            r.cache[layer] = r.cache.get(layer, True) and hit


def status(stage: str, message: str, **extra: Any) -> None:
    if (run := _run.get()) is not None:
        for r in run.chain():
            if r.on_status is not None:
                r.on_status({"type": "status", "stage": stage, "message": message, **extra})
                return


def warn(message: str) -> None:
    if (run := _run.get()) is not None and message not in run.warnings:
        run.warnings.append(message)
