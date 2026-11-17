"""우리 투찰 결과(낙찰·탈락) API (P12, docs/decisions/2026-11-17-p12a-opening-ranks.md).

- GET /my-bids: 우리가 낙찰했거나 개찰 결과에 우리가 있는 공고. 결과·순위·낙찰업체
- GET /my-bids/{no}/{ord}/{clsfc}/{rbid}: 공고 하나의 참가업체 전체(순위·투찰·점수·비고)와
  업체별 낙찰 수.
  개찰 결과가 아직 없으면 그 공고만 온디맨드로 1회 부른다(낙찰 몫, P11과 같은 캐시)
투찰가 추천·낙찰 가능성은 내지 않는다(§15.1 비목표).
"""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Path, Query

from app.api.deps import ActiveUser, Ctx, DbSession
from app.api.schemas.mybids import (
    MyBidCountsOut,
    MyBidDetailOut,
    MyBidListOut,
    MyBidOut,
    MyBidParticipantOut,
    OpeningScanOut,
)
from app.awards import mybids as mb
from app.awards import participants as parts
from app.awards import service as svc
from app.awards import views
from app.errors import ApiError

router = APIRouter(tags=["mybids"])
KeyPart = Annotated[str, Path(pattern=r"^[0-9A-Za-z]{1,20}$")]


def _f(v: object) -> float | None:
    return float(v) if v is not None else None  # type: ignore[arg-type]


def item_out(i: mb.MyBid, us: str) -> MyBidOut:
    a, u = i.award, i.us
    return MyBidOut(
        bid_ntce_no=a.bid_ntce_no,
        bid_ntce_ord=a.bid_ntce_ord,
        bid_clsfc_no=a.bid_clsfc_no,
        rbid_no=a.rbid_no,
        title=a.title,
        dminstt_name=a.dminstt_name,
        registered_at=a.registered_at,
        opened_at=a.opened_at,
        result=i.result(us),
        our_rank=u.rank if u else None,
        valid_count=i.valid_count,
        participant_count=i.rows if i.rows else a.participant_count,
        our_bid_amount=u.bid_amount if u else None,
        our_bid_rate=_f(u.bid_rate) if u else None,
        our_total_score=_f(u.total_score) if u else None,
        remark=u.remark if u else None,
        winner_bizno=a.bizno,
        winner_name=a.winner_name,
        award_amount=a.award_amount,
        fetched=i.fetched,
        bid_id=f"b{i.bid_id}" if i.bid_id is not None else None,
    )


@router.get("/my-bids")
async def list_my_bids(
    _: ActiveUser,
    s: DbSession,
    ctx: Ctx,
    result: Annotated[Literal["all", "won", "lost"], Query()] = "all",
    cursor: Annotated[str | None, Query(max_length=200)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
) -> MyBidListOut:
    _org, us, _name = await views.us_config(s, ctx.deps)
    cur = None
    if cursor:
        cur = svc.decode_cursor(cursor)
        if cur is None:
            raise ApiError(
                400, "bad_request", "목록 위치가 올바르지 않아요. 처음부터 다시 불러와 주세요."
            )
    items, nxt = await mb.page(s, us, result, cur, limit)
    counts = await mb.counts(s, us)
    since, done, total = await mb.scan_status(s)
    return MyBidListOut(
        items=[item_out(i, us) for i in items],
        next_cursor=svc.encode_cursor(*nxt) if nxt else None,
        counts=MyBidCountsOut(**counts),
        scan=OpeningScanOut(since=since, fetched_notices=done, award_notices=total),
    )


@router.get("/my-bids/{no}/{ord}/{clsfc}/{rbid}")
async def get_my_bid(
    no: KeyPart,
    ord: KeyPart,
    clsfc: KeyPart,
    rbid: KeyPart,
    user: ActiveUser,
    s: DbSession,
    ctx: Ctx,
) -> MyBidDetailOut:
    ctx.limiter.hit(f"my-bid:{user.id}", 30, 60)
    _org, us, _name = await views.us_config(s, ctx.deps)
    key = (no, ord, clsfc, rbid)
    item = await mb.one(s, us, key)
    if item is None:
        raise ApiError(404, "not_found", "낙찰 정보를 찾지 못했어요.")
    budget_exhausted = failed = False
    if not item.fetched:
        await s.commit()  # 온디맨드 채우기는 별도 세션·트랜잭션
        ensured = await parts.ensure(ctx.deps, [(no, ord)], user.id, max_calls=1)
        budget_exhausted, failed = ensured.budget_exhausted, ensured.failed
        item = await mb.one(s, us, key) or item
    rows = await mb.participants(s, key) if item.fetched else None
    counts = await mb.award_counts(s, [r.bizno for r in rows or []])
    a = item.award
    return MyBidDetailOut(
        item=item_out(item, us),
        estimated_price=a.estimated_price,
        award_ratio=_f(a.award_ratio),
        g2b_award_rate=_f(a.g2b_award_rate),
        is_joint=a.is_joint,
        participants=None
        if rows is None
        else [
            MyBidParticipantOut(
                rank=r.rank,
                bizno=r.bizno,
                name=r.name,
                bid_amount=r.bid_amount,
                bid_rate=_f(r.bid_rate),
                tech_score=_f(r.tech_score),
                price_score=_f(r.price_score),
                total_score=_f(r.total_score),
                remark=r.remark,
                is_winner=r.bizno == a.bizno,
                is_us=r.bizno == us,
                award_count=counts.get(r.bizno, 0),
            )
            for r in rows
        ],
        budget_exhausted=budget_exhausted,
        failed=failed,
    )
