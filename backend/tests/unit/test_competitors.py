"""판정 규칙 경계값 (SPEC §15.5, §15.11 수용 기준 4) · 같은 입력 같은 출력."""

from decimal import Decimal

import pytest

from app.analysis.competitors import (
    AwardFact,
    HeadToHead,
    compare,
    field_verdict,
    h2h_verdict,
    metrics,
    overlap_score,
    ratio_verdict,
)


@pytest.mark.parametrize(
    ("us", "them", "want"),
    [
        (0, 0, "same"),  # 둘 다 0
        (100, 80, "same"),  # rel = 0.2 정확히 → 비슷
        (100, 79, "up"),  # 0.21
        (80, 100, "same"),  # −0.2
        (79, 100, "down"),  # −0.21
        (5, 0, "up"),  # 한쪽 0
        (0, 5, "down"),
        (100, 100, "same"),
    ],
)
def test_ratio_rule_20_percent(us, them, want):
    assert ratio_verdict(us, them) == want


@pytest.mark.parametrize(
    ("us", "them", "want"),
    [
        (2, 0, ("info", True)),  # 합 2 < 3 → 표본 적음
        (1, 1, ("info", True)),
        (0, 0, ("info", True)),
        (2, 1, ("up", False)),  # 합 3, 2배 정확히 → 앞섬
        (1, 2, ("down", False)),
        (3, 2, ("same", False)),  # 1.5배 → 비슷
        (4, 2, ("up", False)),  # 2배
        (5, 3, ("same", False)),
        (3, 0, ("up", False)),  # 한쪽 0이면 다른 쪽 2 이상
        (0, 3, ("down", False)),
        (2, 2, ("same", False)),
    ],
)
def test_field_rule_double_and_min_total(us, them, want):
    assert field_verdict(us, them) == want


@pytest.mark.parametrize(
    ("h", "want"),
    [
        (HeadToHead(0, 0, 0), ("info", True)),  # 맞붙은 공고 없음 → 참고
        (HeadToHead(1, 1, 0), ("up", True)),  # 1건 이상이면 판정, 5건 미만은 표본 적음
        (HeadToHead(4, 1, 3), ("down", True)),
        (HeadToHead(4, 2, 2), ("same", True)),
        (HeadToHead(5, 3, 2), ("up", False)),  # 5건이면 표본 적음 아님
        (HeadToHead(6, 0, 0), ("same", False)),  # 둘 다 못 땄으면 비슷
    ],
)
def test_head_to_head_rule(h, want):
    assert h2h_verdict(h) == want


def _f(n, amount=100, org="A", fields=(), rate=None, ratio=None, joint=False):
    return AwardFact(
        (f"R{n:012d}", "000", "0", "000"), amount, org, tuple(fields), rate, ratio, joint
    )


US = [
    _f(1, 100, "A", ("AI",), Decimal("90"), Decimal("0.8")),
    _f(2, 300, "B", ("AI",), Decimal("85")),
    _f(3, 200, "C", ("AI", "데이터")),
]
THEM = [
    _f(11, 1000, "A", ("클라우드",), Decimal("88"), joint=True),
    _f(12, 1000, "A", ("클라우드",)),
    _f(13, 1000, "A", ("클라우드",)),
    _f(14, 500, "B", ("데이터",)),
]


def test_metrics():
    m = metrics(US)
    assert (m.count, m.amount_sum, m.amount_avg, m.org_count) == (3, 600, 200, 3)
    assert m.by_field == {"AI": 3, "데이터": 1}
    assert m.g2b_rate_median == 87.5 and m.ratio_median == 0.8 and m.joint_share == 0.0
    empty = metrics([])
    assert (empty.count, empty.amount_avg, empty.g2b_rate_median, empty.joint_share) == (
        0,
        0,
        None,
        None,
    )


def test_compare_full_table_is_rule_driven():
    shared = [US[0].key, THEM[0].key]
    c = compare(US, THEM, shared)
    v = {r.key: (r.verdict, r.small_sample) for r in c.verdicts}
    assert v["count"] == ("down", False)  # 3 vs 4 → −0.25
    assert v["amount_sum"] == ("down", False)  # 600 vs 3500
    assert v["amount_avg"] == ("down", False)
    assert v["org_count"] == ("up", False)  # 3 vs 2 → 0.33
    assert v["field:AI"] == ("up", False)  # 3 vs 0
    assert v["field:클라우드"] == ("down", False)  # 0 vs 3
    assert v["field:데이터"] == ("info", True)  # 1 vs 1 → 표본 적음
    assert v["head_to_head"] == ("same", True)  # 2건, 1:1
    assert v["g2b_rate_median"] == ("info", False)
    assert c.strengths == ["field:AI", "org_count"]  # |rel| 큰 순
    assert c.weaknesses == ["field:클라우드", "amount_sum", "amount_avg", "count"]


def test_same_input_same_output():
    a = compare(US, THEM, [US[0].key])
    b = compare(list(reversed(US)), list(reversed(THEM)), [US[0].key])
    assert a == b


def test_cards_are_capped_at_five():
    us = [_f(i, 10, f"O{i}", tuple(f"T{j}" for j in range(8))) for i in range(4)]
    c = compare(us, [])
    assert len(c.strengths) == 5 and c.weaknesses == []


def test_overlap_score():
    assert overlap_score(1, 1) == 100
    assert overlap_score(0.5, 0) == 30
    assert overlap_score(0, 0.5) == 20
