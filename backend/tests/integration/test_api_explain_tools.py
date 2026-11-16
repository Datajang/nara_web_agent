"""P11: 비교 AI 해설(SSE)과 어시스턴트 낙찰·경쟁사 도구 (SPEC §15.8, §15.11 수용 기준 6).

- 해설 입력은 GET /compare 응답 JSON뿐, 해설의 숫자는 모두 입력에 있다
- 입력에 없는 숫자가 나오면 한 번 다시 만들고, 그래도 실패하면 해설 없이(사용자에게 안 나감)
- 어시스턴트 도구는 API와 같은 서비스 함수·같은 값
"""

import json
from datetime import UTC, datetime

from sqlalchemy import select

from app.analysis.explain_check import unsupported
from app.awards.mapper import to_award
from app.awards.store import upsert_awards
from app.conversations.tools import make_executor
from app.db.models import CollectorCoverage, UsageLog
from app.llm.prompts import PROMPTS
from tests.helpers import admin_client, parse_sse

from .test_api_competitors import AWARDS, KEYWORDS, OTHER, THEM, US

BAD = json.dumps({"summary": "가온과 비교했어요.", "points": ["금액은 4.7배 차이예요."]})


async def _setup(api):
    async with api.db.transaction() as s:
        s.add(
            CollectorCoverage(
                source="awards",
                covered_from=datetime(2021, 1, 1, tzinfo=UTC),
                covered_to=api.clock(),
            )
        )
        await upsert_awards(s, [to_award(it) for it in AWARDS], KEYWORDS)
    a = await admin_client(api)
    r = await a.put("/api/v1/admin/company", json={"our_bizno": US, "field_keywords": KEYWORDS})
    assert r.status_code == 200, r.text
    return a


async def _explain(c, bizno=THEM):
    r = await c.post(f"/api/v1/compare/{bizno}/explain", headers={"Accept": "text/event-stream"})
    assert r.status_code == 200, r.text
    events = parse_sse(r.text)
    return next(e for e in events if e["type"] == "explain"), events


def _input_of(fake_llm):
    task, messages = fake_llm.payloads[-1]
    assert task == "compare_explain"
    user = messages[-1]["content"] if messages[-1]["role"] == "user" else messages[1]["content"]
    start = user.index("<compare>") + len("<compare>")
    return json.loads(user[start : user.index("</compare>")])


async def test_explain_uses_only_compare_json_and_every_number_is_in_it(full_api, fake_llm):
    a = await _setup(full_api)
    compare = (await a.get(f"/api/v1/compare/{THEM}")).json()
    ev, events = await _explain(a)
    await a.aclose()
    assert ev["verified"] is True and ev["explanation"]["points"]
    # 모델 입력 = 비교 응답(화면 상태 watched 제외), 다른 데이터 없음
    sent = _input_of(fake_llm)
    assert sent == {k: v for k, v in compare.items() if k != "watched"}
    assert "compare_json" in PROMPTS["compare_explain"].user
    texts = [ev["explanation"]["summary"], *ev["explanation"]["points"]]
    assert unsupported(texts, sent) == []
    assert events[0]["stage"] == "explain" and events[-1]["type"] == "done"
    async with full_api.db.session() as s:
        log = (
            await s.execute(select(UsageLog).where(UsageLog.event == "compare_explain"))
        ).scalar_one()
    assert log.llm_calls == 1


async def test_unverified_numbers_retry_once_then_drop_explanation(full_api, fake_llm):
    a = await _setup(full_api)
    fake_llm.queue("compare_explain", BAD, BAD)
    ev, _ = await _explain(a)
    assert ev == {"type": "explain", "explanation": None, "verified": False}
    assert fake_llm.calls["compare_explain"] == 2
    # 두 번째 요청은 고쳐 달라는 말과 함께, 걸린 숫자를 알려 준다
    retry = fake_llm.payloads[-1][1][-1]["content"]
    assert "4.7" in retry

    fake_llm.queue("compare_explain", BAD)  # 첫 시도 실패 → 다시 만든 해설(기본)은 통과
    ev2, _ = await _explain(a)
    await a.aclose()
    assert ev2["verified"] is True and fake_llm.calls["compare_explain"] == 4


async def test_explain_errors_before_stream(full_api):
    a = await admin_client(full_api)
    r = await a.post(f"/api/v1/compare/{THEM}/explain")
    await a.aclose()
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_configured"


async def test_assistant_company_tools_match_api(full_api):
    a = await _setup(full_api)
    api_search = (await a.get("/api/v1/companies/search?q=가온")).json()
    api_summary = (await a.get(f"/api/v1/companies/{THEM}")).json()
    api_awards = (await a.get(f"/api/v1/awards?bizno={THEM}&limit=10")).json()
    api_us = (await a.get("/api/v1/awards/summary")).json()
    api_compare = (await a.get(f"/api/v1/compare/{THEM}")).json()
    await a.aclose()

    run = make_executor(full_api.ctx.deps, 1, None)
    search = json.loads((await run("search_companies", {"q": "가온"})).text)
    awards = json.loads((await run("get_company_awards", {"bizno": THEM})).text)
    ours = json.loads((await run("get_company_awards", {})).text)
    compare = json.loads((await run("compare_companies", {"bizno": THEM})).text)
    assert search == api_search
    assert awards == {"summary": api_summary, "awards": api_awards}
    assert ours["summary"] == api_us
    assert compare == api_compare  # 판정·강점·약점까지 같은 값

    # 오류는 모델에 안내문으로 돌려준다(예외로 대화가 끊기지 않음)
    same = json.loads((await run("compare_companies", {"bizno": US})).text)
    missing = json.loads((await run("get_company_awards", {"bizno": "9999999999"})).text)
    short = json.loads((await run("search_companies", {"q": "가"})).text)
    assert "error" in same and "error" in missing and "error" in short
    assert (await run("compare_companies", {"bizno": OTHER})).summary.startswith("compare_")
