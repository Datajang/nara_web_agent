"""P12-a 개찰 결과 순위 빈칸 확인 (getOpengResultListInfoOpengCompt). 읽기 전용 확인 스크립트.

질문: 참가업체별 개찰순위(opengRank)가 얼마나 비는가, 빈 행은 왜 비는가(비고 rmrk·낙찰방법),
순위 대신 쓸 값(투찰금액·투찰률·종합점수)은 있는가.

- 표본: 최근 45일 용역 낙찰 중 협상계약(낙찰방법명에 '협상') N/2 + 그 밖 N/2
  (bids와 이어지는 공고 우선)
- 호출은 MAX_CALLS(60)회를 넘지 않는다. 앱 예산(usage_logs)과 별도로 센다(확인용).
- 개인정보(대표자명 등)는 읽지 않고, 결과는 집계만 출력한다. 사업자번호·업체명도 남기지 않는다.

실행: uv run python -m scripts.probe_ranks --env-file ../.env --env-file .env [--n 40]
      [--out <저장소 밖 json>]
"""

from __future__ import annotations

import argparse
import asyncio
import json
from collections import Counter
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import httpx
from dotenv import dotenv_values
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.g2b.client import G2BClient

MAX_CALLS = 60
SAMPLE_SQL = """
SELECT no, ord, mthd, no_rate FROM (
  SELECT DISTINCT ON (a.bid_ntce_no, a.bid_ntce_ord)
         a.bid_ntce_no AS no, a.bid_ntce_ord AS ord,
         coalesce(b.raw->>'sucsfbidMthdNm', '') AS mthd, a.g2b_award_rate IS NULL AS no_rate
  FROM bid_awards a LEFT JOIN bids b ON b.bid_no = a.bid_ntce_no AND b.source = 'regular'
  WHERE a.registered_at > now() - interval '45 days'
  ORDER BY a.bid_ntce_no, a.bid_ntce_ord
) t
ORDER BY (mthd = ''), md5(no)
LIMIT 3000
"""


def _num(v: Any) -> Decimal | None:
    s = str(v or "").replace(",", "").strip()
    try:
        return Decimal(s) if s else None
    except InvalidOperation:
        return None


def pick(rows: list[Any], n: int) -> list[tuple[str, str, str, str]]:
    """협상 n/2 + 그 밖 n/2. 낙찰방법을 모르면 낙찰률(G2B) 빈칸을 협상 추정으로 쓴다."""
    nego, other = [], []
    for no, ord_, mthd, no_rate in rows:
        kind = ("협상" in mthd) if mthd else bool(no_rate)
        label = "협상" if kind else "그 밖"
        (nego if kind else other).append((no, ord_, mthd or f"(모름, {label} 추정)", label))
    return nego[: n // 2] + other[: n - n // 2]


def notice_stats(items: list[dict[str, Any]]) -> dict[str, Any]:
    ranked = [i for i in items if str(i.get("opengRank") or "").strip()]
    blank = [i for i in items if not str(i.get("opengRank") or "").strip()]
    ranks = sorted(int(_num(i["opengRank"]) or 0) for i in ranked)
    return {
        "rows": len(items),
        "ranked": len(ranked),
        "blank": len(blank),
        # 순위가 1..k로 앞에서부터 채워졌나(상위 몇 곳만 순위를 주는지)
        "ranks_are_prefix": ranks == list(range(1, len(ranks) + 1)),
        "rmrk_ranked": Counter(str(i.get("rmrk") or "(빈칸)").strip() for i in ranked),
        "rmrk_blank": Counter(str(i.get("rmrk") or "(빈칸)").strip() for i in blank),
        "blank_has_amount": sum(_num(i.get("bidprcAmt")) is not None for i in blank),
        "blank_has_rate": sum(_num(i.get("bidprcrt")) is not None for i in blank),
        "has_total_score": sum(_num(i.get("totalEvlAmtVal")) is not None for i in items),
        "ranked_has_total_score": sum(_num(i.get("totalEvlAmtVal")) is not None for i in ranked),
    }


async def run(key: str, db_url: str, n: int) -> dict[str, Any]:
    eng = create_async_engine(db_url)
    async with eng.connect() as c:
        rows = (await c.execute(text(SAMPLE_SQL))).all()
    await eng.dispose()
    sample = pick(list(rows), n)
    out: dict[str, Any] = {"sample": len(sample), "calls": 0, "by_kind": {}}
    async with httpx.AsyncClient() as http:
        client = G2BClient(http, {"opening_compt": key})
        for no, ord_, mthd, label in sample:
            if out["calls"] >= MAX_CALLS:
                break
            out["calls"] += 1
            try:
                items = await client.opening_results(no, ord_)
            except Exception as e:  # 확인용: 오류도 집계
                k = out["by_kind"].setdefault(label, {"notices": [], "errors": Counter()})
                k["errors"][type(e).__name__] += 1
                continue
            k = out["by_kind"].setdefault(label, {"notices": [], "errors": Counter()})
            st = notice_stats(items)
            st["mthd"] = mthd
            k["notices"].append(st)
    for k in out["by_kind"].values():
        ns = k["notices"]
        k["summary"] = {
            "notices": len(ns),
            "empty_notices": sum(s["rows"] == 0 for s in ns),
            "rows": sum(s["rows"] for s in ns),
            "blank_rows": sum(s["blank"] for s in ns),
            "notices_all_ranked": sum(s["rows"] > 0 and s["blank"] == 0 for s in ns),
            "notices_no_rank": sum(s["rows"] > 0 and s["ranked"] == 0 for s in ns),
            "ranks_are_prefix": sum(s["ranked"] > 0 and s["ranks_are_prefix"] for s in ns),
            "blank_has_amount": sum(s["blank_has_amount"] for s in ns),
            "blank_has_rate": sum(s["blank_has_rate"] for s in ns),
            "rows_with_total_score": sum(s["has_total_score"] for s in ns),
            "rmrk_ranked": sum((s["rmrk_ranked"] for s in ns), Counter()).most_common(8),
            "rmrk_blank": sum((s["rmrk_blank"] for s in ns), Counter()).most_common(8),
            "methods": Counter(s["mthd"] for s in ns).most_common(6),
        }
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--env-file", action="append", required=True)
    ap.add_argument("--n", type=int, default=40)
    ap.add_argument("--out", help="전체 결과 json(저장소 밖)")
    a = ap.parse_args()
    env: dict[str, Any] = {}
    for f in a.env_file:
        env.update({k: v for k, v in dotenv_values(f).items() if v})
    key = env.get("NARA_AWARD_API_KEY") or env.get("NARA_API_KEY") or ""
    rep = asyncio.run(run(key, env["DATABASE_URL"], min(a.n, MAX_CALLS)))
    full = json.dumps(rep, ensure_ascii=False, indent=1, default=str).replace(key or "\0", "***")
    if a.out:
        Path(a.out).write_text(full, encoding="utf-8")
    summary = {k: v["summary"] | {"errors": v["errors"]} for k, v in rep["by_kind"].items()}
    print(json.dumps(summary, ensure_ascii=False, indent=1, default=str))
    print(f"G2B calls={rep['calls']} (상한 {MAX_CALLS})")


if __name__ == "__main__":
    main()
