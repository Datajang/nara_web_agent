"""eval/load_test.py (§13.6 부하 확인: 동시 10명 검색·분석) 판정 로직.

실제 서버 대신 httpx.MockTransport로 로그인·검색·분석 SSE를 흉내 낸다(규칙 3).
"""

import importlib.util
import json
import sys
from pathlib import Path

import httpx

_PATH = Path(__file__).resolve().parents[3] / "eval" / "load_test.py"
_spec = importlib.util.spec_from_file_location("load_test", _PATH)
assert _spec and _spec.loader
lt = importlib.util.module_from_spec(_spec)
sys.modules["load_test"] = lt
_spec.loader.exec_module(lt)


def test_percentiles():
    assert lt.pct([], 50) is None
    assert lt.pct([5.0], 95) == 5.0
    assert lt.pct([1.0, 2.0, 3.0, 4.0], 50) == 2.5
    assert lt.pct(list(map(float, range(1, 101))), 95) == 95.05


def test_parse_sse_ignores_pings_and_keeps_order():
    body = ': ping\n\ndata: {"type": "status"}\n\ndata: {"type": "done"}\n\n'
    assert [e["type"] for e in lt.parse_sse(body)] == ["status", "done"]


def _transport(*, broken_stream: bool = False, limited: bool = False):
    def handler(req: httpx.Request) -> httpx.Response:
        path = req.url.path
        assert req.headers.get("origin") == "http://t"  # CSRF 검사 통과용
        if path.endswith("/auth/login"):
            return httpx.Response(200, json={}, headers={"set-cookie": "access_token=x; Path=/api"})
        if path.endswith("/profiles"):
            return httpx.Response(200, json={"items": [{"id": 3, "is_default": True}]})
        if path.endswith("/bids/search"):
            if limited:
                return httpx.Response(429, json={"error": {"code": "rate_limited"}})
            return httpx.Response(200, json={"items": [{"bid_id": "b7"}], "total": 1})
        if path.endswith("/analyze"):
            events = [{"type": "status", "stage": "analyze"}]
            if not broken_stream:
                events += [{"type": "result"}, {"type": "done", "usage": {}}]
            body = "".join(f"data: {json.dumps(e)}\n\n" for e in events)
            return httpx.Response(200, text=body, headers={"content-type": "text/event-stream"})
        return httpx.Response(404)

    return httpx.MockTransport(handler)


async def test_run_counts_successes_and_writes_report():
    report = await lt.run(
        "http://t", [("a@x", "pw")], users=3, rounds=2, keywords=["AI"], transport=_transport()
    )
    assert report["ops"]["search"]["ok"] == 6 and report["ops"]["analyze"]["ok"] == 6
    assert report["ops"]["analyze"]["p95_ms"] is not None
    assert report["verdict"] == "ok" and report["errors"] == {}


async def test_stream_without_done_is_interrupted():
    report = await lt.run(
        "http://t",
        [("a@x", "pw")],
        users=2,
        rounds=1,
        keywords=["AI"],
        transport=_transport(broken_stream=True),
    )
    assert report["errors"] == {"analyze:stream_interrupted": 2}
    assert report["verdict"] == "fail"


async def test_rate_limits_are_reported_separately():
    report = await lt.run(
        "http://t",
        [("a@x", "pw")],
        users=2,
        rounds=1,
        keywords=["AI"],
        transport=_transport(limited=True),
    )
    assert report["errors"] == {"search:429": 2}
    assert report["verdict"] == "fail"
