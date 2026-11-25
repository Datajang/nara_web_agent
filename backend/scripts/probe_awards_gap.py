"""낙찰 백필이 멈춘 창 확인: G2B totalCount와 실제 받은 행 수가 다른가 (2026-11-25).

운영 로그: awards backfill KST 2017-04-13~19 창에서 '1855/1856건 (페이지 3)'로 G2BIncomplete.
같은 창을 (1) 수집기와 같은 7일·999행 페이지로, (2) 하루씩 나눠 받아
- 행 수가 매번 하나 모자라는지(재현), 어느 날짜인지
- 페이지 사이 중복 행이 있는지(고유키 기준)
를 본다. 개인정보는 남기지 않고 건수·고유키만 쓴다. G2B 약 11회 호출. 서비스키는 출력하지 않는다.

실행(운영 서버, 키를 파일로 남기지 않음):
  uv run python -m scripts.probe_awards_gap \\
    --env-file <(sudo grep -E '^NARA_(AWARD_)?API_KEY=' /etc/nara/nara.env) --out <저장소 밖 경로>
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import date, timedelta
from typing import Any

from dotenv import dotenv_values

from scripts.probe_g2b import Prober, header_of, items_of, total_of

BASE = "http://apis.data.go.kr/1230000/as/ScsbidInfoService"
OP = "getScsbidListSttusServc"
PAGE = 999


def key_of(it: dict[str, Any]) -> str:
    return "|".join(str(it.get(k, "")) for k in ("bidNtceNo", "bidNtceOrd", "bidClsfcNo", "rbidNo"))


def fetch(p: Prober, first: date, last: date) -> dict[str, Any]:
    """[first, last] KST 날짜 창을 빈 페이지가 나올 때까지 받는다."""
    q = {
        "inqryDiv": 1,
        "inqryBgnDt": first.strftime("%Y%m%d0000"),
        "inqryEndDt": last.strftime("%Y%m%d2359"),
        "numOfRows": PAGE,
    }
    pages: list[dict[str, Any]] = []
    keys: list[str] = []
    for page in range(1, 6):
        r = p.get(BASE, OP, "bid", pageNo=page, **q)
        its = items_of(r.get("data") or {})
        pages.append({"page": page, "total": total_of(r.get("data") or {}), "rows": len(its)})
        if r.get("status") != 200 or not its:
            if not its and page == 1:
                pages[-1]["header"] = header_of(r)
            break
        keys += [key_of(i) for i in its]
        if len(keys) >= (pages[0]["total"] or 0):
            break
    dup = [k for k, n in Counter(keys).items() if n > 1]
    return {
        "_keys": keys,
        "range": f"{first}~{last}",
        "total": pages[0]["total"],
        "rows": len(keys),
        "unique": len(set(keys)),
        "dup_keys": dup[:5],
        "pages": pages,
    }


SOURCES = {
    "awards": (BASE, OP),
    "contracts": ("http://apis.data.go.kr/1230000/ao/CntrctInfoService", "getCntrctInfoListServc"),
}


def split_check(p: Prober, day: date) -> dict[str, Any]:
    """하루를 오전·오후로 나눠 조회: 시·분 필터가 먹는지(합 = 하루, rgstDt 시각이 범위 안)."""
    out: dict[str, Any] = {}
    for src, (base, op) in SOURCES.items():
        res: dict[str, Any] = {}
        totals: dict[str, int] = {}
        for label, a, b in (
            ("day", "0000", "2359"),
            ("am", "0000", "1159"),
            ("pm", "1200", "2359"),
        ):
            d = day.strftime("%Y%m%d")
            r = p.get(
                base,
                op,
                "bid",
                inqryDiv=1,
                inqryBgnDt=d + a,
                inqryEndDt=d + b,
                numOfRows=PAGE,
                pageNo=1,
            )
            its = items_of(r.get("data") or {})
            hours = sorted(str(i.get("rgstDt", ""))[11:16] for i in its if i.get("rgstDt"))
            totals[label] = total_of(r.get("data") or {}) or 0
            res[label] = {
                "total": totals[label],
                "rows": len(its),
                "rgst_first": hours[0] if hours else None,
                "rgst_last": hours[-1] if hours else None,
            }
        res["am_plus_pm_equals_day"] = totals["am"] + totals["pm"] == totals["day"]
        out[src] = res
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--env-file", required=True)
    ap.add_argument("--out", required=True, help="요약 JSON 경로 (저장소 밖)")
    ap.add_argument("--first", default="2017-04-13", help="창 첫 KST 날짜")
    ap.add_argument("--split-day", help="이 KST 날짜를 오전·오후로 나눠 시·분 필터만 확인(6회)")
    args = ap.parse_args()
    env = dotenv_values(args.env_file)
    key = env.get("NARA_AWARD_API_KEY") or env.get("NARA_API_KEY") or ""
    p = Prober(key, "")
    if args.split_day:
        res = split_check(p, date.fromisoformat(args.split_day))
        res["g2b_calls"] = p.calls
        text = json.dumps(res, ensure_ascii=False, indent=2)
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text)
        print(text)
        return
    first = date.fromisoformat(args.first)
    out: dict[str, Any] = {"window": fetch(p, first, first + timedelta(days=6))}
    out["days"] = [fetch(p, d, d) for d in (first + timedelta(days=i) for i in range(7))]
    out["days_sum"] = {
        "total": sum(d["total"] or 0 for d in out["days"]),
        "rows": sum(d["rows"] for d in out["days"]),
    }
    # 창의 중복 행이 '날짜가 다른 같은 키'(정상)인지 '페이지 겹침으로 다른 행이 빠짐'인지 가른다
    win = set(out["window"].pop("_keys"))
    per_day = [set(d.pop("_keys")) for d in out["days"]]
    union = set().union(*per_day)
    cross = Counter(k for ks in per_day for k in ks)
    out["keys"] = {
        "window_unique": len(win),
        "days_union_unique": len(union),
        "only_in_days": sorted(union - win)[:5],  # 창에서 빠진 행(페이지 겹침이면 여기 나온다)
        "only_in_window": sorted(win - union)[:5],
        "same_key_on_two_days": sorted(k for k, n in cross.items() if n > 1)[:5],
    }
    out["g2b_calls"] = p.calls
    text = json.dumps(out, ensure_ascii=False, indent=2)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(text)
    print(text)


if __name__ == "__main__":
    main()
