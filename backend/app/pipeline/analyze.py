"""상세 분석 캐시 계약 (SPEC §5.7). 같은 profile_hash끼리만 공유 (§5.1)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.db.models import Analysis
from app.deps import Deps
from app.llm.versions import ANALYSIS_PROMPT, bid_ref, prompt_version
from app.pipeline.singleflight import single_flight
from app.pipeline.summarize import _llm, get_or_create_summary
from app.profiles.hashing import normalize_profile, profile_hash


async def get_or_create_analysis(
    deps: Deps, bid_id: int, profile_text: str
) -> tuple[Analysis, bool]:
    llm = _llm(deps)
    summary, _ = await get_or_create_summary(deps, bid_id)
    ph = profile_hash(profile_text)
    pv = prompt_version(ANALYSIS_PROMPT, llm.model_id)
    where = (
        Analysis.bid_id == bid_id,
        Analysis.summary_id == summary.id,
        Analysis.profile_hash == ph,
        Analysis.prompt_version == pv,
    )

    async def check() -> Analysis | None:
        async with deps.db.session() as s:
            return (await s.execute(select(Analysis).where(*where))).scalar_one_or_none()

    async def compute() -> Analysis:
        res = await llm.complete_json(
            "analysis",
            {
                "bid": bid_ref(bid_id),
                "summary": summary.summary,
                "profile": normalize_profile(profile_text),
            },
        )
        async with deps.db.transaction() as s:
            await s.execute(
                insert(Analysis)
                .values(
                    bid_id=bid_id,
                    summary_id=summary.id,
                    profile_hash=ph,
                    prompt_version=pv,
                    model_id=llm.model_id,
                    result=res.data,
                    markdown=str(res.data.get("markdown", "")),
                )
                .on_conflict_do_nothing(
                    constraint="uq_analyses_bid_id_summary_id_profile_hash_prompt_version"
                )
            )
        row = await check()
        assert row is not None
        return row

    return await single_flight(deps.db, f"analysis:{bid_id}:{summary.id}:{ph}:{pv}", check, compute)
