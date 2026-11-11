"""구조화 출력: Pydantic 검증 + repair 1회 (SPEC §8.1-1, §8.7) 와 사용량 집계 (§8.1-6)."""

import pytest

from app.llm.base import LLMContextTooLong, LLMInvalidOutput
from app.llm.fake import FakeLLM
from app.llm.schemas import KeywordSuggestion
from app.llm.structured import generate
from app.llm.usage import track

MSGS = [{"role": "user", "content": "<profile>AI 플랫폼 개발</profile>"}]


async def test_valid_output_needs_one_call():
    llm = FakeLLM()
    llm.queue("suggest_keywords", '{"keywords": ["인공지능", "AI"]}')
    out = await generate(llm, "suggest_keywords", MSGS, KeywordSuggestion)
    assert out.keywords == ["인공지능", "AI"]
    assert llm.calls["suggest_keywords"] == 1


async def test_invalid_output_is_repaired_once_with_error_feedback():
    llm = FakeLLM()
    llm.queue("suggest_keywords", "이건 JSON이 아님", '{"keywords": ["검색"]}')
    out = await generate(llm, "suggest_keywords", MSGS, KeywordSuggestion)
    assert out.keywords == ["검색"]
    assert llm.calls["suggest_keywords"] == 2
    repair_msgs = llm.payloads[-1][1]
    assert repair_msgs[-2]["role"] == "assistant"
    assert "스키마" in repair_msgs[-1]["content"]


async def test_second_failure_raises_invalid_output():
    llm = FakeLLM()
    llm.queue("suggest_keywords", '{"keywords": []}', '{"nope": 1}')
    with pytest.raises(LLMInvalidOutput):
        await generate(llm, "suggest_keywords", MSGS, KeywordSuggestion)
    assert llm.calls["suggest_keywords"] == 2


async def test_context_too_long_is_not_repaired():
    llm = FakeLLM()
    llm.queue("suggest_keywords", LLMContextTooLong("too long"))
    with pytest.raises(LLMContextTooLong):
        await generate(llm, "suggest_keywords", MSGS, KeywordSuggestion)
    assert llm.calls["suggest_keywords"] == 1


async def test_usage_is_accumulated_in_tracked_run():
    llm = FakeLLM()
    llm.queue("suggest_keywords", "깨진 출력", '{"keywords": ["검색"]}')
    with track() as run:
        await generate(llm, "suggest_keywords", MSGS, KeywordSuggestion)
    assert run.llm_calls == 2
    assert run.prompt_tokens > 0 and run.completion_tokens > 0


async def test_json_schema_and_task_params_are_sent():
    llm = FakeLLM()
    await generate(llm, "suggest_keywords", MSGS, KeywordSuggestion)
    req = llm.requests[-1]
    assert req["json_schema"]["properties"]["keywords"]["maxItems"] == 10
    assert (req["temperature"], req["max_tokens"]) == (0.2, 300)  # §8.1 표
