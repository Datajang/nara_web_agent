"""입찰공고정보서비스 v1.3(`BidPublicInfoService02`, 오퍼레이션 `...02`) 확인.

운영계정(하루 10만)이 `02` 오퍼레이션에만 승인돼, `02` 없는 옛 주소는 개발계정 한도(약 1,000)에
걸린 것으로 보인다(2026-11-24). 같은 키로 `02` 검색·번호 조회가 되는지, 응답 필드가 같은지 본다.
v1.3(2026-11-10) '조회기간 1개월→7일'도 KST 날짜 7개·8개 창으로 본다.
실제 G2B를 4회 호출한다. 서비스키는 출력·파일에 남기지 않는다(규칙 4).

실행(운영 서버, 키를 파일로 남기지 않음):
  uv run python -m scripts.probe_bid02 \
    --env-file <(sudo grep '^NARA_API_KEY=' /etc/nara/nara.env) --out <저장소 밖 경로>
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta
from typing import Any

from dotenv import dotenv_values

from scripts.probe_g2b import Prober, header_of, items_of, total_of

BASE02 = "http://apis.data.go.kr/1230000/ad/BidPublicInfoService02"
SEARCH02 = "getBidPblancListInfoServcPPSSrch02"
PLAIN02 = "getBidPblancListInfoServc02"
# 수집기가 읽는 필드(app/g2b/mapper·collector 기준)
FIELDS = (
    "bidNtceNo",
    "bidNtceOrd",
    "bidNtceNm",
    "ntceInsttNm",
    "dminsttNm",
    "asignBdgtAmt",
    "presmptPrce",
    "bidNtceDt",
    "bidClseDt",
    "bidNtceDtlUrl",
    "bfSpecRgstNo",
    "ntceSpecDocUrl1",
    "ntceSpecFileNm1",
    "stdNtceDocUrl",
)


def summary(res: dict[str, Any]) -> dict[str, Any]:
    its = items_of(res.get("data") or {})
    first = its[0] if its else {}
    return {
        "status": res.get("status"),
        "header": header_of(res),
        "total": total_of(res.get("data") or {}),
        "rows": len(its),
        "missing_fields": [f for f in FIELDS if f not in first],
        "field_count": len(first),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--env-file", required=True)
    ap.add_argument("--out", required=True, help="요약 JSON 경로 (저장소 밖)")
    args = ap.parse_args()
    env = dotenv_values(args.env_file)
    p = Prober(env.get("NARA_API_KEY") or "", env.get("NARA_PRESPEC_API_KEY") or "")

    day = datetime.now() - timedelta(days=1)
    d = {"inqryDiv": 1, "inqryBgnDt": day.strftime("%Y%m%d0000")}
    d["inqryEndDt"] = day.strftime("%Y%m%d2359")
    out: dict[str, Any] = {"date": day.strftime("%Y-%m-%d")}

    r = p.get(BASE02, SEARCH02, "bid", pageNo=1, numOfRows=10, **d)
    out["search02"] = summary(r)
    its = items_of(r.get("data") or {})
    no = str(its[0].get("bidNtceNo", "")) if its else ""
    if no:
        r2 = p.get(BASE02, PLAIN02, "bid", inqryDiv=2, bidNtceNo=no, pageNo=1, numOfRows=10)
        s2 = summary(r2)
        s2["all_same_no"] = {str(i.get("bidNtceNo")) for i in items_of(r2.get("data") or {})} == {
            no
        }
        out["lookup02"] = s2
    # 조회기간 상한: 어제까지 KST 날짜 7개 / 8개
    for n in (7, 8):
        b = (day - timedelta(days=n - 1)).strftime("%Y%m%d0000")
        rs = p.get(
            BASE02,
            SEARCH02,
            "bid",
            pageNo=1,
            numOfRows=1,
            inqryDiv=1,
            inqryBgnDt=b,
            inqryEndDt=d["inqryEndDt"],
        )
        out[f"span_{n}_dates"] = {k: v for k, v in summary(rs).items() if k != "missing_fields"}
    text = json.dumps(out, ensure_ascii=False, indent=2)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(text)
    print(text)


if __name__ == "__main__":
    main()
