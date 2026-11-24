"""개찰완료 목록(참가 업체 순위·투찰·점수) 온디맨드 캐시 (SPEC §15.4 '온디맨드', P11).

- `getOpengResultListInfoOpengCompt`는 요청이 올 때만 공고(차수) 단위로 부른다
- 한 요청에서 새로 부르는 호출은 MAX_NEW_CALLS(6)회까지(재시도 포함, client.call_cap).
  못 부른 공고는 '일부만 불러왔어요'로 남기고 다음 요청에서 이어 부른다
- 불러온 공고는 bid_participant_fetches에 표시해 0행이어도 다시 부르지 않는다
- 화이트리스트 필드만 저장한다(업체명·사업자번호·순위·투찰·점수·비고). 사업자번호가 없으면 버린다
- 호출 수는 usage_logs(event='competition', cache.source='opening_compt')로 남겨 낙찰 몫 예산에 센다
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Sequence
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import select, tuple_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.awards.mapper import normalize_bizno
from app.awards.store import CHUNK
from app.db.models import BidParticipant, BidParticipantFetch, UsageLog
from app.deps import Deps
from app.g2b.client import G2BBudgetExceeded, G2BError, call_cap, count_calls

log = logging.getLogger(__name__)
SOURCE = "opening_compt"
MAX_NEW_CALLS = 6
Notice = tuple[str, str]  # (공고번호, 차수)
# 같은 프로세스의 동시 요청이 같은 공고를 두 번 부르지 않게 채우기를 한 줄로 세운다
_lock = asyncio.Lock()


def _dec(v: Any) -> Decimal | None:
    s = str(v or "").strip()
    if not s:
        return None
    try:
        return Decimal(s)
    except InvalidOperation:
        return None


def _int(v: Any) -> int | None:
    s = str(v or "").strip().replace(",", "")
    return int(s) if s.isdigit() else None


def to_participant(item: dict[str, Any]) -> dict[str, Any] | None:
    bizno = normalize_bizno(item.get("prcbdrBizno"))
    no = str(item.get("bidNtceNo") or "").strip()
    if bizno is None or not no:
        return None
    return {
        "bid_ntce_no": no,
        "bid_ntce_ord": str(item.get("bidNtceOrd") or "000").strip(),
        "bid_clsfc_no": str(item.get("bidClsfcNo") or "0").strip(),
        "rbid_no": str(item.get("rbidNo") or "000").strip(),
        "bizno": bizno,
        "name": (str(item.get("prcbdrNm") or "").strip() or None),
        "rank": _int(item.get("opengRank")),
        "bid_amount": _int(item.get("bidprcAmt")),
        "bid_rate": _dec(item.get("bidprcrt")),
        "tech_score": _dec(item.get("techEvlVal")),
        "price_score": _dec(item.get("bidPrceEvlVal")),
        "total_score": _dec(item.get("totalEvlAmtVal")),
        "remark": (str(item.get("rmrk") or "").strip()[:100] or None),
    }


async def store(s: AsyncSession, notice: Notice, items: list[dict[str, Any]]) -> int:
    best: dict[tuple[str, str, str, str, str], dict[str, Any]] = {}
    for it in items:
        r = to_participant(it)
        if r is not None and (r["bid_ntce_no"], r["bid_ntce_ord"]) == notice:
            best[
                (r["bid_ntce_no"], r["bid_ntce_ord"], r["bid_clsfc_no"], r["rbid_no"], r["bizno"])
            ] = r
    values = [best[k] for k in sorted(best)]
    cols = (
        "name",
        "rank",
        "bid_amount",
        "bid_rate",
        "tech_score",
        "price_score",
        "total_score",
        "remark",
    )
    # 한 공고 참가 업체가 수천 곳이면 인자 상한(32767)을 넘으므로 나눠 넣는다
    for i in range(0, len(values), CHUNK):
        ins = insert(BidParticipant).values(values[i : i + CHUNK])
        ex = ins.excluded
        await s.execute(
            ins.on_conflict_do_update(
                index_elements=["bid_ntce_no", "bid_ntce_ord", "bid_clsfc_no", "rbid_no", "bizno"],
                set_={c: getattr(ex, c) for c in cols},
            )
        )
    f = insert(BidParticipantFetch).values(
        bid_ntce_no=notice[0], bid_ntce_ord=notice[1], row_count=len(values)
    )
    await s.execute(
        f.on_conflict_do_update(
            index_elements=["bid_ntce_no", "bid_ntce_ord"],
            set_={"row_count": f.excluded.row_count, "fetched_at": f.excluded.fetched_at},
        )
    )
    return len(values)


async def fetched(s: AsyncSession, notices: Sequence[Notice]) -> set[Notice]:
    if not notices:
        return set()
    f = BidParticipantFetch
    rows = await s.execute(
        select(f.bid_ntce_no, f.bid_ntce_ord).where(
            tuple_(f.bid_ntce_no, f.bid_ntce_ord).in_(list(notices))
        )
    )
    return {(a, b) for a, b in rows.all()}


@dataclass
class EnsureResult:
    requested: int = 0  # 개찰 결과가 필요한 공고 수
    loaded: int = 0  # 이미 있거나 이번에 불러온 공고 수
    fetched_now: int = 0  # 이번 요청에서 새로 불러온 공고 수
    g2b_calls: int = 0
    failed: bool = False  # 예산 초과 외의 G2B 오류로 멈춤
    budget_exhausted: bool = False
    missing: list[Notice] = field(default_factory=list)

    @property
    def partial(self) -> bool:
        return bool(self.missing)


async def ensure(
    deps: Deps, notices: Sequence[Notice], user_id: int | None, max_calls: int = MAX_NEW_CALLS
) -> EnsureResult:
    """notices(우선순위 순)의 개찰 결과를 캐시에 채운다. 새 호출은 max_calls회까지."""
    async with _lock:
        return await _ensure(deps, list(dict.fromkeys(notices)), user_id, max_calls)


async def _ensure(
    deps: Deps, order: list[Notice], user_id: int | None, max_calls: int
) -> EnsureResult:
    res = EnsureResult(requested=len(order))
    async with deps.db.session() as s:
        have = await fetched(s, order)
    todo = [n for n in order if n not in have]
    res.loaded = len(order) - len(todo)
    if not todo:
        return res
    if deps.g2b is None:
        res.missing = todo
        return res
    with count_calls() as calls, call_cap(max_calls):
        for i, n in enumerate(todo):
            try:
                items = await deps.g2b.opening_results(*n)
            except G2BBudgetExceeded:
                res.budget_exhausted = calls.value < max_calls
                res.missing = todo[i:]
                break
            except G2BError as e:
                log.warning("개찰 결과 조회 실패 %s: %s", n[0], deps.g2b.mask(str(e)))
                res.failed = True
                res.missing = todo[i:]
                break
            async with deps.db.transaction() as s:
                await store(s, n, items)
            res.fetched_now += 1
            res.loaded += 1
    res.g2b_calls = calls.value
    async with deps.db.transaction() as s:
        s.add(
            UsageLog(
                user_id=user_id,
                event="competition",
                g2b_calls=res.g2b_calls,
                cache={"source": SOURCE, "fetched": res.fetched_now, "partial": res.partial},
            )
        )
    deps.g2b.settle(res.g2b_calls, SOURCE)
    return res
