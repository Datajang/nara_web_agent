"""G2B 공고 정보 (docs/decisions/2026-11-13-official-facts.md, SPEC §7.5-3).

마감·개찰 일시, 배정예산·추정가격, 입찰·낙찰 방법은 G2B가 정확한 값으로 준다. AI가 첨부 문서에서
다시 찾게 하면 문서에 없을 때 놓치거나 지어내므로, 화면에는 이 값을 그대로 쓴다.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Protocol

from pydantic import BaseModel

from app.g2b.mapper import parse_kst


class _BidLike(Protocol):
    @property
    def source(self) -> str: ...
    @property
    def deadline_at(self) -> datetime | None: ...
    @property
    def raw(self) -> dict[str, Any] | None: ...


class OfficialFacts(BaseModel):
    deadline_label: Literal["입찰 마감", "의견 등록 마감"]
    deadline_at: datetime | None
    opening_at: datetime | None  # 개찰 (일반공고만)
    assigned_budget: int | None  # 배정예산, 부가세 포함 (원문 사업비와 같음)
    estimated_price: int | None  # 추정가격, 부가세 제외 (일반공고만)
    contract_method: str | None  # 입찰 방식 (예: 제한경쟁)
    award_method: str | None  # 낙찰 방법 (예: 협상에 의한 낙찰자 결정)


def _amount(v: Any) -> int | None:
    try:
        n = int(float(str(v).replace(",", "")))
    except (TypeError, ValueError):
        return None
    return n if n > 0 else None


def _text(v: Any) -> str | None:
    s = str(v or "").strip()
    return s or None


def _award(v: Any) -> str | None:
    """'협상에의한계약-협상에 의한 낙찰자 결정(SW사업)' → 설명 부분만."""
    s = _text(v)
    if s and "-" in s:
        s = s.split("-", 1)[1].strip() or s
    return s


def official_facts(bid: _BidLike) -> OfficialFacts:
    raw = bid.raw or {}
    if bid.source == "prespec":
        return OfficialFacts(
            deadline_label="의견 등록 마감",
            deadline_at=bid.deadline_at,
            opening_at=None,
            assigned_budget=_amount(raw.get("asignBdgtAmt")),
            estimated_price=None,
            contract_method=None,
            award_method=None,
        )
    return OfficialFacts(
        deadline_label="입찰 마감",
        deadline_at=bid.deadline_at,
        opening_at=parse_kst(raw.get("opengDt")),
        assigned_budget=_amount(raw.get("asignBdgtAmt")),
        estimated_price=_amount(raw.get("presmptPrce")),
        contract_method=_text(raw.get("cntrctCnclsMthdNm")),
        award_method=_award(raw.get("sucsfbidMthdNm")),
    )
