"""G2B 공고 정보 (docs/decisions/2026-11-13-official-facts.md, SPEC §7.5-3).

마감·개찰 일시, 배정예산·추정가격, 입찰·낙찰 방법은 G2B가 정확한 값으로 준다. AI가 첨부 문서에서
다시 찾게 하면 문서에 없을 때 놓치거나 지어내므로, 화면에는 이 값을 그대로 쓴다.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from datetime import datetime
from typing import Any, Literal, Protocol

from pydantic import BaseModel

from app.g2b.mapper import parse_kst
from app.pipeline.grounding import leading_amount


class _BidLike(Protocol):
    @property
    def source(self) -> str: ...
    @property
    def deadline_at(self) -> datetime | None: ...
    @property
    def raw(self) -> dict[str, Any] | None: ...


class _DocLike(Protocol):
    @property
    def name(self) -> str: ...
    @property
    def text(self) -> str: ...


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


# 첨부 문서의 사업 금액 (사용자 결정 2026-11-13: 원문 금액이 G2B와 다르면 둘 다 보여 준다).
# AI가 아니라 '사업금액: 665,000,000원'처럼 라벨 바로 뒤에 금액이 오는 표기만 읽는다.
# 참가 조건 문구(예: '사업금액이 20억원 미만', '총 사업비의 0.5%')를 빼려고(실데이터 오탐)
# 라벨과 금액 사이에는 쌍점·'금'만 허용하고, 금액 뒤가 미만·이상·이하·초과면 버린다.
_S = r"\s*"
_BUDGET_LABEL = re.compile(
    rf"(?:총{_S})?(?:사{_S}업{_S}(?:금{_S}액|예{_S}산|비)|소{_S}요{_S}예{_S}산|배{_S}정{_S}예{_S}산)"
    rf"{_S}[:：]?{_S}(?:금{_S})?(?=\d)"
)
_CONDITION = re.compile(r"\s*(?:미만|이상|이하|초과)")
_MIN_WON = 1_000_000
_MAX_DOC_BUDGETS = 3


class DocBudget(BaseModel):
    file: str
    label: str  # 원문 표기 (예: 사업금액)
    amount: int


def doc_budgets(
    docs: Iterable[_DocLike], assigned: int | None, estimated: int | None
) -> list[DocBudget]:
    """첨부 문서에 적힌 사업 금액 중 G2B 배정예산·추정가격과 다른 것 (같은 금액은 한 번만)."""
    seen = {v for v in (assigned, estimated) if v}
    out: list[DocBudget] = []
    for d in docs:
        for m in _BUDGET_LABEL.finditer(d.text):
            found = leading_amount(d.text[m.end() :])
            if found is None or _CONDITION.match(found[1]):
                continue
            won = found[0]
            if won < _MIN_WON or won in seen:
                continue
            seen.add(won)
            label = re.sub(r"[:：]?금?$", "", re.sub(r"\s+", "", m.group(0)))
            out.append(DocBudget(file=d.name, label=label, amount=won))
            if len(out) == _MAX_DOC_BUDGETS:
                return out
    return out
