"""분석·추천 SSE 계약 (SPEC §6.4, §6.5-4·5, §8.7, P3 완료 게이트의 '두 사용자 LLM 1회')."""

import asyncio
import json
from datetime import timedelta

from sqlalchemy import func, select

from app.db.models import Analysis, SearchRun, UsageLog
from app.llm.base import LLMUnavailable
from tests.conftest import NOW, ORIGIN, build_api, make_auth_settings
from tests.fakes.downloader import docx_bytes
from tests.fakes.g2b import regular_item
from tests.helpers import make_profile, member, seed, sse

RFP_URL = "https://www.g2b.go.kr/files/rfp-sse.docx"
PROFILE = "AI 플랫폼 개발팀. 자연어처리 검색 구축 경험."


async def _bid(api, fake_downloader, no="R26BK80000001"):
    fake_downloader.files[RFP_URL] = (docx_bytes("과업 범위: AI 검색 플랫폼"), "제안요청서.docx")
    item = regular_item(no, NOW - timedelta(hours=1), files=[(RFP_URL, "제안요청서.docx")])
    (bid_id,) = await seed(api.ctx.deps, "regular", item)
    return bid_id


def _types(events):
    return [e["type"] if e["type"] != "status" else f"status:{e['stage']}" for e in events]


async def test_two_users_same_bid_one_computation_and_second_all_cached(
    full_api, fake_llm, fake_downloader
):
    bid_id = await _bid(full_api, fake_downloader)
    a = await member(full_api, "a@corp.example")
    b = await member(full_api, "b@corp.example")
    pa, pb = await make_profile(a, PROFILE), await make_profile(b, PROFILE)
    first = await sse(a, f"/api/v1/bids/b{bid_id}/analyze", {"profile_id": pa})
    calls_after_first = dict(fake_llm.calls)
    second = await sse(b, f"/api/v1/bids/b{bid_id}/analyze", {"profile_id": pb})
    mine = (await b.get("/api/v1/analyses")).json()
    await a.aclose()
    await b.aclose()

    assert _types(first) == [
        "status:files", "status:extract", "status:summarize", "status:analyze", "result", "done",
    ]  # fmt: skip
    assert _types(second) == ["result", "done"]  # 전부 적중이면 status 없이 즉시
    assert dict(fake_llm.calls) == calls_after_first  # 두 번째 사용자는 LLM 호출 0회
    assert calls_after_first == {"summarize_file": 1, "summarize_bid": 1, "analyze_bid": 1}
    assert second[0]["from_cache"] is True and second[0]["analysis_id"] == first[-2]["analysis_id"]
    assert second[-1]["usage"] == {
        "llm_calls": 0,
        "g2b_calls": 0,
        "cache": {"file_text": True, "summary": True, "analysis": True},
    }
    assert first[-1]["usage"]["cache"] == {"file_text": False, "summary": False, "analysis": False}
    async with full_api.db.session() as s:
        logs = (
            (
                await s.execute(
                    select(UsageLog).where(UsageLog.event == "analyze").order_by(UsageLog.id)
                )
            )
            .scalars()
            .all()
        )
    assert [lg.llm_calls for lg in logs] == [3, 0]
    assert logs[1].cache == {"file_text": True, "summary": True, "analysis": True}
    assert mine["total"] == 1  # 두 번째 사용자의 내 기록에도 남는다


async def test_llm_exception_mid_stream_still_ends_with_done(full_api, fake_llm, fake_downloader):
    """§6.5-4"""
    bid_id = await _bid(full_api, fake_downloader)
    fake_llm.queue("analyze_bid", RuntimeError("boom"))
    c = await member(full_api, "a@corp.example")
    pid = await make_profile(c)
    events = await sse(c, f"/api/v1/bids/b{bid_id}/analyze", {"profile_id": pid})
    fake_llm.queue("analyze_bid", LLMUnavailable("down"))
    again = await sse(c, f"/api/v1/bids/b{bid_id}/analyze", {"profile_id": pid})
    await c.aclose()
    assert _types(events)[-2:] == ["error", "done"] and events[-2]["code"] == "internal_error"
    assert "status:summarize" in _types(events)  # 중간까지 진행한 뒤 실패
    assert again[-2]["code"] == "llm_unavailable" and again[-1]["type"] == "done"
    assert "boom" not in json.dumps(events)


async def _post_then_disconnect(app, path, body, cookies):
    """첫 이벤트를 받은 직후 연결을 끊는 ASGI 클라이언트 (httpx는 끊김을 흉내 내지 못한다)."""
    got_first, hang_up = asyncio.Event(), asyncio.Event()
    pending = [{"type": "http.request", "body": json.dumps(body).encode(), "more_body": False}]

    async def receive():
        if pending:
            return pending.pop(0)
        await hang_up.wait()
        return {"type": "http.disconnect"}

    async def send(message):
        if message["type"] == "http.response.body" and message.get("body"):
            got_first.set()

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "https",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "root_path": "",
        "headers": [
            (b"host", b"testserver"),
            (b"origin", ORIGIN.encode()),
            (b"content-type", b"application/json"),
            (b"accept", b"text/event-stream"),
            (b"cookie", cookies.encode()),
        ],
        "client": ("127.0.0.1", 50000),
        "server": ("testserver", 443),
    }
    task = asyncio.create_task(app(scope, receive, send))
    await asyncio.wait_for(got_first.wait(), timeout=5)
    hang_up.set()
    await asyncio.wait_for(task, timeout=5)


