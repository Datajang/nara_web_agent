"""공고 카드 (SPEC §6.3 BidCard). 검색·추천·북마크·어시스턴트가 같은 모양을 쓴다.

- bid_id는 외부용 문자열 `b{id}` (§6.1). LLM에도 같은 ID만 준다.
- status는 deadline_at에서 계산, null이면 open (§4).
- cancelled: 취소공고 표시 (P1 사용자 결정: 검색에서 빼지 않고 표시만). 원본 raw.ntceKindNm.
- summary_ready: 현재 프롬프트 버전의 요약이 이미 있는지(조회가 요약을 만들지 않는다).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import datetime
from typing import Literal

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Bid, BidSummary, Bookmark
from app.llm.versions import SUMMARY_PROMPT, bid_ref, prompt_version

CANCELLED_KIND = "취소공고"


class BidCard(BaseModel):
    bid_id: str
    source: Literal["regular", "prespec"]
    bid_no: str
    title: str
    org_name: str | None
    budget: int | None
    deadline_at: datetime | None
    notice_at: datetime | None
    status: Literal["open", "closed"]
    cancelled: bool
    revision: int  # 1보다 크면 '정정' 배지 (§7.3)
    detail_url: str | None
    has_files: bool
    summary_ready: bool
    bookmarked: bool
    score: int | None = None  # 추천 결과에서만
    reason: str | None = None


def bid_status(bid: Bid, now: datetime) -> Literal["open", "closed"]:
    return "open" if bid.deadline_at is None or bid.deadline_at > now else "closed"


def is_cancelled(bid: Bid) -> bool:
    return (bid.raw or {}).get("ntceKindNm") == CANCELLED_KIND


async def build_cards(
    s: AsyncSession,
    user_id: int,
    bids: Iterable[Bid],
    now: datetime,
    model_id: str | None,
    scores: Mapping[int, tuple[int | None, str | None]] | None = None,
) -> list[BidCard]:
    bids = list(bids)
    ids = [b.id for b in bids]
    if not ids:
        return []
    marked = set(
        (
            await s.execute(
                select(Bookmark.bid_id).where(Bookmark.user_id == user_id, Bookmark.bid_id.in_(ids))
            )
        ).scalars()
    )
    ready: set[int] = set()
    if model_id is not None:
        pv = prompt_version(SUMMARY_PROMPT, model_id)
        ready = set(
            (
                await s.execute(
                    select(BidSummary.bid_id).where(
                        BidSummary.bid_id.in_(ids), BidSummary.prompt_version == pv
                    )
                )
            ).scalars()
        )
    scores = scores or {}
    return [
        BidCard(
            bid_id=bid_ref(b.id),
            source=b.source,  # type: ignore[arg-type]
            bid_no=b.bid_no,
            title=b.title,
            org_name=b.org_name,
            budget=b.budget,
            deadline_at=b.deadline_at,
            notice_at=b.notice_at,
            status=bid_status(b, now),
            cancelled=is_cancelled(b),
            revision=b.revision,
            detail_url=b.detail_url,
            has_files=bool(b.files),
            summary_ready=b.id in ready,
            bookmarked=b.id in marked,
            score=scores.get(b.id, (None, None))[0],
            reason=scores.get(b.id, (None, None))[1],
        )
        for b in bids
    ]
