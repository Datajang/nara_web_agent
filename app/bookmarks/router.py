from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.database import get_db
from app.db.models import BookmarkedBid, Project
from app.auth.deps import get_current_user

router = APIRouter(tags=["bookmarks"])


class BookmarkIn(BaseModel):
    bid_title: str
    bid_number: Optional[str] = None
    file_url: Optional[str] = None
    analysis_summary: Optional[str] = None


def _bm_out(b: BookmarkedBid) -> dict:
    return {"id": b.id, "bid_title": b.bid_title, "bid_number": b.bid_number,
            "file_url": b.file_url, "analysis_summary": b.analysis_summary,
            "bookmarked_at": b.bookmarked_at.isoformat()}


@router.get("/projects/{pid}/bookmarks")
async def list_bookmarks(pid: int, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    p = await db.get(Project, pid)
    if not p or p.user_id != user.id:
        raise HTTPException(404)
    result = await db.execute(select(BookmarkedBid).where(BookmarkedBid.project_id == pid))
    return [_bm_out(b) for b in result.scalars()]


@router.post("/projects/{pid}/bookmarks", status_code=201)
async def create_bookmark(pid: int, body: BookmarkIn, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    p = await db.get(Project, pid)
    if not p or p.user_id != user.id:
        raise HTTPException(404)
    b = BookmarkedBid(project_id=pid, **body.model_dump())
    db.add(b)
    await db.commit()
    await db.refresh(b)
    return _bm_out(b)


@router.delete("/bookmarks/{bid}", status_code=204)
async def delete_bookmark(bid: int, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    b = await db.get(BookmarkedBid, bid)
    if not b:
        raise HTTPException(404)
    p = await db.get(Project, b.project_id)
    if not p or p.user_id != user.id:
        raise HTTPException(403)
    await db.delete(b)
    await db.commit()
