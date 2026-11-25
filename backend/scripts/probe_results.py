"""결과 메일 [미확인] 확인 (설계 docs/superpowers/specs/2026-11-25-bid-result-mail-design.md, 2026-11-25).

확인 항목: (a) 낙찰 목록 inqryDiv=4 + bidNtceNo 단건 조회 (b) 개찰결과의 진행 상태 필드(유찰·재입찰 등)
(c) 재공고 표시 (d) 개찰 시각 대비 Open API 반영 시각. 호출 30회 이하. 서비스키는 출력하지 않는다(규칙 4).

실행: cd backend && uv run python -m scripts.probe_results --env-file ../.env
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import unquote

import httpx
from dotenv import dotenv_values

KST = timezone(timedelta(hours=9))
AWARD = "http://apis.data.go.kr/1230000/as/ScsbidInfoService"
BID = "http://apis.data.go.kr/1230000/ad/BidPublicInfoService02"
TIME_KEYS = re.compile(r"(Dt|Dtm|Date)$")
MAX_CALLS = 30


class Probe:
    def __init__(self, http: httpx.AsyncClient, key: str) -> None:
        self.http, self.key, self.calls = http, key, 0

    async def get(self, url: str, **params: str) -> dict[str, Any]:
        if self.calls >= MAX_CALLS:
            raise SystemExit("호출 상한")
        self.calls += 1
        r = await self.http.get(
            url, params={"ServiceKey": self.key, "type": "json", **params}, timeout=60
        )
        try:
            body = r.json()
        except ValueError:
            return {"_error": f"HTTP {r.status_code} {r.text[:200].replace(self.key, '***')}"}
        if "response" not in body:
            return {"_raw": json.dumps(body, ensure_ascii=False)[:400].replace(self.key, "***")}
        resp = body["response"]
        header = resp.get("header", {})
        b = resp.get("body", {}) or {}
        items = b.get("items") or []
        if isinstance(items, dict):
            items = items.get("item") or []
        if isinstance(items, dict):
            items = [items]
        return {"code": header.get("resultCode"), "total": b.get("totalCount"), "items": items}


def fmt(d: datetime) -> str:
    return d.strftime("%Y%m%d%H%M")


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--env-file", default="../.env")
    a = ap.parse_args()
    env = dotenv_values(a.env_file)
    key = env.get("NARA_AWARD_API_KEY") or env.get("NARA_API_KEY")
    if not key:
        raise SystemExit("NARA_API_KEY가 없습니다")
    key = unquote(key)  # data.go.kr '인코딩' 키면 디코딩 (httpx가 다시 인코딩한다)
    now = datetime.now(KST)
    async with httpx.AsyncClient() as http:
        p = Probe(http, key)
        # (b)(d) 어제 0시~지금 개찰된 용역 개찰결과
        start = (now - timedelta(days=1)).replace(hour=0, minute=0)
        res = await p.get(
            f"{AWARD}/getOpengResultListInfoServc",
            inqryDiv="3",  # 문서: 3 = 개찰일시
            inqryBgnDt=fmt(start),
            inqryEndDt=fmt(now),
            numOfRows="999",
            pageNo="1",
        )
        items = res.get("items", [])
        print("개찰결과:", res.get("code"), "total", res.get("total"), "받은 행", len(items))
        if not items:
            print(json.dumps(res, ensure_ascii=False)[:600])
            return
        print("필드:", sorted(items[0]))
        print("시간 필드 예:", {k: v for k, v in items[0].items() if TIME_KEYS.search(k)})
        status = Counter(str(it.get("progrsDivCdNm")) for it in items)
        print("progrsDivCdNm:", dict(status))
        # 가장 최근 개찰이 지금보다 얼마나 앞인지 (반영 지연의 상한 가늠)
        opened = sorted(items, key=lambda it: str(it.get("opengDt") or ""))
        # (d) 개찰(opengDt) → 입력(inptDt) 지연 분포(분)
        lag = []
        for it in items:
            try:
                o = datetime.strptime(str(it.get("opengDt")), "%Y-%m-%d %H:%M:%S")
                n = datetime.strptime(str(it.get("inptDt")), "%Y-%m-%d %H:%M:%S")
            except ValueError:
                continue
            lag.append((n - o).total_seconds() / 60)
        lag.sort()
        if lag:
            q = [lag[int(len(lag) * f)] for f in (0.5, 0.9, 0.99)] + [lag[-1]]
            print("개찰→입력 지연(분) p50·p90·p99·max:", [round(x, 1) for x in q], "n", len(lag))
            for st in status:
                ls = sorted(
                    (
                        datetime.strptime(str(it["inptDt"]), "%Y-%m-%d %H:%M:%S")
                        - datetime.strptime(str(it["opengDt"]), "%Y-%m-%d %H:%M:%S")
                    ).total_seconds()
                    / 60
                    for it in items
                    if str(it.get("progrsDivCdNm")) == st and it.get("inptDt") and it.get("opengDt")
                )
                if ls:
                    print(f"  {st}: p50 {ls[len(ls) // 2]:.1f}분 max {ls[-1]:.1f}분")
        print("가장 최근 개찰 5건 (지금", now.strftime("%H:%M"), "):")
        for it in opened[-5:]:
            extra = {k: it.get(k) for k in it if TIME_KEYS.search(k)}
            print("  ", it.get("bidNtceNo"), it.get("bidNtceOrd"), it.get("progrsDivCdNm"), extra)
        # (a)(c) 상태별 표본 2건씩: 낙찰 단건·개찰완료 목록·공고(재공고 여부)
        samples: list[dict[str, Any]] = []
        for st in status:
            samples += [it for it in items if str(it.get("progrsDivCdNm")) == st][:2]
        for it in samples[:8]:
            no, ord_ = str(it.get("bidNtceNo")), str(it.get("bidNtceOrd") or "000")
            aw = await p.get(
                f"{AWARD}/getScsbidListSttusServc",
                inqryDiv="4",
                bidNtceNo=no,
                numOfRows="10",
                pageNo="1",
            )
            oc = await p.get(
                f"{AWARD}/getOpengResultListInfoOpengCompt",
                bidNtceNo=no,
                bidNtceOrd=ord_,
                numOfRows="999",
                pageNo="1",
            )
            winners = [
                (x.get("bidNtceOrd"), x.get("bidwinnrNm"), x.get("sucsfbidAmt"), x.get("rgstDt"))
                for x in aw.get("items", [])
            ]
            print(
                f"[{it.get('progrsDivCdNm')}] {no}-{ord_} 낙찰(div4) code={aw.get('code')}"
                f" rows={len(aw.get('items', []))} {winners[:2]} | 개찰완료 rows={len(oc.get('items', []))}"
            )
        # (c) 유찰 표본의 공고 차수·재공고 필드
        fail = [it for it in items if "유찰" in str(it.get("progrsDivCdNm"))][:2]
        for it in fail:
            no = str(it.get("bidNtceNo"))
            bd = await p.get(
                f"{BID}/getBidPblancListInfoServc02",
                inqryDiv="2",
                bidNtceNo=no,
                numOfRows="20",
                pageNo="1",
            )
            rows = [
                {k: x.get(k) for k in ("bidNtceOrd", "reNtceYn", "ntceKindNm", "opengDt")}
                for x in bd.get("items", [])
            ]
            print(f"유찰 공고 {no} 공고 행:", rows)
        print("호출 수:", p.calls)


if __name__ == "__main__":
    asyncio.run(main())
