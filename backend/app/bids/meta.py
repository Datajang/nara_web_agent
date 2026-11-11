"""LLM에 주는 공고 메타 (SPEC §8.3-7). URL·파일 경로는 넣지 않는다 (규칙 6)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from app.db.models import Bid
from app.llm.versions import bid_ref

KST = timezone(timedelta(hours=9))


def budget_text(budget: int | None) -> str:
    return f"{budget:,}원" if budget else "미공개"


def kst_text(dt: datetime | None, missing: str = "미정") -> str:
    return dt.astimezone(KST).strftime("%Y-%m-%d %H:%M") if dt else missing


def bid_meta(bid: Bid) -> dict[str, Any]:
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
    }
