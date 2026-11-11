"""Q5 [미확인] 확인: G2B에서 공고번호로 단건 조회가 되는가 (SPEC §14 Q5, §6.2 lookup).

방법: 최근 하루치 목록에서 실제 공고번호를 하나 고른 뒤, 여러 조회 방식으로 그 번호만
다시 찾아본다. 응답 행이 모두 그 번호인지(필터가 실제로 먹는지)를 본다.
실제 G2B를 약 12회 호출한다. 서비스키는 출력·파일에 남기지 않는다(규칙 4).

실행: uv run python -m scripts.probe_lookup --env-file ../.env --out <저장소 밖 경로>
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta
from typing import Any

from dotenv import dotenv_values

from scripts.probe_g2b import (
    BID_BASE,
    BID_OP,
    PRESPEC_BASE,
    PRESPEC_OP,
    Prober,
    header_of,
    items_of,
    total_of,
)

BID_PLAIN_OP = "getBidPblancListInfoServc"
PRESPEC_PLAIN_OP = "getPublicPrcureThngInfoServc"


def judge(res: dict[str, Any], field: str, no: str) -> dict[str, Any]:
    """필터가 적용됐는지: 행이 있고 모두 그 번호면 hit."""
    its = items_of(res.get("data") or {})
    nos = {str(i.get(field, "")) for i in its}
    if not its:
        verdict = "empty"
    elif nos == {no}:
        verdict = "hit"
    else:
        verdict = "ignored"  # 필터 무시하고 다른 공고가 섞여 옴
    return {
        "status": res.get("status"),
        "header": header_of(res),
        "total": total_of(res.get("data") or {}),
        "rows": len(its),
        "distinct_nos": len(nos),
        "verdict": verdict,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--env-file", required=True)
    ap.add_argument("--out", required=True, help="요약 JSON 경로 (저장소 밖)")
    ap.add_argument("--days-ago", type=int, default=1)
    args = ap.parse_args()
    env = dotenv_values(args.env_file)
    p = Prober(env.get("NARA_API_KEY") or "", env.get("NARA_PRESPEC_API_KEY") or "")

    day = datetime.now() - timedelta(days=args.days_ago)
    begin, end = day.strftime("%Y%m%d0000"), day.strftime("%Y%m%d2359")
    old = datetime.now() - timedelta(days=60)
    old_begin, old_end = old.strftime("%Y%m%d0000"), old.strftime("%Y%m%d2359")
    page = {"pageNo": 1, "numOfRows": 20}
    out: dict[str, Any] = {"date": day.strftime("%Y-%m-%d"), "cases": {}}

    # 표본 번호: 최근 하루, 60일 전 하루 (공고·사전규격)
    def sample(base: str, op: str, key: str, b: str, e: str, field: str) -> str:
        r = p.get(base, op, key, inqryDiv=1, inqryBgnDt=b, inqryEndDt=e, **page)
        its = items_of(r.get("data") or {})
        return str(its[0].get(field, "")) if its else ""

    bid_no = sample(BID_BASE, BID_OP, "bid", begin, end, "bidNtceNo")
    old_no = sample(BID_BASE, BID_OP, "bid", old_begin, old_end, "bidNtceNo")
    spec_no = sample(PRESPEC_BASE, PRESPEC_OP, "prespec", begin, end, "bfSpecRgstNo")
    out["samples"] = {"bid": bool(bid_no), "old_bid": bool(old_no), "prespec": bool(spec_no)}
    cases = out["cases"]

    for label, no in (("recent", bid_no), ("60d", old_no)):
        if not no:
            continue
        for op in (BID_OP, BID_PLAIN_OP):
            for div in (2, 3):
                r = p.get(BID_BASE, op, "bid", inqryDiv=div, bidNtceNo=no, **page)
                cases[f"bid/{label}/{op}/inqryDiv={div}"] = judge(r, "bidNtceNo", no)
    if spec_no:
        for op in (PRESPEC_OP, PRESPEC_PLAIN_OP):
            r = p.get(PRESPEC_BASE, op, "prespec", inqryDiv=2, bfSpecRgstNo=spec_no, **page)
            cases[f"prespec/recent/{op}/inqryDiv=2"] = judge(r, "bfSpecRgstNo", spec_no)

    out["calls"] = p.calls
    text = p.mask(json.dumps(out, ensure_ascii=False, indent=1, default=str))
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(text)
    for k, v in cases.items():
        print(f"{v['verdict']:8} total={v['total']} rows={v['rows']} {k}")
    print(f"calls={p.calls}")


if __name__ == "__main__":
    main()
