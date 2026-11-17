"""LLM에 주는 공고 메타 (SPEC §8.3-7). URL·파일 경로는 넣지 않는다 (규칙 6)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from app.bids.facts import official_facts
from app.db.models import Bid
from app.llm.versions import bid_ref

KST = timezone(timedelta(hours=9))


def budget_text(budget: int | None) -> str:
    return f"{budget:,}원" if budget else "미공개"


def money_reading(won: int) -> str | None:
    """억·만 읽기(만 미만 버림). 302,727,273 → '3억 272만', 45,000,000 → '4,500만'."""
    eok, rest = divmod(won, 10**8)
    man = rest // 10**4
    if eok:
        return f"{eok:,}억" + (f" {man:,}만" if man else "")
    return f"{man:,}만" if man else None


def money_text(won: int | None) -> str:
    """어시스턴트 도구 결과용 금액: 원 단위와 억·만 읽기를 함께 준다.

    모델이 원 단위를 억·만으로 직접 바꾸다 자릿수를 틀린다(2026-11-18 실측: 302,727,273원 →
    '약 30억 2700만원'). 맞는 읽기를 주고 그대로 쓰게 한다.
    """
    if not won:
        return "미공개"
    reading = money_reading(won)
    if reading is None:
        return f"{won:,}원"
    exact = won % 10**4 == 0
    return f"{won:,}원 ({'' if exact else '약 '}{reading} 원)"


def kst_text(dt: datetime | None, missing: str = "미정") -> str:
    return dt.astimezone(KST).strftime("%Y-%m-%d %H:%M") if dt else missing


def bid_meta(bid: Bid) -> dict[str, Any]:
    """G2B 공고 정보도 같이 준다: AI 출력의 숫자·날짜를 원문(메타 포함)과 대조할 때 쓴다."""
    f = official_facts(bid)
    return {
        "bid_id": bid_ref(bid.id),
        "source": bid.source,
        "bid_no": bid.bid_no,
        "title": bid.title,
        "org": bid.org_name,
        "budget": budget_text(bid.budget),
        "notice_at": kst_text(bid.notice_at),
        "deadline": kst_text(bid.deadline_at),
        "notice_kind": (bid.raw or {}).get("ntceKindNm"),
        "assigned_budget": budget_text(f.assigned_budget),
        "opening_at": kst_text(f.opening_at),
        "contract_method": f.contract_method,
        "award_method": f.award_method,
    }
