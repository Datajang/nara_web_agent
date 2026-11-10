"""eval/smoke_llm.py 판정 로직 테스트.

실제 vLLM 대신 httpx.MockTransport로 OpenAI 호환 가짜 서버를 둔다(규칙 3).
openai SDK의 응답 파싱 경로를 그대로 거치므로 GPU 서버에서 스크립트가 깨지는 것을 미리 잡는다.
"""

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import httpx
import pytest
from openai import AsyncOpenAI

_PATH = Path(__file__).resolve().parents[3] / "eval" / "smoke_llm.py"
_spec = importlib.util.spec_from_file_location("smoke_llm", _PATH)
assert _spec and _spec.loader
smoke = importlib.util.module_from_spec(_spec)
sys.modules["smoke_llm"] = smoke
_spec.loader.exec_module(smoke)


def _prompt_tokens(body: dict[str, Any]) -> int:
    # 가짜 토크나이저: 글자 2개 = 토큰 1개
    return 10 + sum(len(m.get("content") or "") for m in body["messages"]) // 2


def _completion(body: dict[str, Any], message: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": "x",
        "object": "chat.completion",
        "created": 0,
        "model": body["model"],
        "choices": [{"index": 0, "message": message, "finish_reason": "stop"}],
        "usage": {
            "prompt_tokens": _prompt_tokens(body),
            "completion_tokens": 5,
            "total_tokens": _prompt_tokens(body) + 5,
        },
    }


def _sse(body: dict[str, Any], text: str) -> str:
    def chunk(delta: dict[str, Any], usage: dict[str, int] | None = None) -> str:
        choices = [] if usage else [{"index": 0, "delta": delta, "finish_reason": None}]
        payload = {
            "id": "x",
            "object": "chat.completion.chunk",
            "created": 0,
            "model": body["model"],
            "choices": choices,
            "usage": usage,
        }
        return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

    pieces = [text[i : i + 4] for i in range(0, len(text), 4)]
    out = [chunk({"role": "assistant", "content": ""})]
    out += [chunk({"content": p}) for p in pieces]
    pt = _prompt_tokens(body)
    out.append(
        chunk({}, {"prompt_tokens": pt, "completion_tokens": len(pieces), "total_tokens": pt})
    )
    return "".join(out) + "data: [DONE]\n\n"


def make_handler(*, tool_calls: bool = True, valid_json: bool = True):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/models"):
            data = [{"id": "brain", "object": "model", "owned_by": "x", "max_model_len": 32768}]
            return httpx.Response(200, json={"object": "list", "data": data})
        body = json.loads(request.content)
        prompt = body["messages"][-1]["content"]
        if body.get("stream"):
            text = smoke.NEEDLE if smoke.NEEDLE in prompt else "나라장터는 조달 시스템입니다."
            return httpx.Response(
                200, text=_sse(body, text), headers={"content-type": "text/event-stream"}
            )
        if body.get("tools"):
            if not tool_calls:
                return httpx.Response(
                    200, json=_completion(body, {"role": "assistant", "content": "<tool_call>"})
                )
            call = {
                "id": "c1",
                "type": "function",
                "function": {"name": "search_bids", "arguments": '{"keyword": "AI", "days": 30}'},
            }
            msg = {"role": "assistant", "content": None, "tool_calls": [call]}
            return httpx.Response(200, json=_completion(body, msg))
        if body.get("response_format"):
            facts = {
                "title": "AI 민원",
                "budget_won": 150000000,
                "deadline": "2026-12-01",
                "method": "협상",
            }
            content = json.dumps(facts, ensure_ascii=False) if valid_json else "{title: 깨짐"
            return httpx.Response(
                200, json=_completion(body, {"role": "assistant", "content": content})
            )
        return httpx.Response(200, json=_completion(body, {"role": "assistant", "content": "."}))

    return handler


def client_for(handler) -> AsyncOpenAI:
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return AsyncOpenAI(base_url="http://fake/v1", api_key="t", http_client=http, max_retries=0)


async def test_all_checks_pass_against_healthy_server():
    client = client_for(make_handler())
    results = await smoke.run_checks(client, "brain")
    by_name = {r.name: r for r in results}
    assert [r.name for r in results] == list(smoke.CHECKS)
    assert all(r.passed for r in results), [(r.name, r.error) for r in results]
    assert by_name["long_input"].metrics["prompt_tokens"] >= 12_000 * 0.9
    assert by_name["concurrency"].metrics["succeeded"] == 4
    assert by_name["simple"].metrics["ttft_s"] is not None


async def test_missing_tool_calls_fails_with_parser_hint():
    results = await smoke.run_checks(
        client_for(make_handler(tool_calls=False)), "brain", ("tool_call",)
    )
    assert not results[0].passed
    assert "qwen3_xml" in (results[0].error or "")


async def test_invalid_json_fails_schema_check():
    results = await smoke.run_checks(
        client_for(make_handler(valid_json=False)), "brain", ("json_schema",)
    )
    assert not results[0].passed


async def test_server_error_is_recorded_not_raised():
    def broken(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "boom"})

    results = await smoke.run_checks(client_for(broken), "brain", ("simple",))
    assert not results[0].passed and results[0].error


async def test_server_info_reads_max_model_len():
    info = await smoke.server_info(client_for(make_handler()))
    assert info["models"][0]["max_model_len"] == 32768


@pytest.mark.parametrize("argv", [["--label", "x", "--checks", "bogus"]])
async def test_main_rejects_unknown_check(argv, monkeypatch):
    monkeypatch.setenv("LLM_BASE_URL", "http://fake/v1")
    assert await smoke.main(argv) == 2
