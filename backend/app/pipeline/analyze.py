"""상세 분석 (SPEC §5.7 캐시 계약, §8.4·§8.5 analyze_bid). 같은 profile_hash끼리만 공유 (§5.1).

- fit.verdict는 서버가 score에서 다시 계산한다 (80↑ strong, 60~79 possible, 60↓ weak).
- warnings에는 요약의 coverage.warnings를 항상 포함한다.
- requirements의 evidence는 원문에 실제로 있는 문자열만 남긴다.
"""

from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.bids.meta import bid_meta
from app.db.models import Analysis, Bid
from app.deps import Deps
from app.llm import usage
from app.llm.prompts import render
from app.llm.schemas import AnalysisResult, verdict_for
from app.llm.structured import generate
from app.llm.versions import ANALYSIS_PROMPT, prompt_version
from app.pipeline.grounding import ground, unverified_warning
from app.pipeline.singleflight import single_flight
from app.pipeline.summarize import (
    _dedupe,
    _llm,
    check_evidence,
    get_or_create_summary,
    known_source,
    source_inputs,
)
from app.profiles.hashing import normalize_profile, profile_hash

VERDICT_KO = {"strong": "적합", "possible": "검토 필요", "weak": "낮음"}
SEVERITY_KO = {"high": "높음", "mid": "중간", "low": "낮음"}


def _bullets(items: list[str]) -> str:
    return "\n".join(f"- {x}" for x in items) if items else "- 문서에서 확인되지 않음"


def render_markdown(r: AnalysisResult) -> str:
    """§7.5 화면 순서와 같은 순서의 마크다운 (내보내기·북마크 미리보기용)."""
    reqs = [f"{x.text}" + (f" (근거: {x.source})" if x.source else "") for x in r.requirements]
    evals = [
        f"{e.name}"
        + (f": {e.points:g}점" if e.points is not None else "")
        + (f" — {e.note}" if e.note else "")
        for e in r.evaluation.items
    ]
    sched = [f"{s.label}: {s.date or s.raw or '미정'}" for s in r.schedule]
    bc = r.budget_contract
    money = [
        f"{label}: {value}"
        for label, value in (
            ("예산", bc.budget_text),
            ("계약 방법", bc.contract_method),
            ("대금 지급", bc.payment_terms),
            ("기간", bc.period),
        )
        if value
    ]
    risks = [f"[{SEVERITY_KO[x.severity]}] {x.text}" for x in r.risks]
    fit = r.fit
    parts = [
        f"## 사업 개요\n{r.overview}",
        f"## 핵심 요구사항\n{_bullets(reqs)}",
        "## 평가 기준·배점\n"
        + (f"방식: {r.evaluation.method}\n" if r.evaluation.method else "")
        + _bullets(evals),
        f"## 일정\n{_bullets(sched)}",
        f"## 예산·계약 조건\n{_bullets(money)}",
        f"## 리스크·유의사항\n{_bullets(risks)}",
        f"## 우리 팀 적합도\n**{fit.score}점 ({VERDICT_KO[fit.verdict]})** {fit.reasoning}\n\n"
        f"강점\n{_bullets(fit.strengths)}\n\n보완할 점\n{_bullets(fit.gaps)}",
        f"## 다음 할 일\n{_bullets(r.next_actions)}",
    ]
    if r.warnings:
        parts.append(f"## 확인이 필요한 점\n{_bullets(r.warnings)}")
    return "\n\n".join(parts) + "\n"


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

    if (cached := await check()) is not None:
        usage.set_cache("analysis", True)
        return cached, True
    usage.status("analyze", "프로필과 비교해 분석하고 있어요", cache=False)

    async def compute() -> Analysis:
        async with deps.db.session() as s:
            bid = await s.get_one(Bid, bid_id)
        msgs = render(
            "analyze_bid",
            profile_description=normalize_profile(profile_text),
            meta=json.dumps(bid_meta(bid), ensure_ascii=False),
            bid_summary_json=json.dumps(summary.summary, ensure_ascii=False),
        )
        result = await generate(llm, "analyze_bid", msgs, AnalysisResult)
        _, docs, _ = await source_inputs(deps, bid)
        check_evidence(result.requirements, [d.text for d in docs], None)
        names = [d.name for d in docs]
        for r in result.requirements:
            r.source = known_source(r.source, names)
        for k in result.risks:
            k.source = known_source(k.source, names)
        removed = ground(
            result, [*(d.text for d in docs), json.dumps(bid_meta(bid), ensure_ascii=False)]
        )
        result.fit.verdict = verdict_for(result.fit.score)
        cov_warnings = summary.summary.get("coverage", {}).get("warnings", [])
        mine = [unverified_warning(removed)] if removed else []
        result.warnings = _dedupe([*result.warnings, *mine, *cov_warnings])
        async with deps.db.transaction() as s:
            await s.execute(
                insert(Analysis)
                .values(
                    bid_id=bid_id,
                    summary_id=summary.id,
                    profile_hash=ph,
                    prompt_version=pv,
                    model_id=llm.model_id,
                    result=result.model_dump(mode="json"),
                    markdown=render_markdown(result),
                )
                .on_conflict_do_nothing(
                    constraint="uq_analyses_bid_id_summary_id_profile_hash_prompt_version"
                )
            )
        row = await check()
        assert row is not None
        return row

    row, hit = await single_flight(
        deps.db,
        f"analysis:{bid_id}:{summary.id}:{ph}:{pv}",
        check,
        compute,
        wait_s=deps.settings.llm_lock_wait_s,
    )
    usage.set_cache("analysis", hit)
    return row, hit
