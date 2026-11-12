"""구조화 출력: Pydantic 검증 + repair 1회 (SPEC §8.1-1, §8.7) 와 사용량 집계 (§8.1-6)."""

import pytest

from app.llm.base import LLMContextTooLong, LLMInvalidOutput
from app.llm.fake import FakeLLM
from app.llm.schemas import KeywordSuggestion
from app.llm.structured import TASKS, generate
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


def _objects(node, out):
    """스키마 안의 모든 object 노드(중첩·$defs 포함)."""
    if isinstance(node, dict):
        if node.get("type") == "object" and "properties" in node:
            out.append(node)
        for v in node.values():
            _objects(v, out)
    elif isinstance(node, list):
        for v in node:
            _objects(v, out)
    return out


async def test_schema_sent_to_llm_requires_every_field():
    """P3a-2 실측: 기본값 있는 필드가 선택이면 모델이 summarize_bid에서 일정·예산·요구사항을 통째로
    빼먹었다(2026-11-12 골든셋). 모든 필드를 required로 보내 빈 값이라도 명시하게 한다."""
    from app.llm.schemas import BidSummary

    llm = FakeLLM()
    with track():
        await generate(llm, "summarize_bid", MSGS, BidSummary)
    sent = llm.requests[-1]["json_schema"]
    objs = _objects(sent, [])
    assert objs, "object 노드가 있어야 함"
    for o in objs:
        assert set(o.get("required", [])) == set(o["properties"]), o.get("title")
    # 검증용 Pydantic 스키마 자체는 그대로(기본값 허용)
    assert BidSummary.model_json_schema()["required"] == ["headline", "overview", "coverage"]


def test_summary_tasks_get_the_full_output_budget():
    # strict 스키마로 모든 필드를 채우면 map 출력이 2,000토큰을 넘어 JSON이 잘린다 (2026-11-12 실측
    # 1,000~2,100). §8.3 예산(입력 24,000 + 출력 4,000 ≤ 32,768)의 출력 몫을 다 준다.
    from app.pipeline.chunking import INPUT_BUDGET

    for task in ("summarize_file", "summarize_bid"):
        assert TASKS[task].max_tokens == 4000
        assert INPUT_BUDGET + TASKS[task].max_tokens <= 32_768


def test_default_llm_timeout_covers_a_full_summary_output():
    # 동시 4요청일 때 요청당 생성 속도 약 17토큰/초 (2026-11-12 vLLM 로그, L4 FP8).
    # 4,000토큰 출력 ≈ 235초 + 입력 처리 → 180초면 타임아웃·재시도로 같은 생성을 세 번 한다.
    from app.config import Settings

    slowest_tok_s = 17
    default = Settings.model_fields["llm_timeout_s"].default
    assert default >= TASKS["summarize_file"].max_tokens / slowest_tok_s + 60