async def test_client_disconnect_still_saves_analysis(full_api, fake_llm, fake_downloader):
    """§6.5-5"""
    bid_id = await _bid(full_api, fake_downloader)
    fake_llm.delay_s = 0.2
    c = await member(full_api, "a@corp.example")
    pid = await make_profile(c)
    cookies = "; ".join(f"{k}={v}" for k, v in c.cookies.items())
    await _post_then_disconnect(
        full_api.app, f"/api/v1/bids/b{bid_id}/analyze", {"profile_id": pid}, cookies
    )
    await c.aclose()
    assert fake_llm.calls["analyze_bid"] == 0  # 끊긴 시점에는 아직 분석 전
    for _ in range(50):
        await asyncio.sleep(0.1)
        async with full_api.db.session() as s:
            n = await s.scalar(select(func.count()).select_from(Analysis))
            logged = await s.scalar(
                select(func.count()).select_from(UsageLog).where(UsageLog.event == "analyze")
            )
        if n and logged:
            break
    assert n == 1 and logged == 1


async def test_lock_timeout_reports_in_progress(db, clock, fake_llm, fake_downloader):
    api = build_api(
        db, make_auth_settings(llm_lock_wait_s=0.2), clock, llm=fake_llm, downloader=fake_downloader
    )
    bid_id = await _bid(api, fake_downloader)
    fake_llm.delay_s = 0.6
    a = await member(api, "a@corp.example")
    b = await member(api, "b@corp.example")
    pa, pb = await make_profile(a), await make_profile(b)
    path = f"/api/v1/bids/b{bid_id}/analyze"
    first, second = await asyncio.gather(
        sse(a, path, {"profile_id": pa}), sse(b, path, {"profile_id": pb})
    )
    await a.aclose()
    await b.aclose()
    winner, loser = (first, second) if first[-2]["type"] == "result" else (second, first)
    assert winner[-2]["type"] == "result"
    assert loser[-3]["type"] == "status" and loser[-3]["message"] == "다른 요청이 처리 중입니다"
    assert loser[-2] == {"type": "error", "code": "in_progress", "message": loser[-2]["message"]}
    assert loser[-1]["type"] == "done"


async def test_analyze_without_llm_is_503_before_stream(db, clock):
    api = build_api(db, make_auth_settings(), clock)
    (bid_id,) = await seed(api.ctx.deps, "regular", regular_item("R26BK80000009", NOW))
    c = await member(api, "a@corp.example")
    pid = await make_profile(c)
    r = await c.post(f"/api/v1/bids/b{bid_id}/analyze", json={"profile_id": pid})
    await c.aclose()
    assert r.status_code == 503 and r.json()["error"]["code"] == "llm_unavailable"


async def test_analyze_rate_limited_before_stream(db, clock, fake_llm):
    api = build_api(db, make_auth_settings(rate_limit_enabled=True), clock, llm=fake_llm)
    (bid_id,) = await seed(api.ctx.deps, "regular", regular_item("R26BK80000010", NOW))
    c = await member(api, "a@corp.example")
    pid = await make_profile(c)
    path = f"/api/v1/bids/b{bid_id}/analyze"
    codes = [(await c.post(path, json={"profile_id": pid})).status_code for _ in range(11)]
    await c.aclose()
    assert codes[:10] == [200] * 10 and codes[10] == 429


async def test_recommend_streams_progress_then_sorted_cards(full_api, fake_g2b):
    fake_g2b.add(
        "regular",
        *(
            regular_item(f"R26BK8100000{i}", NOW - timedelta(hours=i + 1), title=t)
            for i, t in enumerate(["AI 검색 플랫폼", "AI 도로 관리", "자연어처리 AI 검색 고도화"])
        ),
    )
    c = await member(full_api, "a@corp.example")
    pid = await make_profile(c, "AI 검색 플랫폼 자연어처리 개발팀", keywords=["AI"])
    events = await sse(c, "/api/v1/recommend", {"profile_id": pid, "days": 7, "top_n": 2})
    runs = (await c.get("/api/v1/search-runs", params={"kind": "recommend"})).json()
    await c.aclose()
    kinds = _types(events)
    assert kinds[0] == "status:search" and kinds[-2:] == ["cards", "done"]
    progress = [e["progress"] for e in events if e["type"] == "status" and e.get("progress")]
    assert progress[-1] == {"done": 3, "total": 3}
    cards = events[-2]["items"]
    assert len(cards) == 2 and cards[0]["score"] >= cards[1]["score"]
    assert all(c["reason"] for c in cards)
    assert runs["total"] == 1 and runs["items"][0]["kind"] == "recommend"
    async with full_api.db.session() as s:
        run = await s.get(SearchRun, runs["items"][0]["id"])
    assert run.profile_id == pid and run.result_count == 2


async def test_suggest_keywords(full_api, fake_llm):
    c = await member(full_api, "a@corp.example")
    r = await c.post(
        "/api/v1/profiles/suggest-keywords", json={"description": "인공지능 검색 플랫폼 개발"}
    )
    fake_llm.down = True
    down = await c.post("/api/v1/profiles/suggest-keywords", json={"description": "x"})
    await c.aclose()
    assert r.status_code == 200 and 1 <= len(r.json()["keywords"]) <= 10
    assert down.status_code == 503 and down.json()["error"]["code"] == "llm_unavailable"


async def test_readyz_reports_db_and_llm(full_api, fake_llm):
    async with full_api.client() as c:
        ok = await c.get("/readyz")
        fake_llm.down = True
        down = await c.get("/readyz")
    assert ok.status_code == 200 and ok.json() == {"db": "ok", "llm": "ok"}
    assert down.status_code == 200 and down.json()["llm"] == "unavailable"
