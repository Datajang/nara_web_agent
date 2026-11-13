"""G2B 공고 정보는 AI를 거치지 않고 그대로 (docs/decisions/2026-11-13-official-facts.md, §7.5-3).

마감일·예산·계약 방법을 AI가 문서에서 다시 찾게 하면, 문서에 없을 때 놓치거나 지어낸다
(골든셋 v4 15건).
"""

from datetime import UTC, datetime

from app.bids.facts import official_facts
from app.bids.meta import bid_meta
from app.g2b.mapper import to_record
from tests.fakes.g2b import prespec_item, regular_item

NOW = datetime(2026, 11, 10, 3, 0, tzinfo=UTC)


class _Bid:
    """ORM 없이 매퍼 결과로 Bid처럼 쓴다."""

    def __init__(self, source: str, item: dict) -> None:
        rec = to_record(source, item)
        self.__dict__.update(rec.model_dump())
        self.id, self.source = 101, source


def test_regular_bid_facts_come_straight_from_g2b():
    item = regular_item("R26BK00000001", NOW, deadline="2026-11-24 10:00:00", budget="90000000")
    item.update(
        opengDt="2026-11-24 11:00:00",
        asignBdgtAmt="99000000",
        cntrctCnclsMthdNm="제한경쟁",
        sucsfbidMthdNm="협상에의한계약-협상에 의한 낙찰자 결정(SW사업)",
    )
    f = official_facts(_Bid("regular", item))
    assert f.deadline_label == "입찰 마감"
    assert f.deadline_at is not None and f.deadline_at.isoformat() == "2026-11-24T01:00:00+00:00"
    assert f.opening_at is not None and f.opening_at.isoformat() == "2026-11-24T02:00:00+00:00"
    assert (f.assigned_budget, f.estimated_price) == (99_000_000, 90_000_000)
    assert f.contract_method == "제한경쟁"
    assert (
        f.award_method == "협상에 의한 낙찰자 결정(SW사업)"
    )  # 코드 부분('협상에의한계약-')은 뺀다


def test_prespec_has_opinion_deadline_and_budget_only():
    f = official_facts(_Bid("prespec", prespec_item("R26BD00000001", NOW)))
    assert f.deadline_label == "의견 등록 마감" and f.deadline_at is not None
    assert f.assigned_budget == 50_000_000 and f.estimated_price is None
    assert f.contract_method is None and f.award_method is None and f.opening_at is None


def test_blank_values_stay_empty_instead_of_guessing():
    item = regular_item("R26BK00000002", NOW, deadline="", budget=None)
    item.update(opengDt="", asignBdgtAmt="0", cntrctCnclsMthdNm="", sucsfbidMthdNm="")
    f = official_facts(_Bid("regular", item))
    assert f.deadline_at is None and f.opening_at is None
    assert f.assigned_budget is None and f.estimated_price is None
    assert f.contract_method is None and f.award_method is None


def test_llm_meta_carries_the_same_facts():
    """AI가 쓰는 메타에도 같은 값이 있어야 원문 대조(메타 포함)에서 같은 숫자가 살아남는다."""
    item = regular_item("R26BK00000003", NOW, budget="90000000")
    item.update(asignBdgtAmt="99000000", sucsfbidMthdNm="협상에의한계약-협상에 의한 낙찰자 결정")
    m = bid_meta(_Bid("regular", item))
    assert m["assigned_budget"] == "99,000,000원" and m["budget"] == "90,000,000원"
    assert m["award_method"] == "협상에 의한 낙찰자 결정"
