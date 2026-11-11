"""어시스턴트 루프와 b-ID 검증 (SPEC §8.6, §8.8-3, P3 게이트 '없는 b-ID 0건')."""

import json

from app.llm.assistant import FALLBACK_HINT, IdFilter, ToolOutcome, run_turn
from app.llm.base import TextDelta, ToolCall, ToolCalls
from app.llm.fake import FakeLLM, text_round, tool_round


def test_filter_removes_unknown_ids_across_chunk_boundaries():
    f = IdFilter(allowed={12, 3})
    out = "".join(f.feed(x) for x in ["찾은 공고: b1", "2와 b9", "99, [b3]", " 그리고 [b4", "4]."])
    out += f.flush()
    assert out == "찾은 공고: b12와 , [b3] 그리고 ."
    assert f.removed == ["b999", "b44"]


def test_filter_ignores_words_that_only_contain_b_digits():
    f = IdFilter(allowed=set())
    assert f.feed("web123 sub7 ") + f.flush() == "web123 sub7 "
    assert f.removed == []


class Tools:
    def __init__(self, ids=(5, 6)):
        self.ids = list(ids)
        self.calls: list[tuple[str, dict]] = []

    async def __call__(self, name, args):
        self.calls.append((name, args))
        if name == "navigate":
            return ToolOutcome(
                text='{"ok": true}',
                summary="navigate",
                action={"name": "open_tab", "params": {"tab": args["tab"]}},
            )
        items = [{"bid_id": f"b{i}", "title": f"공고 {i}"} for i in self.ids]
        return ToolOutcome(
            text=json.dumps({"items": items}, ensure_ascii=False),
            bid_ids=self.ids,
            summary=f"{name}: {len(items)}건",
        )


async def _turn(llm, tools, history=None, profile="AI 팀"):
    events: list[dict] = []
    result = await run_turn(
        llm,
        profile=profile,
        history=history or [],
        user_text="AI 공고 찾아줘",
        execute=tools,
        emit=events.append,
    )
    return result, events


def _tokens(events):
    return "".join(e["text"] for e in events if e["type"] == "token")


async def test_default_flow_calls_tool_then_answers_with_cards():
    llm, tools = FakeLLM(), Tools()
    result, events = await _turn(llm, tools)
    assert tools.calls[0][0] == "search_bids"
    assert _tokens(events) == "찾은 공고예요: b5, b6."
    assert result.card_ids == [5, 6] and result.warnings == []
    assert [e["type"] for e in events if e["type"] != "token"] == ["status"]


async def test_hallucinated_id_never_reaches_user_or_cards():
    llm, tools = FakeLLM(), Tools()
    llm.script_chat(
        tool_round("search_bids", {"keywords": ["AI"]}),
        text_round("b5와 b777을 추천해요. 자세한 건 [b777]을 보세요.", size=2),
    )
    result, events = await _turn(llm, tools)
    assert "777" not in _tokens(events) and "777" not in result.content
    assert result.card_ids == [5]
    assert any("b777" in w for w in result.warnings)


async def test_ids_from_previous_turns_are_not_trusted():
    llm, tools = FakeLLM(), Tools()
    llm.script_chat(tool_round("search_bids", {"keywords": ["AI"]}), "b42와 b5를 보세요.")
    history = [
        {"role": "user", "content": "이전 질문"},
        {"role": "assistant", "content": "b42를 추천했어요."},
    ]
    result, events = await _turn(llm, tools, history=history)
    assert "b42" not in _tokens(events) and result.card_ids == [5]


async def test_repeated_identical_call_is_blocked():
    llm, tools = FakeLLM(), Tools()
    same = {"keywords": ["AI"], "limit": 5}
    llm.script_chat(
        tool_round("search_bids", same),
        tool_round("search_bids", same, call_id="call_2"),
        "b5예요.",
    )
    await _turn(llm, tools)
    assert len(tools.calls) == 1
    tool_msgs = [m for m in llm.payloads[-1][1] if m["role"] == "tool"]
    assert "반복" in tool_msgs[-1]["content"]


async def test_at_most_four_rounds_and_last_forces_no_tools():
    llm, tools = FakeLLM(), Tools()
    llm.script_chat(*(tool_round("search_bids", {"keywords": [f"k{i}"]}) for i in range(4)))
    await _turn(llm, tools)
    assert llm.calls["assistant"] == 4
    assert len(tools.calls) == 3
    assert [r["tool_choice"] for r in llm.requests] == ["auto", "auto", "auto", "none"]


async def test_unparsable_tool_call_falls_back_to_plain_answer_with_hint():
    llm, tools = FakeLLM(), Tools()
    llm.script_chat([ToolCalls([ToolCall("c1", "search_bids", "{broken")])], "일반 답변이에요.")
    result, events = await _turn(llm, tools)
    assert tools.calls == []
    assert llm.requests[-1]["tool_choice"] == "none"
    assert result.content.endswith(FALLBACK_HINT) and _tokens(events).endswith(FALLBACK_HINT)


async def test_unknown_tool_is_a_parse_failure():
    llm, tools = FakeLLM(), Tools()
    llm.script_chat([ToolCalls([ToolCall("c1", "delete_everything", "{}")])], "답변")
    result, _ = await _turn(llm, tools)
    assert tools.calls == [] and result.content.endswith(FALLBACK_HINT)


async def test_tool_results_are_fenced_and_inputs_are_bounded():
    llm, tools = FakeLLM(), Tools()
    history = [
        {"role": "user" if i % 2 == 0 else "assistant", "content": f"m{i}"} for i in range(30)
    ]
    await _turn(llm, tools, history=history, profile="가" * 900)
    first = llm.payloads[0][1]
    assert first[0]["role"] == "system" and "가" * 500 in first[0]["content"]
    assert "가" * 501 not in first[0]["content"]
    assert len(first) == 1 + 12 + 1  # 시스템 + 최근 12개 + 이번 질문
    tool_msg = next(m for m in llm.payloads[-1][1] if m["role"] == "tool")
    assert tool_msg["content"].startswith("<tool_result>")
    assert tool_msg["content"].endswith("</tool_result>")


async def test_navigate_emits_action_without_side_effects():
    llm, tools = FakeLLM(), Tools()
    llm.script_chat(tool_round("navigate", {"tab": "library"}), "내 기록으로 이동해요.")
    result, events = await _turn(llm, tools)
    assert result.actions == [{"name": "open_tab", "params": {"tab": "library"}}]


async def test_text_before_tool_call_is_streamed_and_kept():
    llm, tools = FakeLLM(), Tools()
    llm.script_chat(
        [TextDelta("찾아볼게요. "), *tool_round("search_bids", {"keywords": ["AI"]})], "b6이에요."
    )
    result, events = await _turn(llm, tools)
    assert _tokens(events) == "찾아볼게요. b6이에요." == result.content
