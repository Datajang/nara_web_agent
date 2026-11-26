"""개찰 상태: 1분에 999행이 넘는 창의 페이지 넘김 [미확인] 확인 (2026-11-25).

백필이 2021-11-25 11:00(KST) 1분 창 1,159행에서 멈췄다(1분보다 잘게 못 쪼갬).
그 1분을 999행씩 2페이지로 두 번 받아 (a) 키 겹침·빠짐 (b) 두 번 받은 순서가 같은지 본다.
호출 4회. 서비스키는 출력하지 않는다(규칙 4).

실행: cd backend && uv run python -m scripts.probe_status_minute --env-file ../.env
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime
from urllib.parse import unquote

import httpx
from dotenv import dotenv_values

from scripts.probe_opening_status import Probe, k

MINUTE = datetime(2021, 11, 25, 11, 0)


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--env-file", default="../.env")
    a = ap.parse_args()
    env = dotenv_values(a.env_file)
    key = env.get("NARA_AWARD_API_KEY") or env.get("NARA_API_KEY")
    if not key:
        raise SystemExit("서비스키 없음")
    async with httpx.AsyncClient() as http:
        p = Probe(http, unquote(key))
        passes = []
        for n in (1, 2):
            pages = [await p.get(MINUTE, MINUTE, page) for page in (1, 2)]
            keys = [k(i) for r in pages for i in r["items"]]
            total = pages[0]["total"]
            sizes = [len(r["items"]) for r in pages]
            print(f"회차 {n}: code={pages[0]['code']} total={total} 페이지별={sizes}")
            print(
                f"  행 {len(keys)} · 고유 키 {len(set(keys))} · 겹침 {len(keys) - len(set(keys))}"
            )
            passes.append(keys)
        a1, a2 = passes
        print(f"두 회차 같은 순서: {a1 == a2} · 두 회차 고유 키 합집합 {len(set(a1) | set(a2))}")
        print(f"호출 {p.calls}회")


if __name__ == "__main__":
    asyncio.run(main())
