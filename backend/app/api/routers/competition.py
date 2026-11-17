"""GET /api/v1/bids/{bid_id}/competition — 공고 상세 '경쟁 구도' (SPEC §15.6·§15.7, P11).

DB(낙찰)를 읽고, 참가 업체 점수만 개찰완료 목록을 온디맨드로 부른다(한 요청 새 호출 6회까지).
투찰가 추천·낙찰 가능성은 내지 않는다(§15.1 비목표).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query
from sqlalchemy import literal, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.common import load_bid
from app.api.deps import ActiveUser, Ctx, DbSession
from app.api.schemas.competition import (
    CompetitionAwardOut,
    CompetitionDistributionOut,
    CompetitionOrgOut,
    CompetitionOut,
    CompetitionUsOut,
    ParticipantOut,
    ParticipantsStatusOut,
    SpreadOut,
)
from app.awards import competition as cp
from app.awards import participants as parts
from app.awards import service as svc
from app.awards import views
from app.db.models import Bid, BidAward, BidParticipant
from app.llm.versions import bid_ref

router = APIRouter(tags=["competition"])


def _f(v: object) -> float | None:
    return float(v) if v is not None else None  # type: ignore[arg-type]


def _spread(sp: cp.Spread | None) -> SpreadOut | None:
    return SpreadOut(n=sp.n, min=sp.min, median=sp.median, max=sp.max) if sp else None


async def _bid_ids(s: AsyncSession, nos: list[str]) -> dict[str, int]:
    if not nos:
        return {}
    rows = await s.execute(
        select(Bid.bid_no, Bid.id).where(
            Bid.bid_key.in_([f"regular:{n}" for n in set(nos)]), Bid.source == literal("regular")
        )
    )
    return {no: i for no, i in rows.all()}


def _award_out(
    a: BidAward,
    sim: float | None,
    plist: list[BidParticipant] | None,
    us: str | None,
    bid_ids: dict[str, int],
) -> CompetitionAwardOut:
    participants = (
        [
            ParticipantOut(
                rank=p.rank,
                bizno=p.bizno,
                name=p.name,
                bid_amount=p.bid_amount,
                bid_rate=_f(p.bid_rate),
                tech_score=_f(p.tech_score),
                price_score=_f(p.price_score),
                total_score=_f(p.total_score),
                remark=p.remark,
                is_winner=p.bizno == a.bizno,
                is_us=us is not None and p.bizno == us,
            )
            for p in plist
        ]
        if plist is not None
        else None
    )
    bid_id = bid_ids.get(a.bid_ntce_no)
    return CompetitionAwardOut(
        bid_ntce_no=a.bid_ntce_no,
        bid_ntce_ord=a.bid_ntce_ord,
        title=a.title,
        bizno=a.bizno,
        winner_name=a.winner_name,
        award_amount=a.award_amount,
        g2b_award_rate=_f(a.g2b_award_rate),
        award_ratio=_f(a.award_ratio),
        participant_count=a.participant_count,
        registered_at=a.registered_at,
        is_joint=a.is_joint,
        bid_id=bid_ref(bid_id) if bid_id is not None else None,
        similarity=sim,
        participants=participants,
        us_participated=bool(participants and any(p.is_us for p in participants)),
    )


@router.get("/bids/{bid_id}/competition")
async def get_competition(
    bid_id: str,
    user: ActiveUser,
    s: DbSession,
    ctx: Ctx,
    limit: Annotated[int, Query(ge=1, le=10)] = 5,
) -> CompetitionOut:
    ctx.limiter.hit(f"competition:{user.id}", 30, 60)
    bid = await load_bid(s, bid_id)
    deps = ctx.deps
    org = await views.org_config(s, deps)
    period, _cov = await svc.award_period(s, org.backfill_years, deps.clock())
    target = cp.target_of(bid)
    this = await cp.this_awards(s, target)
    similar = await cp.similar_awards(s, target, period, org.field_keywords)
    shown = similar[:limit]
    rate, ratio = cp.distributions(similar)
    await s.commit()  # 온디맨드 채우기는 별도 세션·트랜잭션

    ensured = await parts.ensure(deps, cp.notices_to_load(this, shown), user.id)

    keys = [cp.key_of(a) for a in this[:1]] + [cp.key_of(r.award) for r in shown]
    plists = await cp.participants_of(s, keys)
    loaded = await parts.fetched(s, [(k[0], k[1]) for k in keys])
    bid_ids = await _bid_ids(s, [k[0] for k in keys])
    us = org.our_bizno

    def plist(a: BidAward) -> list[BidParticipant] | None:
        if (a.bid_ntce_no, a.bid_ntce_ord) not in loaded:
            return None
        return plists.get(cp.key_of(a), [])

    us_out = None
    if us is not None:
        h = await cp.us_history(s, target, period, us)
        us_out = CompetitionUsOut(
            bizno=us,
            name=org.our_name or us,
            org_awards=h.org_awards,
            participated=h.participated,
            won=h.won,
        )
    return CompetitionOut(
        bid_id=bid_ref(bid.id),
        org=CompetitionOrgOut(code=target.org_cd, name=target.org_name),
        period=views.period_out(period),
        this_award=_award_out(this[0], None, plist(this[0]), us, bid_ids) if this else None,
        similar=[_award_out(r.award, r.score, plist(r.award), us, bid_ids) for r in shown],
        similar_total=len(similar),
        distribution=CompetitionDistributionOut(
            g2b_rate=_spread(rate), award_ratio=_spread(ratio), basis=len(similar)
        ),
        participants_status=ParticipantsStatusOut(
            requested=ensured.requested,
            loaded=ensured.loaded,
            fetched_now=ensured.fetched_now,
            partial=ensured.partial,
            failed=ensured.failed,
            budget_exhausted=ensured.budget_exhausted,
        ),
        us=us_out,
    )
