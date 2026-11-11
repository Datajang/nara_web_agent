"""맞춤 추천 (SPEC §6.4 recommend 흐름, §8.3-7, §8.8-5).

후보 검색(DB-first, 프로필 키워드 OR) → 점수(캐시 우선, 20건 배치) → 점수 내림차순 top_n.
결과는 search_runs(kind=recommend)에 점수·이유와 함께 저장한다(내 기록에서 다시 보기).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from app.db.models import Bid, BidScore, Profile, SearchRun, SearchRunItem
from app.deps import Deps
from app.llm import usage
from app.pipeline.scoring import get_or_create_scores
from app.search.query import SearchQuery
from app.search.service import find_bids

CANDIDATE_MAX = 300  # §7.4: 넘으면 최신 순으로 자른다 [가정]. §8.8-5 성능 목표는 150건 기준


@dataclass
class Recommendation:
    run_id: int
    ranked: list[tuple[Bid, BidScore]]
    candidates: int
    incomplete: bool
    data_as_of: datetime | None


async def recommend(
    deps: Deps,
    user_id: int,
    profile: Profile,
    *,
    days: int,
    source: Literal["regular", "prespec", "all"],
    top_n: int,
    keywords: list[str] | None,
) -> Recommendation:
    usage.status("search", "후보 공고를 찾고 있어요")
    kws = keywords if keywords is not None else [str(k) for k in profile.keywords]
    q = SearchQuery(keywords=kws, match="any", source=source, days=days, status="open")
    found = await find_bids(deps, q, CANDIDATE_MAX)
    usage.set_cache("bids_db", found.cache_hit)
    usage.status("search", f"후보 {len(found.bids)}건을 찾았어요")
    scores = await get_or_create_scores(deps, [b.id for b in found.bids], profile.description)
    ranked = sorted(
        ((b, scores[b.id]) for b in found.bids if b.id in scores),
        key=lambda x: (-x[1].score, -(x[0].notice_at.timestamp() if x[0].notice_at else 0)),
    )[:top_n]
    async with deps.db.transaction() as s:
        run = SearchRun(
            user_id=user_id,
            profile_id=profile.id,
            kind="recommend",
            query={
                "keywords": kws,
                "days": days,
                "source": source,
                "top_n": top_n,
                "candidates": len(found.bids),
            },
            result_count=len(ranked),
            data_as_of=found.data_as_of,
            cache_hit=found.cache_hit,
        )
        s.add(run)
        await s.flush()
        s.add_all(
            SearchRunItem(run_id=run.id, bid_id=b.id, rank=i, score=sc.score, reason=sc.reason)
            for i, (b, sc) in enumerate(ranked, start=1)
        )
    return Recommendation(run.id, ranked, len(found.bids), found.incomplete, found.data_as_of)
