"""어시스턴트 대화 API (SPEC §6.4 messages 흐름, §8.6, §8.8-3, 게이트 '없는 b-ID 0건')."""

import json
from datetime import timedelta

from sqlalchemy import select

from app.db.models import Message
from app.llm.fake import text_round, tool_round
from tests.conftest import NOW
from tests.fakes.g2b import regular_item
from tests.helpers import make_profile, member, parse_sse

AI_TITLES = ["AI 민원 분석", "AI 검색 고도화"]


async def _setup(api, fake_g2b):
    fake_g2b.add(
        "regular",
        *(
            regular_item(f"R26BK9000000{i}", NOW - timedelta(hours=i + 1), title=t)
            for i, t in enumerate(AI_TITLES)
        ),
    )
    c = await member(api, "a@corp.example")
    pid = await make_profile(c)
    conv = (await c.post("/api/v1/conversations", json={"profile_id": pid})).json()
    return c, conv["id"]


async def _say(c, cid, text):
    r = await c.post(
        f"/api/v1/conversations/{cid}/messages",
        json={"content": text},
        headers={"Accept": "text/event-stream"},
    )
    assert r.status_code == 200, r.text
    return r.text, parse_sse(r.text)


async def test_message_flow_status_tokens_cards_done(full_api, fake_g2b):
    c, cid = await _setup(full_api, fake_g2b)
    raw, events = await _say(c, cid, "AI 공고 찾아줘")
    msgs = (await c.get(f"/api/v1/conversations/{cid}/messages")).json()["items"]
    convs = (await c.get("/api/v1/conversations")).json()["items"]
    await c.aclose()
    kinds = [e["type"] for e in events]
    assert kinds[0] == "status" and kinds[-2:] == ["cards", "done"]
    text = "".join(e["text"] for e in events if e["type"] == "token")
    card_ids = [x["bid_id"] for x in events[-2]["items"]]
    assert card_ids and all(ref in text for ref in card_ids)
    assert events[-1]["message_id"] == msgs[-1]["id"]
    assert [m["role"] for m in msgs] == ["user", "assistant"]
    assert [x["bid_id"] for x in msgs[-1]["cards"]] == card_ids
    assert convs[0]["title"] == "AI 공고 찾아줘"  # 첫 질문이 제목
    # 도구 인자·결과는 클라이언트로 내보내지 않는다 (§6.4)
    assert "tool_result" not in raw and '"keywords"' not in raw


async def test_hallucinated_ids_are_removed_from_stream_storage_and_cards(
    full_api, fake_g2b, fake_llm
):
    c, cid = await _setup(full_api, fake_g2b)

    def answer(messages):
        tool = next(m for m in reversed(messages) if m["role"] == "tool")
        real = json.loads(
            tool["content"].removeprefix("<tool_result>").removesuffix("</tool_result>")
        )
        ref = real["items"][0]["bid_id"]
        return text_round(f"{ref}와 b999999, [b424242]를 보세요.", size=2)

    fake_llm.script_chat(tool_round("search_bids", {"keywords": ["AI"]}), answer)
    raw, events = await _say(c, cid, "추천해줘")
    await c.aclose()
    assert "999999" not in raw and "424242" not in raw
    cards = events[-2]["items"]
    assert len(cards) == 1
    async with full_api.db.session() as s:
        stored = (await s.execute(select(Message).where(Message.role == "assistant"))).scalar_one()
    assert "999999" not in stored.content
    assert any("b999999" in w for w in stored.parts["warnings"])
    assert stored.parts["tool_calls"][0]["name"] == "search_bids"


async def test_previous_turn_ids_are_summarized_not_replayed(full_api, fake_g2b, fake_llm):
    c, cid = await _setup(full_api, fake_g2b)
    await _say(c, cid, "AI 공고 찾아줘")
    fake_llm.script_chat("다른 질문엔 짧게 답해요.")
    await _say(c, cid, "고마워")
    await c.aclose()
    second_turn = fake_llm.payloads[-1][1]
    assert not any(m["role"] == "tool" for m in second_turn)  # 이전 도구 결과는 빠진다
    prev = [m for m in second_turn if m["role"] == "assistant"][-1]
    assert "사용한 도구: search_bids" in prev["content"]


async def test_llm_down_gives_error_then_done(full_api, fake_g2b, fake_llm):
    c, cid = await _setup(full_api, fake_g2b)
    fake_llm.down = True
    _, events = await _say(c, cid, "AI 공고")
    await c.aclose()
    assert [e["type"] for e in events] == ["error", "done"]
    assert events[0]["code"] == "llm_unavailable" and "검색 탭" in events[0]["message"]


async def test_message_validation_and_conversation_crud(full_api, fake_g2b):
    c, cid = await _setup(full_api, fake_g2b)
    long = await c.post(f"/api/v1/conversations/{cid}/messages", json={"content": "가" * 4001})
    empty = await c.post(f"/api/v1/conversations/{cid}/messages", json={"content": "  "})
    renamed = await c.patch(f"/api/v1/conversations/{cid}", json={"title": "새 이름"})
    deleted = await c.delete(f"/api/v1/conversations/{cid}")
    gone = await c.get(f"/api/v1/conversations/{cid}/messages")
    await c.aclose()
    assert (long.status_code, empty.status_code) == (422, 422)
    assert renamed.json()["title"] == "새 이름" and deleted.status_code == 204
    assert gone.status_code == 404


async def test_conversation_profile_can_be_changed_only_to_own(full_api, fake_g2b):
    """§7.6 대화별 프로필 선택 (P3b 사용자 결정으로 PATCH에 profile_id 추가)."""
    c, cid = await _setup(full_api, fake_g2b)
    other = await make_profile(c, "클라우드 인프라팀")
    changed = await c.patch(f"/api/v1/conversations/{cid}", json={"profile_id": other})
    cleared = await c.patch(f"/api/v1/conversations/{cid}", json={"profile_id": None})
    b = await member(full_api, "b@corp.example")
    foreign = await make_profile(b)
    stolen = await c.patch(f"/api/v1/conversations/{cid}", json={"profile_id": foreign})
    title_kept = (await c.get("/api/v1/conversations")).json()["items"][0]["title"]
    await c.aclose()
    await b.aclose()
    assert changed.json()["profile_id"] == other
    assert cleared.json()["profile_id"] is None
    assert stolen.status_code == 404
    assert title_kept == ""  # 제목을 주지 않으면 그대로
