"""SSE 응답 (SPEC §6.4). 각 이벤트는 `data: {json}` + 빈 줄, 종류는 JSON의 type.

- 작업은 별도 태스크로 돌고 이벤트를 큐로 넘긴다. 클라이언트가 끊어도 작업·사용량 기록은
  끝까지 진행한다(캐시에 쓸 결과를 다른 사용자가 재사용할 수 있게). 토큰 전송만 멈춘다.
- 15초 동안 보낼 이벤트가 없으면 `: ping` 주석 줄.
- 정상·오류 모두 마지막은 done(usage 포함). 스트림 시작 전 오류(인증·검증·속도 제한)는 라우터가
  일반 JSON 오류로 먼저 처리한다.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import datetime
from typing import Any

from fastapi.responses import StreamingResponse

from app.errors import ApiError
from app.g2b.client import count_calls
from app.llm import usage
from app.llm.base import LLMError, LLMInvalidOutput, LLMUnavailable
from app.pipeline.singleflight import LockTimeout

log = logging.getLogger(__name__)
PING_S = 15.0
HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
IN_PROGRESS = "다른 요청이 처리 중입니다"
MESSAGES = {
    "llm_unavailable": (
        "지금은 AI 응답이 어려워요. 검색 탭을 이용하거나 잠시 후 다시 시도해 주세요."
    ),
    "llm_invalid_output": (
        "AI 응답 형식이 올바르지 않아 결과를 만들지 못했어요. 다시 시도해 주세요."
    ),
    "llm_error": "AI 응답을 처리하지 못했어요. 잠시 후 다시 시도해 주세요.",
    "in_progress": "다른 요청이 같은 작업을 처리하고 있어요. 잠시 후 다시 확인해 주세요.",
    "internal_error": "요청을 처리하지 못했어요. 잠시 후 다시 시도해 주세요.",
}
_background: set[asyncio.Task[Any]] = set()

FinishFn = Callable[[usage.RunStats, int, int], Awaitable[None]]


def _default(o: object) -> str:
    if isinstance(o, datetime):
        return o.isoformat().replace("+00:00", "Z")
    raise TypeError(type(o).__name__)


def encode(event: dict[str, Any]) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False, default=_default)}\n\n"


class Emitter:
    def __init__(self) -> None:
        self.queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self.stage: str | None = None
        self.message_id: int | None = None

    def send(self, event: dict[str, Any]) -> None:
        if event.get("type") == "status":
            self.stage = event.get("stage")
        self.queue.put_nowait(event)

    def error(self, code: str, message: str | None = None) -> None:
        self.send({"type": "error", "code": code, "message": message or MESSAGES[code]})


Work = Callable[[Emitter], Awaitable[dict[str, Any] | None]]


async def _run(work: Work, em: Emitter, on_finish: FinishFn | None) -> None:
    t0 = time.monotonic()
    extra: dict[str, Any] = {}
    with usage.track(on_status=em.send) as run, count_calls() as calls:
        try:
            extra = await work(em) or {}
        except LockTimeout:
            em.send({"type": "status", "stage": em.stage or "analyze", "message": IN_PROGRESS})
            em.error("in_progress")
        except LLMUnavailable:
            em.error("llm_unavailable")
        except LLMInvalidOutput:
            em.error("llm_invalid_output")
        except LLMError:
            log.warning("sse: llm error", exc_info=True)
            em.error("llm_error")
        except ApiError as e:
            em.error(e.code, e.message)
        except Exception:
            log.exception("sse: work failed")
            em.error("internal_error")
        if on_finish is not None:  # done보다 먼저 기록: done을 받은 시점엔 사용량도 저장돼 있다
            try:
                await on_finish(run, calls.value, int((time.monotonic() - t0) * 1000))
            except Exception:
                log.exception("sse: usage log failed")
        done = {
            "type": "done",
            **extra,
            "usage": {"llm_calls": run.llm_calls, "g2b_calls": calls.value, "cache": run.cache},
        }
        if em.message_id is not None:
            done.setdefault("message_id", em.message_id)
        em.send(done)


def sse_response(
    work: Work, *, on_finish: FinishFn | None = None, ping_s: float = PING_S
) -> StreamingResponse:
    em = Emitter()

    async def stream() -> AsyncIterator[str]:
        task = asyncio.ensure_future(_run(work, em, on_finish))
        _background.add(task)
        task.add_done_callback(_background.discard)
        while True:
            try:
                event = await asyncio.wait_for(em.queue.get(), timeout=ping_s)
            except TimeoutError:
                yield ": ping\n\n"
                continue
            yield encode(event)
            if event.get("type") == "done":
                return

    return StreamingResponse(stream(), media_type="text/event-stream", headers=HEADERS)
