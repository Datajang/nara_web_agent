"""eval/run_eval.py 지표 계산 (§12.5, §8.8-1·2). 실제 모델 없이 순수 함수만 시험한다."""

import importlib.util
import sys
from pathlib import Path

import pytest

_PATH = Path(__file__).resolve().parents[3] / "eval" / "run_eval.py"
_spec = importlib.util.spec_from_file_location("run_eval", _PATH)
assert _spec and _spec.loader
ev = importlib.util.module_from_spec(_spec)
sys.modules["run_eval"] = ev
_spec.loader.exec_module(ev)


@pytest.mark.parametrize(
    ("text", "want"),
    [
        ("사업예산 100,000,000원(부가세 포함)", {100_000_000}),
        ("추정가격 1억 2천만원", {120_000_000}),
        ("5,000만원 이내", {50_000_000}),
        ("3억원", {300_000_000}),
        ("금 12,345,000 원", {12_345_000}),
        ("2026년 사업, 제3조, 10명", set()),  # 연도·조항·인원은 금액이 아니다
    ],
)
def test_amounts(text, want):
    assert ev.amounts(text) == want


@pytest.mark.parametrize(
    "text",
    ["2026-11-12", "2026.11.12", "2026. 11. 12.", "2026년 11월 12일", "2026/11/12 10:00"],
)
def test_dates_accept_common_korean_formats(text):
    assert ev.dates(text) == {"2026-11-12"}


def test_grounding_counts_tokens_found_in_source():
    src = ["제안서 제출 마감: 2026. 11. 30. 18:00, 사업비 금 300,000,000원"]
    out = ["마감 2026-11-30, 예산 3억원", "착수 2026-12-01"]  # 12-01은 원문에 없음
    assert ev.grounding(out, src) == (2, 3)


def test_grounding_with_no_numbers_is_zero_of_zero():
    assert ev.grounding(["숫자 없는 요약"], ["원문"]) == (0, 0)


def test_spearman_and_ties():
    assert ev.spearman([1, 2, 3, 4], [10, 20, 30, 40]) == pytest.approx(1.0)
    assert ev.spearman([1, 2, 3, 4], [40, 30, 20, 10]) == pytest.approx(-1.0)
    assert ev.spearman([1, 1, 2], [1, 2, 3]) == pytest.approx(0.866, abs=1e-3)
    assert ev.spearman([1, 1], [1, 2]) is None  # 분산 0


def test_precision_at_k_counts_high_labels():
    scores = {"g1": 90, "g2": 80, "g3": 20, "g4": 70}
    fits = {"g1": "high", "g2": "low", "g3": "high", "g4": "mid"}
    assert ev.precision_at_k(scores, fits, 2) == 0.5


def test_extraction_matches_budget_deadline_method():
    expect = {"budget_won": 300_000_000, "deadline": "2026-11-30", "method": "협상에 의한 계약"}
    summary = {
        "budget_contract": {"budget_text": "금 삼억원(300,000,000원)", "contract_method": None},
        "evaluation": {"method": "협상에의한계약"},
        "schedule": [{"label": "제안서 제출 마감", "date": "2026-11-30"}],
    }
    assert ev.extraction(expect, summary) == {"budget": True, "deadline": True, "method": True}


def test_extraction_skips_unlabeled_and_flags_wrong():
    expect = {"budget_won": None, "deadline": "2026-11-30", "method": ""}
    summary = {"budget_contract": {}, "evaluation": {}, "schedule": [{"label": "마감"}]}
    assert ev.extraction(expect, summary) == {"budget": None, "deadline": False, "method": None}


def test_extraction_counts_g2b_facts_shown_on_screen():
    """화면에 보이는 값(G2B 공고 정보 + 요약)으로 채점 (decisions/2026-11-13-official-facts)."""
    expect = {"budget_won": 99_000_000, "deadline": "2026-11-24", "method": "협상에 의한 계약"}
    official = {
        "deadline_at": "2026-11-24T01:00:00+00:00",  # KST 10:00
        "assigned_budget": 99_000_000,
        "estimated_price": 90_000_000,
        "award_method": "협상에 의한 낙찰자 결정",
        "award_method_code": "협상에의한계약",
        "contract_method": "제한경쟁",
    }
    empty = {"budget_contract": {}, "evaluation": {}, "schedule": []}
    assert ev.extraction(expect, empty, official) == {
        "budget": True,
        "deadline": True,
        "method": True,
    }
    late = {**official, "deadline_at": "2026-11-24T15:30:00+00:00"}  # KST로는 25일
    assert ev.extraction(expect, empty, late)["deadline"] is False
    # 원문 사업금액이 G2B와 다르면 화면에 둘 다 나온다 (v5 g013)
    doc = {**official, "assigned_budget": 670_900_400, "doc_budgets": [{"amount": 99_000_000}]}
    assert ev.extraction(expect, empty, doc)["budget"] is True


def test_schema_rates_from_invalid_output_logs():
    # complete 호출 12회 중 첫 시도 실패 2회(→ repair 2회), 최종 실패 1회 → generate 10회
    st = ev.schema_rates(calls=12, invalid_first=2, invalid_final=1)
    assert st == {"generate": 10, "first_try": 0.8, "with_repair": 0.9}


def test_injection_payload_is_in_the_middle_of_text():
    text = "가" * 100
    out = ev.inject(text)
    assert ev.INJECTION in out and out.startswith("가") and out.endswith("가")


def test_filled_reports_which_structured_fields_have_content():
    summary = {
        "schedule": [{"label": "마감", "date": "2026-11-30"}],
        "budget_contract": {"budget_text": None, "contract_method": "협상에 의한 계약"},
        "key_requirements": [],
        "eligibility": ["중소기업"],
        "evaluation": {"method": None, "items": []},
    }
    assert ev.filled(summary) == {
        "schedule": True, "budget_contract": True, "key_requirements": False,
        "eligibility": True, "evaluation": False,
    }  # fmt: skip
