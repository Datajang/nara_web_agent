"""구조화 출력: Pydantic 검증 + repair 1회 (SPEC §8.1-1, §8.7) 와 사용량 집계 (§8.1-6)."""

import json

import pytest

from app.llm.base import Completion, LLMContextTooLong, LLMInvalidOutput
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


# --- 출력 길이 상한 (2026-11-12 실측: summarize_file 실패 9/25건이 모두 4,000토큰에서 잘림) ---

# 실제 공고문 한국어를 들여쓰기 JSON으로 썼을 때 vLLM /tokenize 기준 1.96~2.18자/토큰.
# 가장 촘촘한 값보다 조금 낮게 잡아 최악의 출력 글자 수를 토큰으로 바꾼다.
CHARS_PER_TOKEN = 1.9


def _resolve(node, defs):
    while isinstance(node, dict) and "$ref" in node:
        node = defs[node["$ref"].rsplit("/", 1)[-1]]
    return node


def _longest(node, defs):
    """상한을 꽉 채운 값. 상한 없는 문자열·목록이 있으면 실패 (모든 출력은 길이가 막혀야 함)."""
    node = _resolve(node, defs)
    if "anyOf" in node:
        branches = [_longest(b, defs) for b in node["anyOf"] if b.get("type") != "null"]
        return max(branches, key=lambda v: len(json.dumps(v, ensure_ascii=False)))
    if "enum" in node:
        return max(node["enum"], key=lambda v: len(str(v)))
    t = node.get("type")
    if t == "object":
        return {k: _longest(v, defs) for k, v in node["properties"].items()}
    if t == "array":
        assert "maxItems" in node, f"목록 상한 없음: {node}"
        return [_longest(node["items"], defs) for _ in range(node["maxItems"])]
    if t == "string":
        assert "maxLength" in node, f"문자열 상한 없음: {node}"
        return "가" * node["maxLength"]
    if t in ("number", "integer"):
        return 100.5 if t == "number" else 100
    if t == "boolean":
        return False
    raise AssertionError(f"모르는 스키마: {node}")


@pytest.mark.parametrize(
    "task,model", [("summarize_file", "FileFacts"), ("summarize_bid", "BidSummary")]
)
async def test_worst_case_output_fits_the_token_budget(task, model):
    from app.llm import schemas

    llm = FakeLLM()
    with track():
        await generate(llm, task, MSGS, getattr(schemas, model))
    sent = llm.requests[-1]["json_schema"]
    worst = json.dumps(_longest(sent, sent.get("$defs", {})), ensure_ascii=False, indent=2)
    assert len(worst) / CHARS_PER_TOKEN <= TASKS[task].max_tokens, len(worst)


def test_caps_name_real_fields_and_leave_validation_alone():
    from app.llm import schemas
    from app.llm.structured import CAPS

    for key in CAPS:
        model, field = key.split(".")
        assert field in getattr(schemas, model).model_fields, key
    # 상한은 모델에 보내는 스키마에만: 저장된 긴 값도 그대로 읽힌다
    many = [{"text": "가" * 300, "evidence": "나" * 300}] * 30
    assert len(schemas.FileFacts.model_validate({"requirements": many}).requirements) == 30
    assert "maxItems" not in schemas.FileFacts.model_json_schema()["properties"]["requirements"]


async def test_truncated_output_is_retried_shorter_without_echoing_it():
    """잘린 출력은 고칠 것이 아니라 짧게 다시 써야 한다: 잘린 본문을 되돌려 보내지 않는다."""
    llm = FakeLLM()
    llm.queue(
        "suggest_keywords",
        Completion(text='{"keywords": ["검', finish_reason="length"),
        '{"keywords": ["검색"]}',
    )
    out = await generate(llm, "suggest_keywords", MSGS, KeywordSuggestion)
    assert out.keywords == ["검색"]
    retry = llm.payloads[-1][1]
    assert all(m["role"] != "assistant" for m in retry)
    assert "잘렸" in retry[-1]["content"]


def test_prompts_state_the_same_caps_so_text_is_not_cut_midway():
    """강제 디코딩은 상한에서 문장을 자른다. 프롬프트에 같은 숫자를 알려 처음부터 고르게 한다."""
    from app.llm.prompts import render
    from app.llm.structured import CAPS

    file_p = str(render("summarize_file", file_name="a.hwp", kind="rfp", i=1, n=1, chunk_text="x"))
    for key, unit in [
        ("FileFacts.requirements", "items"),
        ("Requirement.text", "chars"),
        ("Requirement.evidence", "chars"),
    ]:
        n = getattr(CAPS[key], unit)
        assert f"{n}{'개' if unit == 'items' else '자'} 이내" in file_p, key
    assert "YYYY-MM-DD" in file_p  # 일정 날짜 형식 안내
    bid_p = str(
        render("summarize_bid", meta="m", facts_list="f", n_read=1, n_total=1, truncated=False)
    )
    assert f"{CAPS['BidSummary.key_requirements'].items}개 이내" in bid_p
    assert f"{CAPS['BidSummary.overview'].chars}자 이내" in bid_p


async def test_schedule_date_is_forced_to_iso_date_or_null():
    """2026-11-12 예시: date에 '협상 후'·'기술평가 원점수 8'처럼 글이 들어가 마감일 추출 0/16.
    모델에 보내는 스키마에서 날짜 형식(YYYY-MM-DD)만 받게 하고, 모르면 null."""
    from app.llm.schemas import FileFacts

    llm = FakeLLM()
    await generate(llm, "summarize_file", MSGS, FileFacts)
    sent = llm.requests[-1]["json_schema"]
    date = sent["$defs"]["ScheduleItem"]["properties"]["date"]
    kinds = {b.get("type"): b for b in date["anyOf"]}
    assert kinds["string"]["pattern"] == r"^\d{4}-\d{2}-\d{2}$"
    assert "null" in kinds


async def test_contract_method_is_one_of_fixed_choices():
    """2026-11-13 v4: 계약 방식 칸에 '선금 30%, 잔금 70%'·장비명이 들어감 → 보기 중에서만 고르게."""
    from app.llm.schemas import BidSummary
    from app.llm.structured import CONTRACT_METHODS

    llm = FakeLLM()
    with track():
        await generate(llm, "summarize_bid", MSGS, BidSummary)
    prop = llm.requests[-1]["json_schema"]["$defs"]["BudgetContract"]["properties"]
    kinds = {b.get("type"): b for b in prop["contract_method"]["anyOf"]}
    assert kinds["string"]["enum"] == list(CONTRACT_METHODS) and "null" in kinds
    assert "협상에 의한 계약" in CONTRACT_METHODS and "적격심사" in CONTRACT_METHODS


async def test_evaluation_method_is_one_of_fixed_choices():
    """2026-11-13 v5 g019: 평가 방식 칸에 분석 기법명('Atera in situ')이 들어감 → 보기 중에서만."""
    from app.llm.schemas import BidSummary
    from app.llm.structured import EVAL_METHODS

    llm = FakeLLM()
    with track():
        await generate(llm, "summarize_bid", MSGS, BidSummary)
    prop = llm.requests[-1]["json_schema"]["$defs"]["Evaluation"]["properties"]
    kinds = {b.get("type"): b for b in prop["method"]["anyOf"]}
    assert kinds["string"]["enum"] == list(EVAL_METHODS) and "null" in kinds
    assert "종합평가" in EVAL_METHODS and "협상에 의한 계약" in EVAL_METHODS
