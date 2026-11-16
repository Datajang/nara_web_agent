"""AI 해설 숫자 검증기 (SPEC §15.8, §15.11 수용 기준 6): 입력에 없는 숫자를 넣은 출력을 막는다."""

from decimal import Decimal

import pytest

from app.analysis.explain_check import allowed_values, banned_phrases, numbers, unsupported
from app.llm.schemas import CompareExplain
from app.pipeline.explain import model_input, problems

COMPARE = {
    "period": {"from": "2021-11-11", "to": "2026-11-10"},
    "us": {"bizno": "1234567890", "name": "(주)예시컴퍼니"},
    "them": {"bizno": "2345678901", "name": "가온데이터시스템(주)"},
    "verdicts": [
        {"key": "count", "label": "낙찰 건수", "us": 7, "them": 12, "verdict": "down",
         "rule": "ratio_20", "small_sample": False},
        {"key": "amount_sum", "label": "낙찰금액 합계", "us": 700000000, "them": 2412000000,
         "verdict": "down", "rule": "ratio_20", "small_sample": False},
        {"key": "g2b_rate_median", "label": "낙찰률(G2B) 중앙값", "us": 87.5, "them": None,
         "verdict": "info", "rule": "info", "small_sample": False},
        {"key": "joint_ratio", "label": "공동수급 비중", "us": 0.25, "them": 0.0,
         "verdict": "info", "rule": "info", "small_sample": False},
    ],
    "head_to_head": {"matched": 3, "us_wins": 2, "them_wins": 1},
    "watched": True,
}  # fmt: skip


@pytest.mark.parametrize(
    ("text", "value", "precision", "pct"),
    [
        ("7억원", "700000000", "100000000", False),
        ("24.1억", "2410000000", "10000000", False),
        ("1억 2천만원", "120000000", "10000000", False),
        ("700,000,000원", "700000000", "1", False),
        ("87.5%", "87.5", "0.1", True),
        ("12건", "12", "1", False),
    ],
)
def test_numbers_read_value_and_shown_precision(text, value, precision, pct):
    (n,) = numbers(text)
    assert (n.value, n.precision, n.pct) == (Decimal(value), Decimal(precision), pct)


def test_numbers_glued_to_latin_are_not_numbers():
    assert numbers("낙찰률(G2B) 기준 ratio_20 규칙") == []


def test_allowed_values_include_json_numbers_and_numbers_in_strings():
    vals = allowed_values(COMPARE)
    assert {Decimal(7), Decimal(2412000000), Decimal("87.5"), Decimal(2026), Decimal(11)} <= vals
    assert Decimal(20) not in vals  # 'ratio_20'의 20은 숫자가 아니다


@pytest.mark.parametrize(
    "text",
    [
        "낙찰 건수는 우리 7건, 가온데이터시스템(주) 12건이에요.",
        "낙찰금액 합계는 7억원 대 24억원이에요.",  # 반올림 표기
        "합계 2,412,000,000원, 24.1억원",
        "낙찰률(G2B) 중앙값은 87.5%예요.",
        "공동수급 비중은 25%예요.",  # 비율 0.25 × 100
        "2021년 11월부터 2026년 11월까지, 맞붙은 공고 3건 중 2건",
    ],
)
def test_numbers_from_input_pass(text):
    assert unsupported([text], model_input(COMPARE)) == []


@pytest.mark.parametrize(
    ("text", "bad"),
    [
        ("건수 차이는 5건이에요.", "5"),  # 12 − 7: 계산한 숫자
        ("금액은 3.4배 차이예요.", "3.4"),
        ("우리가 42% 뒤처져요.", "42"),
        ("합계는 8억원이에요.", "8억"),  # 7억과 반올림으로도 다름
        ("차이가 20%를 넘어요.", "20"),  # 판정 기준 숫자
        ("1억 2천만원 차이", "1억 2천만"),
    ],
)
def test_numbers_not_in_input_are_blocked(text, bad):
    assert unsupported([text], model_input(COMPARE)) == [bad]


def test_banned_phrases_block_advice_and_prediction():
    assert banned_phrases(["이 공고에 투찰하세요"]) == ["투찰하"]
    assert banned_phrases(["낙찰 가능성이 높아요"]) == ["가능성"]
    assert banned_phrases(["낙찰 건수는 비슷해요"]) == []


def test_problems_checks_summary_and_every_point():
    ok = CompareExplain(
        summary="가온데이터시스템(주)와 비교했어요.", points=["낙찰 건수 7건 대 12건"]
    )
    assert problems(ok, model_input(COMPARE)) == []
    bad = CompareExplain(
        summary="비교했어요.", points=["좋아요", "건수가 5건 적어요", "투찰가 낮추세요"]
    )
    assert problems(bad, model_input(COMPARE)) == ["5", "투찰가"]


def test_model_input_drops_screen_state_only():
    m = model_input(COMPARE)
    assert "watched" not in m and m["verdicts"] == COMPARE["verdicts"]
