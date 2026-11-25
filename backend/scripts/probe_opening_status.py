"""마감 공고 사유 [미확인] 확인 (2026-11-25).

개찰결과 목록(`getOpengResultListInfoServc`)을 개찰일시(inqryDiv=3) 기간으로 모아 둘 수 있는지:
(a) 한 번에 조회할 수 있는 기간(1·7·31일) (b) 페이지 넘김 (c) 몇 년 전 개찰까지 나오는지
(d) 한 공고가 몇 행인지(차수·분류·재입찰). 호출 12회 이하. 서비스키는 출력하지 않는다(규칙 4).

실행: cd backend && uv run python -m scripts.probe_opening_status --env-file ../.env
"""

from __future__ import annotations

import argparse
import asyncio
import json
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import unquote

import httpx
from dotenv import dotenv_values

KST = timezone(timedelta(hours=9))
URL = "http://apis.data.go.kr/1230000/as/ScsbidInfoService/getOpengResultListInfoServc"
MAX_CALLS = 12


class Probe:
    def __init__(self, http: httpx.AsyncClient, key: str) -> None:
        self.http, self.key, self.calls = http, key, 0

    async def get(self, bgn: datetime, end: datetime, page: int = 1, rows: int = 999) -> dict:
        if self.calls >= MAX_CALLS:
            raise SystemExit("호출 상한")
        self.calls += 1
        params = {
            "ServiceKey": self.key,
            "type": "json",
            "inqryDiv": "3",
            "inqryBgnDt": bgn.strftime("%Y%m%d%H%M"),
            "inqryEndDt": end.strftime("%Y%m%d%H%M"),
            "numOfRows": str(rows),
            "pageNo": str(page),
        }
        r = await self.http.get(URL, params=params, timeout=90)
        try:
            body = r.json()
        except ValueError:
            return {"_error": f"HTTP {r.status_code} {r.text[:300].replace(self.key, '***')}"}
        if "response" not in body:
            return {"_raw": json.dumps(body, ensure_ascii=False)[:400].replace(self.key, "***")}
        resp = body["response"]
        b = resp.get("body", {}) or {}
        items: Any = b.get("items") or []
        if isinstance(items, dict):
            items = items.get("item") or []
        if isinstance(items, dict):
            items = [items]
        h = resp.get("header", {})
        return {
            "code": h.get("resultCode"),
            "msg": h.get("resultMsg"),
            "total": b.get("totalCount"),
            "items": items,
        }


def k(i: dict) -> tuple:
    return (i.get("bidNtceNo"), i.get("bidNtceOrd"), i.get("bidClsfcNo"), i.get("rbidNo"))


def show(label: str, res: dict) -> list[dict]:
    items = res.get("items") or []
    if "code" not in res:
        print(label, "오류", res)
        return []
    st = Counter(str(i.get("progrsDivCdNm")) for i in items)
    print(
        f"{label}: code {res['code']} {res.get('msg')} total {res.get('total')}",
        f"받은 {len(items)} {dict(st)}",
    )
    return items


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--env-file", default="../.env")
    a = ap.parse_args()
    env = dotenv_values(a.env_file)
    key = env.get("NARA_AWARD_API_KEY") or env.get("NARA_API_KEY")
    if not key:
        raise SystemExit("NARA_API_KEY가 없습니다")
    key = unquote(key)
    today = datetime.now(KST).replace(hour=0, minute=0, second=0, microsecond=0)
    async with httpx.AsyncClient() as http:
        p = Probe(http, key)
        # (a) 기간 길이
        day = show(
            "1일(어제)", await p.get(today - timedelta(days=1), today - timedelta(minutes=1))
        )
        week_res = await p.get(today - timedelta(days=7), today - timedelta(minutes=1))
        week = show("7일", week_res)
        show("31일", await p.get(today - timedelta(days=31), today - timedelta(minutes=1)))
        # (b) 페이지 넘김: 7일 2쪽이 1쪽과 겹치는지
        if int(week_res.get("total") or 0) > len(week):
            res2 = await p.get(today - timedelta(days=7), today - timedelta(minutes=1), page=2)
            w2 = show("7일 2쪽", res2)
            print("  1쪽∩2쪽 겹침:", len({k(i) for i in week} & {k(i) for i in w2}))
        # (c) 과거
        for y in (2025, 2023, 2021, 2020):
            d = datetime(y, 6, 10, tzinfo=KST)
            show(f"{y}-06-10 하루", await p.get(d, d + timedelta(hours=23, minutes=59)))
        # (d) 한 공고의 행 수, 필드
        if day:
            print("필드:", sorted(day[0]))
            per = Counter(i.get("bidNtceNo") for i in day)
            print("공고당 행 수 분포:", dict(Counter(per.values())))
            multi = [n for n, c in per.items() if c > 1][:2]
            for n in multi:
                for i in day:
                    if i.get("bidNtceNo") == n:
                        print(
                            "  ",
                            n,
                            i.get("bidNtceOrd"),
                            i.get("bidClsfcNo"),
                            i.get("rbidNo"),
                            i.get("progrsDivCdNm"),
                            i.get("opengDt"),
                            i.get("inptDt"),
                        )
        print("호출", p.calls)


if __name__ == "__main__":
    asyncio.run(main())
