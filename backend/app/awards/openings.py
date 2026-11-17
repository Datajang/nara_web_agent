"""개찰 결과 자동 수집 (P12 '우리 투찰 결과', docs/decisions/2026-11-17-p12a-opening-ranks.md).

업체(사업자번호)로는 이긴 공고만 조회되고 참가업체·순위는 공고번호로 1건씩만 조회된다.
그래서 수집된 낙찰 공고(bid_awards)마다 개찰완료 목록을 한 번씩 받아 두고, 그 안에서 우리
사업자번호를 찾아 낙찰·탈락을 안다.

- incremental: 최근 RECENT(14일) 등록 낙찰 공고 중 아직 안 받은 것
- backfill: 그보다 오래된 공고
- 둘 다 우리가 낙찰한 공고 → 우리 분야 태그·우리가 낙찰한 수요기관 공고 → 나머지 순,
  같은 순위면 최신부터
  (실측: 용역 낙찰 하루 약 240건이라 14일치는 하루 몫 300보다 훨씬 많다)
- 예산은 낙찰 몫과 따로 'openings'(G2B_OPENINGS_DAILY_BUDGET). 몫을 다 쓰면 정상 종료(status ok)하고
  다음 날 이어 받는다. 불러온 공고는 bid_participant_fetches에 표시해 다시 부르지 않는다
  (화면 온디맨드와 공유)
- 공고 하나가 G2B 오류면 건너뛰고(다음 실행에서 다시) 연속 MAX_ERRORS번이면 멈춘다(failed)
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from sqlalchemy import and_, case, exists, func, or_, select, update

from app.awards import participants
from app.collector.runner import RunResult
from app.db.models import BidAward, BidParticipantFetch, CollectorRun, OrgSettings, UsageLog
from app.deps import Deps
from app.g2b.client import OPENINGS_SOURCE, G2BBudgetExceeded, G2BError, count_calls

log = logging.getLogger(__name__)
SOURCE = OPENINGS_SOURCE
RECENT = timedelta(days=14)
MAX_ERRORS = 3
Picked = tuple[str, str, datetime]  # (공고번호, 차수, 등록일시)


async def _our_bizno(deps: Deps) -> str | None:
    async with deps.db.session() as s:
        row = await s.get(OrgSettings, 1)
    return row.our_bizno if row is not None else None


async def pick(deps: Deps, mode: str, limit: int) -> list[Picked]:
    """아직 개찰 결과를 받지 않은 낙찰 공고(차수) 목록(받을 순서)."""
    now = deps.clock()
    us = await _our_bizno(deps)
    a, f = BidAward, BidParticipantFetch
    not_fetched = ~exists().where(f.bid_ntce_no == a.bid_ntce_no, f.bid_ntce_ord == a.bid_ntce_ord)
    since = now - RECENT
    reg = func.max(a.registered_at)
    order = [reg.desc(), a.bid_ntce_no]
    recent = a.registered_at >= since
    conds = [not_fetched, recent if mode == "incremental" else ~recent]
    if us:  # 증분도 같은 순서: 첫날 14일치(약 3,000건)가 하루 몫보다 많아 우리와 관련된 공고부터
        our_orgs = select(BidAward.dminstt_cd).where(
            BidAward.bizno == us, BidAward.dminstt_cd.is_not(None)
        )
        prio = func.max(
            case(
                (a.bizno == us, 2),
                (or_(func.cardinality(a.fields) > 0, a.dminstt_cd.in_(our_orgs)), 1),
                else_=0,
            )
        )
        order = [prio.desc(), *order]
    async with deps.db.session() as s:
        res = await s.execute(
            select(a.bid_ntce_no, a.bid_ntce_ord, reg)
            .where(and_(*conds))
            .group_by(a.bid_ntce_no, a.bid_ntce_ord)
            .order_by(*order)
            .limit(limit)
        )
        return [(no, ord_, r) for no, ord_, r in res.all()]


async def run(deps: Deps, mode: str) -> RunResult:
    if deps.g2b is None:
        return RunResult(status="failed", error="G2B 클라이언트 없음")
    g2b = deps.g2b
    todo = await pick(deps, mode, deps.settings.g2b_openings_daily_budget)
    if not todo:
        return RunResult(status="ok")
    result = RunResult(status="ok")
    async with deps.db.transaction() as s:
        run_row = CollectorRun(
            source=SOURCE,
            mode=mode,
            window_from=min(t[2] for t in todo),
            window_to=max(t[2] for t in todo),
        )
        s.add(run_row)
        await s.flush()
        run_id = run_row.id
    errors = 0
    with count_calls() as calls:
        for no, ord_, _reg in todo:
            try:
                items = await g2b.opening_results(no, ord_, source=SOURCE)
            except G2BBudgetExceeded as e:
                # 하루 몫을 다 쓰면 정상 종료: 남은 공고는 다음 실행에서 이어 받는다
                result.error = g2b.mask(str(e))
                break
            except G2BError as e:
                errors += 1
                log.warning("개찰 결과 수집 실패 %s: %s", no, g2b.mask(str(e)))
                if errors >= MAX_ERRORS:
                    result.status, result.error = "failed", g2b.mask(str(e))
                    break
                continue
            errors = 0
            async with deps.db.transaction() as s:
                await participants.store(s, (no, ord_), items)
            result.fetched += len(items)
            result.inserted += 1  # 개찰 결과를 받은 공고 수
    result.g2b_calls = calls.value
    async with deps.db.transaction() as s:
        await s.execute(
            update(CollectorRun)
            .where(CollectorRun.id == run_id)
            .values(
                status=result.status,
                fetched=result.fetched,
                inserted=result.inserted,
                g2b_calls=result.g2b_calls,
                error=result.error,
                finished_at=func.now(),
            )
        )
        # cache.source='openings': 개찰 결과 몫 예산이 이 기록으로 오늘 호출 수를 센다
        s.add(UsageLog(event="collector", g2b_calls=result.g2b_calls, cache={"source": SOURCE}))
    g2b.settle(result.g2b_calls, SOURCE)
    return result
