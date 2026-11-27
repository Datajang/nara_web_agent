"""북마크 공고 결과 확인 (5분 타이머, 설계 2026-11-25).

판별 근거: docs/decisions/2026-11-25-result-status-probe.md. 한 감시 행마다:
1. 개찰결과(`opening_status`)의 진행 상태를 본다.
   분류마다 마지막 재입찰 차수의 상태가 그 분류의 상태
2. 개찰완료가 있으면 개찰완료 목록(순위·투찰가)을 저장하고(0행이면 저장 안 함),
   낙찰을 공고번호로 본다
3. 낙찰 행 → final/awarded. 모든 분류가 유찰 → final/failed. 재입찰·재시담 → 최종 아님.
   낙찰인데 이번 실행에서 순위표를 받지 않았으면 한 번 더 받는다(개찰 뒤 한 분류만 재입찰된 경우)
4. 같은 실행에서 개찰과 낙찰이 함께 보이면 Change(final) 하나(메일 1통에 순위·투찰가)
유찰 뒤 30일 동안은 DB에 수집된 재공고(같은 수요기관·같은 사업명·reNtceYn=Y)를 찾는다
(G2B 호출 없음). 알림 켠 북마크가 없는 감시는 부르지 않는다(켜면 다음 실행에서 이어 감).
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Literal

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.awards import participants
from app.awards.collector import award_store, load_settings
from app.db.models import Bid, BidResultWatch, Bookmark, UsageLog
from app.deps import Deps
from app.g2b.client import RESULT_WATCH_SOURCE, G2BBudgetExceeded, count_calls
from app.results.schedule import RENOTICE_DAYS
from app.results.watch import plan_next

log = logging.getLogger(__name__)
Stage = Literal["opened", "final", "renotice"]
OPENED, FAILED = "개찰완료", "유찰"
DEADLINE_S = 150.0  # 타이머 TimeoutStartSec(240) 안에 발송까지 끝나게
_RENOTICE_MARK = re.compile(r"[(\[{<【〔「『]\s*재공고\s*[)\]}>】〕」』]")


@dataclass(frozen=True)
class Change:
    bid_id: int
    stage: Stage


def same_title(a: str, b: str) -> bool:
    """사업명 비교: 공백과 '재공고' 표기(괄호 포함)는 무시한다. 그 밖의 괄호 내용은 그대로 비교."""

    def norm(s: str) -> str:
        s = _RENOTICE_MARK.sub("", s).replace("재공고", "")
        return re.sub(r"\s+", "", s)

    return norm(a) == norm(b)


def _class_status(rows: list[dict[str, Any]]) -> dict[str, str]:
    """분류(bidClsfcNo)마다 마지막 재입찰(rbidNo) 행의 진행 상태."""
    last: dict[str, tuple[str, str]] = {}
    for r in rows:
        clsfc, rbid = str(r.get("bidClsfcNo") or "0"), str(r.get("rbidNo") or "000")
        if clsfc not in last or rbid >= last[clsfc][0]:
            last[clsfc] = (rbid, str(r.get("progrsDivCdNm") or ""))
    return {k: v[1] for k, v in last.items()}


async def _check_one(deps: Deps, w: BidResultWatch, bid: Bid, now: datetime) -> Change | None:
    """G2B를 불러 감시 행을 갱신한다. 예산 소진은 G2BBudgetExceeded로 올린다."""
    g2b = deps.g2b
    assert g2b is not None
    notice = (bid.bid_no, w.notice_ord)
    # 개찰 결과를 받은 뒤(opened)에는 낙찰만 묻는다(호출을 아껴 새로 개찰한 공고에 몫을 남긴다)
    status = {} if w.stage == "opened" else _class_status(await g2b.opening_status(*notice))
    any_opened = OPENED in status.values()
    opened_now = fetched = False
    if w.stage == "waiting" and any_opened:
        fetched = True
        rows = await g2b.opening_results(*notice, source=RESULT_WATCH_SOURCE)
        if rows:
            async with deps.db.transaction() as s:
                await participants.store(s, notice, rows)
            opened_now = True
    awarded: list[dict[str, Any]] = []
    if any_opened or w.stage == "opened":
        awarded = [
            r
            for r in await g2b.award_by_notice(bid.bid_no)
            if str(r.get("bidNtceOrd") or "000") == w.notice_ord
        ]
        if awarded:
            _, keywords = await load_settings(deps)
            async with deps.db.transaction() as s:
                await award_store(keywords)(s, awarded)
            if not fetched:  # 최종 메일의 순위표를 최신 재입찰 차수로
                rows = await g2b.opening_results(*notice, source=RESULT_WATCH_SOURCE)
                if rows:
                    async with deps.db.transaction() as s:
                        await participants.store(s, notice, rows)
    failed = bool(status) and all(v == FAILED for v in status.values())
    async with deps.db.transaction() as s:
        row = await s.get_one(BidResultWatch, w.bid_id)
        row.checks += 1
        row.updated_at = now
        if awarded or failed:
            row.stage, row.final_kind, row.final_at = (
                "final",
                "awarded" if awarded else "failed",
                now,
            )
            return Change(w.bid_id, "final")  # 같은 실행의 개찰은 opened_at 없이 최종 메일에 함께
        if opened_now:
            row.stage, row.opened_at = "opened", now
        nc = plan_next(row, bid, now)
        if nc is None:
            row.stage = "expired"
        else:
            row.next_check_at = nc
        return Change(w.bid_id, "opened") if opened_now else None


async def _due(s: AsyncSession, now: datetime, limit: int) -> list[tuple[BidResultWatch, Bid]]:
    rows = await s.execute(
        select(BidResultWatch, Bid)
        .join(Bid, Bid.id == BidResultWatch.bid_id)
        .where(
            BidResultWatch.stage.in_(("waiting", "opened")),
            BidResultWatch.next_check_at <= now,
            exists().where(Bookmark.bid_id == Bid.id, Bookmark.notify_result.is_(True)),
        )
        # 가장 최근에 개찰한 공고부터: 개찰 직후가 '바로' 알려야 할 때다
        .order_by(BidResultWatch.opening_at.desc(), BidResultWatch.bid_id)
        .limit(limit)
    )
    return [(w, b) for w, b in rows.all()]


async def _renotices(deps: Deps, now: datetime) -> list[Change]:
    """유찰 뒤 30일 안의 감시마다 DB에 수집된 재공고를 찾는다."""
    out: list[Change] = []
    async with deps.db.transaction() as s:
        rows = await s.execute(
            select(BidResultWatch, Bid)
            .join(Bid, Bid.id == BidResultWatch.bid_id)
            .where(
                BidResultWatch.stage == "final",
                BidResultWatch.final_kind == "failed",
                BidResultWatch.renotice_bid_id.is_(None),
                BidResultWatch.final_at >= now - timedelta(days=RENOTICE_DAYS),
            )
        )
        for w, bid in rows.all():
            candidates = (
                await s.execute(
                    select(Bid).where(
                        Bid.source == "regular",
                        Bid.id != bid.id,
                        Bid.org_name == bid.org_name,
                        Bid.raw["reNtceYn"].astext == "Y",
                        Bid.notice_at >= w.opening_at,
                    )
                )
            ).scalars()
            hit = next((c for c in candidates if same_title(c.title, bid.title)), None)
            if hit is not None:
                w.renotice_bid_id, w.renotice_at, w.updated_at = hit.id, now, now
                out.append(Change(w.bid_id, "renotice"))
    return out


def _reschedule(row: BidResultWatch, bid: Bid, now: datetime) -> None:
    row.checks += 1
    row.next_check_at = plan_next(row, bid, now) or now


async def check_due(
    deps: Deps, now: datetime, limit: int = 200, deadline_s: float = DEADLINE_S
) -> list[Change]:
    """확인할 때가 된 감시를 최근 개찰 순으로 확인하고, 바뀐 것(메일 보낼 것)을 돌려준다.

    deadline_s가 지나면 더 부르지 않는다(남은 공고는 다음 실행). 부른 횟수는 오류가 나도 남긴다.
    """
    changes: list[Change] = []
    stop_at = time.monotonic() + deadline_s
    async with deps.db.session() as s:
        due = await _due(s, now, limit)
    with count_calls() as calls:
        try:
            for w, bid in due:
                if time.monotonic() >= stop_at:
                    log.warning("결과 메일 감시: 시간 상한, 남은 공고는 다음 실행에서")
                    break
                if plan_next(w, bid, now) is None:
                    async with deps.db.transaction() as s:
                        (await s.get_one(BidResultWatch, w.bid_id)).stage = "expired"
                    continue
                try:
                    change = await _check_one(deps, w, bid, now)
                except G2BBudgetExceeded:
                    log.warning("결과 메일 감시: 오늘 G2B 몫을 다 씀, 남은 공고는 다음 실행에서")
                    break
                except Exception as e:  # noqa: BLE001 — 한 공고의 이상한 응답이 나머지를 막지 않게
                    assert deps.g2b is not None
                    log.warning(
                        "결과 메일 감시 실패 %s: %s %s",
                        bid.bid_no,
                        type(e).__name__,
                        deps.g2b.mask(str(e))[:200],
                    )
                    async with deps.db.transaction() as s:
                        _reschedule(await s.get_one(BidResultWatch, w.bid_id), bid, now)
                    continue
                if change is not None:
                    changes.append(change)
        finally:
            if calls.value and deps.g2b is not None:
                async with deps.db.transaction() as s:
                    # cache.source='result_watch': 결과 메일 몫 예산이 이 기록으로 센다
                    s.add(
                        UsageLog(
                            event="collector",
                            g2b_calls=calls.value,
                            cache={"source": RESULT_WATCH_SOURCE},
                        )
                    )
                deps.g2b.settle(calls.value, RESULT_WATCH_SOURCE)
    return changes + await _renotices(deps, now)
