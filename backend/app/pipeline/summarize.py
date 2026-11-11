"""공통 요약 캐시 계약 (SPEC §5.7). 프로필과 무관하며 모든 사용자가 공유한다.

source_hash = 이 공고의 rfp·spec 중 ok 파일 sha256을 정렬해 이어 붙인 값의 sha256.
읽을 파일이 없으면 `meta-only:{bids.content_hash}` (정정공고면 해시가 바뀌어 새 요약).
"""

from __future__ import annotations

import hashlib

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.db.models import Bid, BidFile, BidSummary, FileText
from app.deps import Deps
from app.files.store import ensure_bid_files
from app.llm.base import LLMClient
from app.llm.versions import SUMMARY_PROMPT, bid_ref, prompt_version
from app.pipeline.singleflight import single_flight

SCANNED_THRESHOLD = 200  # §5.6-8: 이보다 짧으면 스캔본일 가능성


def _llm(deps: Deps) -> LLMClient:
    if deps.llm is None:
        raise RuntimeError("LLM 클라이언트가 없습니다")
    return deps.llm


async def source_inputs(deps: Deps, bid: Bid) -> tuple[str, list[str]]:
    async with deps.db.session() as s:
        found = (
            await s.execute(
                select(BidFile.sha256).where(
                    BidFile.bid_id == bid.id,
                    BidFile.status == "ok",
                    BidFile.kind.in_(("rfp", "spec")),
                )
            )
        ).scalars()
        shas = sorted({x for x in found if x})
        if not shas:
            return f"meta-only:{bid.content_hash}", []
        texts = dict(
            (
                await s.execute(
                    select(FileText.sha256, FileText.text).where(FileText.sha256.in_(shas))
                )
            ).all()
        )
    return hashlib.sha256("".join(shas).encode()).hexdigest(), [texts.get(x, "") for x in shas]


async def get_or_create_summary(deps: Deps, bid_id: int) -> tuple[BidSummary, bool]:
    llm = _llm(deps)
    await ensure_bid_files(deps, bid_id)
    async with deps.db.session() as s:
        bid = await s.get(Bid, bid_id)
    if bid is None:
        raise LookupError(f"공고 없음: {bid_id}")
    source_hash, texts = await source_inputs(deps, bid)
    pv = prompt_version(SUMMARY_PROMPT, llm.model_id)
    where = (
        BidSummary.bid_id == bid_id,
        BidSummary.source_hash == source_hash,
        BidSummary.prompt_version == pv,
    )

    async def check() -> BidSummary | None:
        async with deps.db.session() as s:
            return (await s.execute(select(BidSummary).where(*where))).scalar_one_or_none()

    async def compute() -> BidSummary:
        text = "\n\n".join(texts)
        res = await llm.complete_json(
            "summary",
            {
                "bid": bid_ref(bid_id),
                "title": bid.title,
                "org": bid.org_name,
                "budget": bid.budget,
                "deadline": bid.deadline_at.isoformat() if bid.deadline_at else None,
                "text": text,
                "unreadable": bool(texts) and len(text) < SCANNED_THRESHOLD,
            },
        )
        async with deps.db.transaction() as s:
            await s.execute(
                insert(BidSummary)
                .values(
                    bid_id=bid_id,
                    source_hash=source_hash,
                    prompt_version=pv,
                    model_id=llm.model_id,
                    summary=res.data,
                    input_tokens=res.prompt_tokens,
                    output_tokens=res.completion_tokens,
                )
                .on_conflict_do_nothing(
                    constraint="uq_bid_summaries_bid_id_source_hash_prompt_version"
                )
            )
        row = await check()
        assert row is not None
        return row

    return await single_flight(deps.db, f"summary:{bid_id}:{source_hash}:{pv}", check, compute)
