"""적합도 점수 캐시 계약 (SPEC §5.7, §5.1).

- 키 (bid_id, profile_hash, prompt_version). bid_content_hash가 bids.content_hash와 다르면 stale로
  재평가.
- 캐시에 없는 공고만 모아 20건씩 LLM에 보낸다 [가정]. 배치 하나가 실패해도 나머지는 계속.
- P1은 점수에 single-flight를 걸지 않는다: upsert가 경쟁을 흡수하고, 최악은 같은 배치의 중복 LLM
  호출.
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.db.models import Bid, BidScore
from app.deps import Deps
from app.llm.versions import SCORE_PROMPT, bid_ref, parse_bid_ref, prompt_version
from app.pipeline.summarize import _llm
from app.profiles.hashing import normalize_profile, profile_hash

log = logging.getLogger(__name__)
BATCH = 20


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
    todo = [i for i in bid_ids if i in bids and i not in fresh]
    for n in range(0, len(todo), BATCH):
        batch = todo[n : n + BATCH]
        payload = {
            "profile": normalize_profile(profile_text),
            "bids": [
                {"bid_id": bid_ref(i), "title": bids[i].title, "org": bids[i].org_name}
                for i in batch
            ],
        }
        try:
            res = await llm.complete_json("score", payload)
        except Exception:  # 배치 실패는 기록만 하고 다음 배치로 (§5.7)
            log.exception("점수 배치 실패 (%d건)", len(batch))
            continue
        values = []
        for item in res.data.get("scores", []):
            bid_id = parse_bid_ref(item.get("bid_id"))
            if bid_id not in batch:  # 존재하지 않거나 요청하지 않은 ID는 버린다
                continue
            values.append(
                {
                    "bid_id": bid_id,
                    "profile_hash": ph,
                    "prompt_version": pv,
                    "bid_content_hash": bids[bid_id].content_hash,
                    "model_id": llm.model_id,
                    "score": max(0, min(100, int(item.get("score", 0)))),
                    "reason": str(item.get("reason", "")),
                }
            )
        if values:
            stmt = insert(BidScore).values(values)
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
    _, fresh = await load()
    return fresh
