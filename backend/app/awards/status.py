"""개찰 상태 수집 `status` (2026-11-26, docs/decisions/2026-11-26-opening-status-bulk.md).

개찰결과 목록(`getOpengResultListInfoServc`)을 개찰일시(inqryDiv=3) 창으로 받아
`bid_opening_status`에 덮어쓴다.
마감 공고 카드의 사유(유찰·개찰완료·재입찰)에 쓴다. 창·커버리지·한 페이지 분할은 낙찰 수집과 같다.

- 증분: 어제·오늘(개찰 → 입력 지연 최대 약 24시간) + covered_to 이후 빈 구간.
  공고 수집 10분 타이머 뒤
- 백필: org_settings.backfill_years(기본 5)만큼 과거로(낙찰 타이머).
  단 공고 수집 시작보다 앞은 안 받는다
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, literal_column
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.awards.collector import DAYS_PER_YEAR, load_settings, plan_backfill, plan_incremental
from app.awards.mapper import _int, _text, normalize_bizno
from app.collector import coverage
from app.collector.runner import RunResult, _collect
from app.db.models import BidOpeningStatus
from app.deps import Deps
from app.g2b.client import STATUS_SOURCE
from app.g2b.mapper import parse_kst

INCREMENTAL_SPAN = timedelta(days=2)
TEXT_MAX = 200
BATCH = 1000  # INSERT 인자 상한(32,767) 아래로: 11열 × 1000행


@dataclass(frozen=True)
class StatusRow:
    bid_ntce_no: str
    bid_ntce_ord: str
    bid_clsfc_no: str
    rbid_no: str
    status: str
    opened_at: datetime | None
    input_at: datetime | None
    participant_count: int | None
    result_text: str | None
    top_name: str | None
    top_bizno: str | None

    @property
    def key(self) -> tuple[str, str, str, str]:
        return (self.bid_ntce_no, self.bid_ntce_ord, self.bid_clsfc_no, self.rbid_no)


def to_status(item: dict[str, Any]) -> StatusRow | None:
    """공고번호나 상태가 없으면 None(저장 불가 행). 1순위 업체는 `업체명^사업자번호^…`."""
    no, st = _text(item, "bidNtceNo"), _text(item, "progrsDivCdNm")
    if not no or not st:
        return None
    corp = (_text(item, "opengCorpInfo") or "").split("^")
    text = _text(item, "opengRsltNtcCntnts")
    return StatusRow(
        bid_ntce_no=no,
        bid_ntce_ord=_text(item, "bidNtceOrd") or "000",
        bid_clsfc_no=_text(item, "bidClsfcNo") or "0",
        rbid_no=_text(item, "rbidNo") or "000",
        status=st,
        opened_at=parse_kst(_text(item, "opengDt")),
        input_at=parse_kst(_text(item, "inptDt")),
        participant_count=_int(item.get("prtcptCnum")),
        result_text=text[:TEXT_MAX] if text else None,
        top_name=corp[0].strip() or None,
        top_bizno=normalize_bizno(corp[1]) if len(corp) > 1 else None,
    )


async def status_store(s: AsyncSession, items: list[dict[str, Any]]) -> tuple[int, int]:
    """같은 키는 마지막 행으로 덮어쓴다. (새로 넣은 수, 고친 수)."""
    rows = {r.key: r for r in (to_status(it) for it in items) if r is not None}
    inserted = updated = 0
    values = [r.__dict__.copy() for r in rows.values()]
    for i in range(0, len(values), BATCH):
        ins = insert(BidOpeningStatus).values(values[i : i + BATCH])
        cols = {c: ins.excluded[c] for c in values[0] if c not in _KEY}
        stmt: Any = ins.on_conflict_do_update(
            index_elements=list(_KEY), set_={**cols, "updated_at": func.now()}
        ).returning(literal_column("(xmax = 0)").label("inserted"))  # 새 행이면 xmax = 0
        flags = (await s.execute(stmt)).scalars().all()
        inserted += sum(1 for f in flags if f)
        updated += sum(1 for f in flags if not f)
    return inserted, updated


_KEY = ("bid_ntce_no", "bid_ntce_ord", "bid_clsfc_no", "rbid_no")


async def incremental(deps: Deps) -> RunResult:
    now = deps.clock()
    async with deps.db.session() as s:
        cov = await coverage.get(s, STATUS_SOURCE)
    windows = plan_incremental(cov, now, INCREMENTAL_SPAN)
    return await _collect(deps, STATUS_SOURCE, "incremental", windows, store=status_store)


async def backfill(deps: Deps, days: int | None = None) -> RunResult:
    years, _ = await load_settings(deps)
    now = deps.clock()
    start = now - timedelta(days=days if days is not None else years * DAYS_PER_YEAR)
    async with deps.db.session() as s:
        cov = await coverage.get(s, STATUS_SOURCE)
        bids = await coverage.get(s, "regular")
    if bids is not None:  # 공고가 없는 과거의 상태는 카드에 쓰이지 않는다
        start = max(start, bids.covered_from)
    windows = plan_backfill(cov, start, now)
    if not windows:
        return RunResult(status="ok")
    return await _collect(deps, STATUS_SOURCE, "backfill", windows, store=status_store)
