"""내 기록 리포지토리 (SPEC §6.1 개인 자원 접근). 모든 쿼리에 user_id 조건을 강제하고,
남의 자원은 403이 아니라 404로 답한다. 공유 analyses 행은 지우지 않는다 (§6.2).
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    Analysis,
    Bid,
    Bookmark,
    Conversation,
    Message,
    Profile,
    SearchRun,
    SearchRunItem,
    UserAnalysis,
)
from app.errors import ApiError


def not_found(what: str = "자원") -> ApiError:
    return ApiError(404, "not_found", f"{what}을(를) 찾을 수 없어요.")


# ---------- 검색 기록 ----------


async def list_runs(
    s: AsyncSession, user_id: int, kind: str | None, limit: int, offset: int
) -> tuple[list[SearchRun], int]:
    where = [SearchRun.user_id == user_id]
    if kind:
        where.append(SearchRun.kind == kind)
    total = await s.scalar(select(func.count()).select_from(SearchRun).where(*where)) or 0
    rows = (
        await s.execute(
            select(SearchRun)
            .where(*where)
            .order_by(SearchRun.created_at.desc(), SearchRun.id.desc())
            .limit(limit)
            .offset(offset)
        )
    ).scalars()
    return list(rows), total


async def get_run(s: AsyncSession, user_id: int, run_id: int) -> SearchRun:
    run = await s.scalar(
        select(SearchRun).where(SearchRun.id == run_id, SearchRun.user_id == user_id)
    )
    if run is None:
        raise not_found("검색 기록")
    return run


async def run_items(
    s: AsyncSession, run_id: int, limit: int, offset: int
) -> list[tuple[Bid, SearchRunItem]]:
    rows = await s.execute(
        select(Bid, SearchRunItem)
        .join(SearchRunItem, SearchRunItem.bid_id == Bid.id)
        .where(SearchRunItem.run_id == run_id)
        .order_by(SearchRunItem.rank)
        .limit(limit)
        .offset(offset)
    )
    return [(b, i) for b, i in rows.all()]


async def delete_run(s: AsyncSession, user_id: int, run_id: int) -> None:
    await get_run(s, user_id, run_id)
    await s.execute(delete(SearchRun).where(SearchRun.id == run_id, SearchRun.user_id == user_id))
    await s.commit()


# ---------- 분석 기록 ----------


async def link_analysis(
    s: AsyncSession, user_id: int, analysis_id: int, profile_id: int | None
) -> None:
    await s.execute(
        insert(UserAnalysis)
        .values(user_id=user_id, analysis_id=analysis_id, profile_id=profile_id)
        .on_conflict_do_nothing(index_elements=["user_id", "analysis_id"])
    )
    await s.commit()


async def list_analyses(
    s: AsyncSession, user_id: int, limit: int, offset: int
) -> tuple[list[tuple[UserAnalysis, Analysis, Bid, str | None]], int]:
    where = UserAnalysis.user_id == user_id
    total = await s.scalar(select(func.count()).select_from(UserAnalysis).where(where)) or 0
    rows = await s.execute(
        select(UserAnalysis, Analysis, Bid, Profile.name)
        .join(Analysis, Analysis.id == UserAnalysis.analysis_id)
        .join(Bid, Bid.id == Analysis.bid_id)
        .outerjoin(Profile, (Profile.id == UserAnalysis.profile_id) & (Profile.user_id == user_id))
        .where(where)
        .order_by(UserAnalysis.created_at.desc(), UserAnalysis.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return [(u, a, b, name) for u, a, b, name in rows.all()], total


async def get_analysis(
    s: AsyncSession, user_id: int, analysis_id: int
) -> tuple[UserAnalysis, Analysis]:
    row = (
        await s.execute(
            select(UserAnalysis, Analysis)
            .join(Analysis, Analysis.id == UserAnalysis.analysis_id)
            .where(UserAnalysis.user_id == user_id, UserAnalysis.analysis_id == analysis_id)
        )
    ).first()
    if row is None:
        raise not_found("분석 기록")
    return row[0], row[1]


async def my_latest_analysis_id(s: AsyncSession, user_id: int, bid_id: int) -> int | None:
    return await s.scalar(
        select(UserAnalysis.analysis_id)
        .join(Analysis, Analysis.id == UserAnalysis.analysis_id)
        .where(UserAnalysis.user_id == user_id, Analysis.bid_id == bid_id)
        .order_by(UserAnalysis.created_at.desc(), UserAnalysis.id.desc())
        .limit(1)
    )


async def delete_analysis(s: AsyncSession, user_id: int, analysis_id: int) -> None:
    await get_analysis(s, user_id, analysis_id)
    await s.execute(
        delete(UserAnalysis).where(
            UserAnalysis.user_id == user_id, UserAnalysis.analysis_id == analysis_id
        )
    )
    await s.commit()


# ---------- 북마크 ----------


async def list_bookmarks(s: AsyncSession, user_id: int) -> list[tuple[Bookmark, Bid]]:
    rows = await s.execute(
        select(Bookmark, Bid)
        .join(Bid, Bid.id == Bookmark.bid_id)
        .where(Bookmark.user_id == user_id)
        .order_by(Bookmark.created_at.desc(), Bookmark.id.desc())
    )
    return [(bm, b) for bm, b in rows.all()]


async def put_bookmark(
    s: AsyncSession,
    user_id: int,
    bid_id: int,
    note: str,
    analysis_id: int | None,
    now: datetime,
) -> None:
    if await s.get(Bid, bid_id) is None:
        raise not_found("공고")
    if analysis_id is not None:
        await get_analysis(s, user_id, analysis_id)  # 내 분석만 연결할 수 있다
    stmt = insert(Bookmark).values(
        user_id=user_id, bid_id=bid_id, note=note, analysis_id=analysis_id, created_at=now
    )
    await s.execute(
        stmt.on_conflict_do_update(
            index_elements=["user_id", "bid_id"],
            set_={"note": stmt.excluded.note, "analysis_id": stmt.excluded.analysis_id},
        )
    )
    await s.commit()


async def delete_bookmark(s: AsyncSession, user_id: int, bid_id: int) -> None:
    res = await s.execute(
        delete(Bookmark).where(Bookmark.user_id == user_id, Bookmark.bid_id == bid_id)
    )
    if not res.rowcount:  # type: ignore[attr-defined]
        raise not_found("북마크")
    await s.commit()


# ---------- 피드백 대상 ----------


async def owns_target(
    s: AsyncSession,
    user_id: int,
    target_type: Literal["analysis", "assistant_message", "search_run"],
    target_id: int,
) -> bool:
    if target_type == "analysis":
        stmt = select(UserAnalysis.id).where(
            UserAnalysis.user_id == user_id, UserAnalysis.analysis_id == target_id
        )
    elif target_type == "search_run":
        stmt = select(SearchRun.id).where(SearchRun.user_id == user_id, SearchRun.id == target_id)
    else:
        stmt = (
            select(Message.id)
            .join(Conversation, Conversation.id == Message.conversation_id)
            .where(
                Conversation.user_id == user_id,
                Message.id == target_id,
                Message.role == "assistant",
            )
        )
    return await s.scalar(stmt) is not None
