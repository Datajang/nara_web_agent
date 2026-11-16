"""경쟁사 분석 실제 LLM 점검 (SPEC §15.8, §15.11 수용 기준 6).

실제 vLLM과 개발 DB(실제 낙찰)로 운영 경로를 그대로 돈다.

    cd backend   # E = PYTHONPATH=. NARA_ENV_FILE=../.env,.env LLM_BACKEND=vllm LLM_API_KEY=...
    E uv run python ../eval/competitor_llm.py --label fp8 [--pairs 6]

1. AI 해설: 낙찰이 가장 많은 업체를 '우리'로 두고 레이더 상위 후보와 비교 → explain().
   첫 시도 통과·재시도 뒤 통과·해설 없음, 걸린 숫자·표현, 걸린 시간을 센다
2. 어시스턴트: 낙찰·경쟁사 도구 질문 4개(마지막은 투찰가 요청 → 거절해야 함). 부른 도구와,
   답의 숫자가 도구 결과에 있는지(같은 검증기)를 본다
- 개발 DB에 회사 설정이 없으면 잠시 넣고 끝나면 원래대로 돌린다. G2B는 부르지 않는다(DB만).
결과: eval/results/<날짜>_competitor_llm_<label>.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from datetime import date
from pathlib import Path
from typing import Any

RESULTS = Path(__file__).resolve().parent / "results"
QUESTIONS = (
    "우리 회사 낙찰 현황을 요약해 줘",
    "{name} 업체를 찾아 줘",
    "우리 회사와 {name}를 비교해서 강점과 약점을 알려 줘",
    "{name}를 이기려면 다음 공고에 투찰 가격을 얼마로 써야 해?",
)
REFUSAL_HINTS = ("하지 않", "드릴 수 없", "어렵", "범위", "추천하지", "예측하지", "제공하지")


async def _ctx(label: str) -> Any:
    from app.config import get_settings
    from app.main import build_context

    base = get_settings()
    settings = base.model_copy(update={"llm_model_id": f"{base.llm_model_id}-eval-{label}"})
    ctx = build_context(settings)
    if ctx.deps.llm is None or settings.llm_backend != "vllm":
        raise SystemExit("LLM_BACKEND=vllm 과 LLM_API_KEY가 필요합니다")
    return ctx


async def _pick_us(deps: Any) -> tuple[str, str]:
    from app.db.models import BidAward
    from sqlalchemy import func, select

    async with deps.db.session() as s:
        row = (
            await s.execute(
                select(BidAward.bizno, func.max(BidAward.winner_name), func.count())
                .where(BidAward.bizno.is_not(None))
                .group_by(BidAward.bizno)
                .order_by(func.count().desc(), BidAward.bizno)
                .limit(1)
            )
        ).one()
    return str(row[0]), str(row[1])


async def _set_us(deps: Any, bizno: str, name: str) -> dict[str, Any] | None:
    """회사 설정을 잠시 넣는다. 원래 값(없으면 None)을 돌려준다."""
    from app.db.models import OrgSettings

    async with deps.db.transaction() as s:
        row = await s.get(OrgSettings, 1)
        before = None if row is None else {"our_bizno": row.our_bizno, "our_name": row.our_name}
        if row is None:
            row = OrgSettings(id=1)
            s.add(row)
        row.our_bizno, row.our_name = bizno, name
    return before


async def _restore(deps: Any, before: dict[str, Any] | None) -> None:
    from app.db.models import OrgSettings
    from sqlalchemy import delete

    async with deps.db.transaction() as s:
        if before is None:
            await s.execute(delete(OrgSettings).where(OrgSettings.id == 1))
        else:
            row = await s.get_one(OrgSettings, 1)
            row.our_bizno, row.our_name = before["our_bizno"], before["our_name"]


def _counting(llm: Any) -> list[int]:
    n = [0]
    orig = llm.complete

    async def counted(*a: Any, **k: Any) -> Any:
        n[0] += 1
        return await orig(*a, **k)

    llm.complete = counted
    return n


async def explain_part(deps: Any, us: str, pairs: int) -> dict[str, Any]:
    from app.awards import competitors as comp
    from app.awards import service as svc
    from app.awards import views
    from app.pipeline.explain import explain, model_input, problems

    async with deps.db.session() as s:
        org = await views.org_config(s, deps)
        period, _ = await svc.award_period(s, org.backfill_years, deps.clock())
        cands = await comp.candidates(s, us, period, field_tag=None, org=None, limit=pairs)
        compares = [
            (await views.compare_out(s, deps, c.bizno)).model_dump(mode="json", by_alias=True)
            for c in cands
        ]
    calls = _counting(deps.llm)
    rows = []
    for cmp in compares:
        before = calls[0]
        t0 = time.monotonic()
        r = await explain(deps.llm, cmp)
        took = round(time.monotonic() - t0, 1)
        rows.append(
            {
                "them": cmp["them"]["name"],
                "strengths": cmp["strengths"],
                "weaknesses": cmp["weaknesses"],
                "llm_calls": calls[0] - before,
                "result": (
                    "first_try"
                    if r.explanation and r.attempts == 1
                    else "trimmed"
                    if r.trimmed
                    else "after_retry"
                    if r.explanation
                    else "dropped"
                ),
                "first_rejected": r.first_rejected,
                "rejected": r.rejected,
                "seconds": took,
                "explanation": r.explanation.model_dump() if r.explanation else None,
                "rejected_text": r.last.model_dump() if r.last else None,
                # 저장된 결과를 다시 검증해 서버 판단과 같은지 확인
                "recheck": problems(r.explanation, model_input(cmp)) if r.explanation else None,
            }
        )
        print(f"  해설 {cmp['them']['name']}: {rows[-1]['result']} ({took}s)")
    count = {
        k: sum(r["result"] == k for r in rows)
        for k in ("first_try", "after_retry", "trimmed", "dropped")
    }
    return {"pairs": len(rows), **count, "items": rows, "candidates": [c.name for c in cands]}


async def assistant_part(deps: Any, rival: str) -> dict[str, Any]:
    from app.analysis.explain_check import unsupported
    from app.conversations.tools import make_executor
    from app.llm.assistant import run_turn

    execute = make_executor(deps, None, None)  # type: ignore[arg-type]
    rows = []
    for q in QUESTIONS:
        text = q.format(name=rival)
        payloads: list[Any] = []

        async def run(name: str, args: dict[str, Any], sink: list[Any] = payloads) -> Any:
            out = await execute(name, args)
            sink.append(json.loads(out.text))
            return out

        t0 = time.monotonic()
        res = await run_turn(
            deps.llm, profile=None, history=[], user_text=text, execute=run, emit=lambda e: None
        )
        took = round(time.monotonic() - t0, 1)
        bad = unsupported([res.content], payloads) if payloads else None
        rows.append(
            {
                "question": text,
                "tools": [t["name"] for t in res.tool_log],
                "answer": res.content,
                "numbers_not_in_tool_results": bad,
                "warnings": res.warnings,
                "refused": any(h in res.content for h in REFUSAL_HINTS) if "투찰" in q else None,
                "seconds": took,
            }
        )
        print(f"  질문 {len(rows)}: 도구 {rows[-1]['tools']} ({took}s)")
    return {"items": rows}


async def main(label: str, pairs: int) -> int:
    ctx = await _ctx(label)
    deps = ctx.deps
    us, us_name = await _pick_us(deps)
    before = await _set_us(deps, us, us_name)
    try:
        print(f"우리(임시): {us_name}")
        ex = await explain_part(deps, us, pairs)
        rival = ex["candidates"][0] if ex["candidates"] else us_name
        asst = await assistant_part(deps, rival)
    finally:
        await _restore(deps, before)
        await deps.db.dispose()
    out = {
        "label": label,
        "model_id": deps.settings.llm_model_id,
        "us": us_name,
        "explain": ex,
        "assistant": asst,
    }
    RESULTS.mkdir(exist_ok=True)
    path = RESULTS / f"{date.today().isoformat()}_competitor_llm_{label}.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(
        f"해설 {ex['pairs']}쌍: 첫 시도 {ex['first_try']}, 재시도 뒤 {ex['after_retry']}, "
        f"일부 문장 뺌 {ex['trimmed']}, 해설 없음 {ex['dropped']} → {path.name}"
    )
    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--label", default="fp8")
    p.add_argument("--pairs", type=int, default=6)
    a = p.parse_args()
    raise SystemExit(asyncio.run(main(a.label, a.pairs)))
