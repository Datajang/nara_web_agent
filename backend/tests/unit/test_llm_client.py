"""vLLM(OpenAI 호환) 클라이언트 (SPEC §8.1, §8.7). 실제 서버 대신 httpx 전송 계층 가짜를 쓴다."""

import json

import httpx
import pytest

from app.llm.base import LLMContextTooLong, LLMUnavailable, TextDelta, ToolCalls
from app.llm.client import OpenAICompatLLM

MSGS = [{"role": "user", "content": "안녕"}]


def _ok(content: str = '{"keywords": ["AI"]}') -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "id": "x",
            "object": "chat.completion",
            "created": 0,
            "model": "brain",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": content},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18},
        },
    )


def _client(handler) -> tuple[OpenAICompatLLM, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def wrapped(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        return handler(req, len(seen))

    http = httpx.AsyncClient(transport=httpx.MockTransport(wrapped))
    llm = OpenAICompatLLM(
        base_url="http://llm.test/v1",
        api_key="k",
        model="brain",
        model_id="q35-9b",
        timeout_s=5,
        max_concurrency=2,
        retry_delays=(0, 0),
        http_client=http,
    )
    return llm, seen


async def test_complete_sends_schema_and_disables_thinking():
    llm, seen = _client(lambda req, n: _ok())
    out = await llm.complete(
        "suggest_keywords",
        MSGS,
        json_schema={"type": "object"},
        temperature=0.2,
        max_tokens=300,
    )
    assert out.text == '{"keywords": ["AI"]}'
    assert (out.prompt_tokens, out.completion_tokens) == (11, 7)
    body = json.loads(seen[0].content)
    assert body["model"] == "brain"
    assert body["response_format"]["type"] == "json_schema"
    assert body["response_format"]["json_schema"]["schema"] == {"type": "object"}
    assert body["chat_template_kwargs"] == {"enable_thinking": False}
    assert (body["temperature"], body["max_tokens"]) == (0.2, 300)


async def test_retries_5xx_twice_then_succeeds():
    llm, seen = _client(lambda req, n: httpx.Response(503) if n <= 2 else _ok())
    out = await llm.complete("t", MSGS, json_schema=None, temperature=0, max_tokens=10)
    assert out.text and len(seen) == 3


async def test_gives_up_after_retries_as_unavailable():
    llm, seen = _client(lambda req, n: httpx.Response(502))
    with pytest.raises(LLMUnavailable):
        await llm.complete("t", MSGS, json_schema=None, temperature=0, max_tokens=10)
    assert len(seen) == 3


async def test_connection_error_is_unavailable():
    def boom(req, n):
        raise httpx.ConnectError("refused", request=req)

    llm, _ = _client(boom)
    with pytest.raises(LLMUnavailable):
        await llm.complete("t", MSGS, json_schema=None, temperature=0, max_tokens=10)


async def test_context_length_400_is_not_retried():
    msg = "This model's maximum context length is 32768 tokens. However, you requested 40000"
    llm, seen = _client(
        lambda req, n: httpx.Response(400, json={"object": "error", "message": msg, "code": 400})
    )
    with pytest.raises(LLMContextTooLong):
        await llm.complete("t", MSGS, json_schema=None, temperature=0, max_tokens=10)
    assert len(seen) == 1


def _sse(*chunks: dict) -> httpx.Response:
    body = "".join(f"data: {json.dumps(c)}\n\n" for c in chunks) + "data: [DONE]\n\n"
    return httpx.Response(200, content=body.encode(), headers={"content-type": "text/event-stream"})


def _delta(**delta) -> dict:
    return {
        "id": "x",
        "object": "chat.completion.chunk",
        "created": 0,
        "model": "brain",
        "choices": [{"index": 0, "delta": delta, "finish_reason": None}],
    }


async def test_stream_yields_text_and_accumulated_tool_calls():
    tc1 = {"index": 0, "id": "c1", "type": "function", "function": {"name": "search_bids"}}
    tc2 = {"index": 0, "function": {"arguments": '{"keywords": '}}
    tc3 = {"index": 0, "function": {"arguments": '["AI"]}'}}
    llm, seen = _client(
        lambda req, n: _sse(
            _delta(role="assistant", content="찾아"),
            _delta(content="볼게요"),
            _delta(tool_calls=[tc1]),
            _delta(tool_calls=[tc2]),
            _delta(tool_calls=[tc3]),
        )
    )
    events = [
        e
        async for e in llm.chat_stream(
            MSGS, tools=[{"type": "function"}], tool_choice="auto", temperature=0.3, max_tokens=50
        )
    ]
    texts = [e.text for e in events if isinstance(e, TextDelta)]
    calls = [e for e in events if isinstance(e, ToolCalls)]
    assert "".join(texts) == "찾아볼게요"
    assert len(calls) == 1 and calls[0].calls[0].name == "search_bids"
    assert json.loads(calls[0].calls[0].arguments) == {"keywords": ["AI"]}
    body = json.loads(seen[0].content)
    assert body["stream"] is True and body["tool_choice"] == "auto"


async def test_health_checks_models_endpoint():
    def handler(req, n):
        assert req.url.path.endswith("/models")
        return httpx.Response(200, json={"object": "list", "data": []})

    llm, _ = _client(handler)
    assert await llm.health() is True
    down, _ = _client(lambda req, n: httpx.Response(503))
    assert await down.health() is False
