"""해시 기반 멱등 upsert (SPEC §5.3).

- content_hash가 같으면 내용은 그대로 두고 last_seen_at만 갱신.
- 바뀌면 갱신하고 revision+1. 단 저장된 차수(raw.bidNtceOrd)보다 낮은 차수는 무시한다
  (같은 공고가 차수별로 여러 줄 오고, 역순으로 도착할 수 있음 — decisions/2026-11-11-g2b-probe.md).
- 같은 배치 안에서 같은 bid_key는 차수가 가장 큰 행만 남긴다.
- 첨부는 bid_files에 추가만 한다 (bid_id, url_hash 중복 무시).
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, literal_column, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Bid, BidFile
from app.g2b.models import BidRecord


@dataclass
class UpsertStats:
    inserted: int = 0
    updated: int = 0
    unchanged: int = 0


def url_hash(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


def _latest(records: Sequence[BidRecord]) -> list[BidRecord]:
    best: dict[str, BidRecord] = {}
    for r in records:
        cur = best.get(r.bid_key)
        if cur is None or (r.ord or "") >= (cur.ord or ""):
            best[r.bid_key] = r
    return list(best.values())


async def upsert_bids(session: AsyncSession, records: Sequence[BidRecord]) -> UpsertStats:
    stats = UpsertStats()
    rows = _latest(records)
    if not rows:
        return stats
    values = [
        {
            "bid_key": r.bid_key,
            "source": r.source,
            "bid_no": r.bid_no,
            "prespec_reg_no": r.prespec_reg_no,
            "title": r.title,
            "org_name": r.org_name,
            "budget": r.budget,
            "deadline_at": r.deadline_at,
            "notice_at": r.notice_at,
            "detail_url": r.detail_url,
            "files": [f.model_dump() for f in r.files],
            "content_hash": r.content_hash(),
            "raw": r.raw,
        }
        for r in rows
    ]
    ins = insert(Bid).values(values)
    ex = ins.excluded
    stmt: Any = ins.on_conflict_do_update(
        index_elements=[Bid.bid_key],
        set_={
            "title": ex.title,
            "org_name": ex.org_name,
            "budget": ex.budget,
            "deadline_at": ex.deadline_at,
            "notice_at": ex.notice_at,
            "detail_url": ex.detail_url,
            "files": ex.files,
            "raw": ex.raw,
            "prespec_reg_no": ex.prespec_reg_no,
            "content_hash": ex.content_hash,
            "revision": Bid.revision + 1,
            "updated_at": func.now(),
            "last_seen_at": func.now(),
        },
        where=(Bid.content_hash.is_distinct_from(ex.content_hash))
        & (
            func.coalesce(ex.raw["bidNtceOrd"].astext, "")
            >= func.coalesce(Bid.raw["bidNtceOrd"].astext, "")
        ),
    ).returning(Bid.bid_key, literal_column("(xmax = 0)").label("inserted"))
    changed = {key: inserted for key, inserted in (await session.execute(stmt)).all()}
    stats.inserted = sum(1 for v in changed.values() if v)
    stats.updated = len(changed) - stats.inserted

    untouched = [r.bid_key for r in rows if r.bid_key not in changed]
    if untouched:
        await session.execute(
            update(Bid).where(Bid.bid_key.in_(untouched)).values(last_seen_at=func.now())
        )
        stats.unchanged = len(untouched)

    # 첨부 목록: 새 파일만 추가
    ids = dict(
        (
            await session.execute(
                select(Bid.bid_key, Bid.id).where(Bid.bid_key.in_([r.bid_key for r in rows]))
            )
        ).all()
    )
    file_rows = [
        {
            "bid_id": ids[r.bid_key],
            "url": f.url,
            "url_hash": url_hash(f.url),
            "name": f.name,
            "kind": f.kind,
            "origin": f.origin,
        }
        for r in rows
        for f in r.files
    ]
    if file_rows:
        await session.execute(
            insert(BidFile)
            .values(file_rows)
            .on_conflict_do_nothing(index_elements=["bid_id", "url_hash"])
        )
    return stats
