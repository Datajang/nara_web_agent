"""SSE 규약 (SPEC §6.4, §6.5-4·5): 형식, ping, 항상 done, 오류 변환, 연결이 끊겨도 작업 계속."""

import asyncio
import json

from app.api.sse import Emitter, sse_response
from app.llm import usage
from app.llm.base import LLMUnavailable
from app.pipeline.singleflight import LockTimeout


async def _collect(resp, limit: int = 100) -> list[str]:
    out = []
    async for chunk in resp.body_iterator:
        out.append(chunk if isinstance(chunk, str) else chunk.decode())
        if len(out) >= limit:
            break
    return out


def _events(chunks: list[str]) -> list[dict]:
    return [json.loads(c.removeprefix("data: ")) for c in chunks if c.startswith("data: ")]


async def test_events_are_data_json_lines_and_end_with_done():
    async def work(em: Emitter):
        em.send({"type": "status", "stage": "search", "message": "찾는 중"})
        usage.record_llm(3, 2)
        return {"message_id": 7}

    resp = sse_response(work)
    chunks = await _collect(resp)
    assert all(c.endswith("\n\n") for c in chunks)
    ev = _events(chunks)
    assert [e["type"] for e in ev] == ["status", "done"]
    assert ev[-1]["message_id"] == 7
    assert ev[-1]["usage"] == {"llm_calls": 1, "g2b_calls": 0, "cache": {}}
    assert resp.headers["x-accel-buffering"] == "no"
    assert resp.headers["cache-control"] == "no-cache"
    assert resp.media_type == "text/event-stream"


async def test_exception_mid_stream_becomes_error_then_done():
    async def work(em: Emitter):
        em.send({"type": "status", "stage": "analyze", "message": "분석 중"})
        raise RuntimeError("boom")

    ev = _events(await _collect(sse_response(work)))
    assert [e["type"] for e in ev] == ["status", "error", "done"]
    assert ev[1]["code"] == "internal_error" and "boom" not in ev[1]["message"]


async def test_llm_unavailable_maps_to_code():
    async def work(em: Emitter):
        raise LLMUnavailable("x")

    ev = _events(await _collect(sse_response(work)))
    assert [e.get("code") for e in ev if e["type"] == "error"] == ["llm_unavailable"]
    assert ev[-1]["type"] == "done"


async def test_lock_timeout_sends_status_error_in_progress_done():
    async def work(em: Emitter):
        em.send({"type": "status", "stage": "summarize", "message": "요약 중"})
        raise LockTimeout("summary:1")

    ev = _events(await _collect(sse_response(work)))
    assert [e["type"] for e in ev] == ["status", "status", "error", "done"]
    assert ev[1]["stage"] == "summarize" and ev[1]["message"] == "다른 요청이 처리 중입니다"
    assert ev[2]["code"] == "in_progress"


async def test_idle_stream_sends_ping_comment():
    async def work(em: Emitter):
        await asyncio.sleep(0.25)
        return None

    chunks = await _collect(sse_response(work, ping_s=0.05))
    assert ": ping\n\n" in chunks
    assert _events(chunks)[-1]["type"] == "done"


async def test_work_continues_after_client_disconnects():
    finished = asyncio.Event()

    async def work(em: Emitter):
        em.send({"type": "status", "stage": "analyze", "message": "분석 중"})
        await asyncio.sleep(0.2)
        finished.set()

    logged: list = []

    async def on_finish(run, g2b_calls, duration_ms):
        logged.append(run.llm_calls)

    resp = sse_response(work, on_finish=on_finish)
    gen = resp.body_iterator
    first = await gen.__anext__()
    assert "status" in (first if isinstance(first, str) else first.decode())
    await gen.aclose()  # 클라이언트 연결 끊김
    await asyncio.wait_for(finished.wait(), timeout=2)
    await asyncio.sleep(0.05)
    assert logged == [0]  # 끊긴 뒤에도 사용량 기록까지 끝난다
