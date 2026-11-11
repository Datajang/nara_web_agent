"""적합도 점수 (SPEC §5.7 캐시 계약, §8.3-7 입력, §8.4 ScoreBatch).

- 키 (bid_id, profile_hash, prompt_version). bid_content_hash가 bids.content_hash와 다르면 stale.
- 캐시에 없는 공고만 20건씩 배치. 배치들은 병렬(클라이언트 세마포어가 동시 수 제한).
- 응답에 빠진 bid_id만 한 번 더 요청하고, 요청하지 않은 ID는 버린다 (§8.4, §8.7).
- 배치 하나가 실패해도 나머지는 계속. 전부 LLM 불가로 실패하면 LLMUnavailable.
- 입력은 공고 메타와, 이미 있으면 요약 headline만 (첨부를 읽지 않음).
"""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.bids.meta import budget_text, kst_text
from app.db.models import Bid, BidScore, BidSummary
from app.deps import Deps
from app.llm import usage
from app.llm.base import LLMClient, LLMError, LLMInvalidOutput, LLMUnavailable
from app.llm.prompts import render
from app.llm.schemas import ScoreBatch, ScoreItem
from app.llm.structured import generate
from app.llm.versions import SCORE_PROMPT, SUMMARY_PROMPT, bid_ref, parse_bid_ref, prompt_version
from app.pipeline.summarize import _llm
from app.profiles.hashing import normalize_profile, profile_hash

log = logging.getLogger(__name__)
BATCH = 20


async def _headlines(deps: Deps, ids: list[int], model_id: str) -> dict[int, str]:
    pv = prompt_version(SUMMARY_PROMPT, model_id)
    async with deps.db.session() as s:
        rows = (
            await s.execute(
                select(BidSummary.bid_id, BidSummary.summary["headline"].astext)
                .where(BidSummary.bid_id.in_(ids), BidSummary.prompt_version == pv)
                .order_by(BidSummary.id)
            )
        ).all()
    return {bid_id: h for bid_id, h in rows if h}


async def _ask(
    llm: LLMClient, profile: str, bids: dict[int, Bid], heads: dict[int, str], ids: list[int]
) -> dict[int, ScoreItem]:
    lines = "\n".join(
        f"[{bid_ref(i)}] 제목: {bids[i].title} / 기관: {bids[i].org_name or '미상'} / "
        f"예산: {budget_text(bids[i].budget)} / 마감: {kst_text(bids[i].deadline_at)} / "
        f"요약: {heads.get(i, '없음')}"
        for i in ids
    )
    msgs = render("score_bids", profile_description=profile, bids=lines)
    try:
        out = await generate(llm, "score_bids", msgs, ScoreBatch)
    except LLMInvalidOutput:
        usage.warn(f"점수 형식 오류로 {len(ids)}건 건너뜀")
        return {}
    got: dict[int, ScoreItem] = {}
    for item in out.scores:
        bid_id = parse_bid_ref(item.bid_id)
        if bid_id in ids and bid_id not in got:  # 요청하지 않은 ID·중복은 버린다
            got[bid_id] = item
    return got


async def get_or_create_scores(
    deps: Deps, bid_ids: list[int], profile_text: str
) -> dict[int, BidScore]:
    llm = _llm(deps)
    ph = profile_hash(profile_text)
    pv = prompt_version(SCORE_PROMPT, llm.model_id)

    async def load() -> tuple[dict[int, Bid], dict[int, BidScore]]:
        async with deps.db.session() as s:
            bids = {
                b.id: b for b in (await s.execute(select(Bid).where(Bid.id.in_(bid_ids)))).scalars()
            }
            rows = (
                await s.execute(
                    select(BidScore).where(
                        BidScore.bid_id.in_(bid_ids),
                        BidScore.profile_hash == ph,
                        BidScore.prompt_version == pv,
                    )
                )
            ).scalars()
        fresh = {
            r.bid_id: r
            for r in rows
            if r.bid_id in bids and r.bid_content_hash == bids[r.bid_id].content_hash
        }
        return bids, fresh

    bids, fresh = await load()
    todo = [i for i in dict.fromkeys(bid_ids) if i in bids and i not in fresh]
    usage.set_cache("score", not todo)
    if not todo:
        return fresh
    profile = normalize_profile(profile_text)
    heads = await _headlines(deps, todo, llm.model_id)
    total = len(bids)
    done = total - len(todo)
    usage.status("score", "적합도 점수를 매기고 있어요", progress={"done": done, "total": total})
    errors: list[LLMError] = []

    async def run(batch: list[int]) -> None:
        nonlocal done
        try:
            got = await _ask(llm, profile, bids, heads, batch)
            missing = [i for i in batch if i not in got]
            if missing:
                got.update(await _ask(llm, profile, bids, heads, missing))
        except LLMError as e:  # 배치 실패는 기록만 하고 다음 배치로 (§5.7)
            log.warning("점수 배치 실패 (%d건): %s", len(batch), type(e).__name__)
            errors.append(e)
            got = {}
        if got:
            stmt = insert(BidScore).values(
                [
                    {
                        "bid_id": i,
                        "profile_hash": ph,
                        "prompt_version": pv,
                        "bid_content_hash": bids[i].content_hash,
                        "model_id": llm.model_id,
                        "score": item.score,
                        "reason": item.reason[:80],
                    }
                    for i, item in got.items()
                ]
            )
            async with deps.db.transaction() as s:
                await s.execute(
                    stmt.on_conflict_do_update(
                        constraint="uq_bid_scores_bid_id_profile_hash_prompt_version",
                        set_={
                            "score": stmt.excluded.score,
                            "reason": stmt.excluded.reason,
                            "bid_content_hash": stmt.excluded.bid_content_hash,
                            "model_id": stmt.excluded.model_id,
                        },
                    )
                )
        done += len(batch)
        usage.status(
            "score", "적합도 점수를 매기고 있어요", progress={"done": done, "total": total}
        )

    batches = [todo[n : n + BATCH] for n in range(0, len(todo), BATCH)]
    await asyncio.gather(*(run(b) for b in batches))
    if len(errors) == len(batches) and all(isinstance(e, LLMUnavailable) for e in errors):
        raise LLMUnavailable("score_bids")
    _, fresh = await load()
    return fresh
