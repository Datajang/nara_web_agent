# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx>=0.27"]
# ///
"""부하 확인 (SPEC §13.6): 동시 사용자 N명(기본 10)이 검색 → 분석(SSE)을 반복할 때 끊기지 않는가.

    uv run eval/load_test.py --base http://localhost:4173 --accounts accounts.txt \\
        --users 10 --rounds 3

accounts.txt: 한 줄에 `이메일 비밀번호`. 계정이 사용자 수보다 적으면 돌려 쓴다(사용자별 속도 제한
§6.1: 검색 30회/분, 분석 10회/분에 걸리면 429로 따로 센다). 각 계정에 프로필이 하나 있어야 한다.
판정: 오류 0건이고 모든 분석 스트림이 done까지 오면 ok.
결과는 eval/results/<날짜>_load_<label>.json.
가짜 LLM으로는 흐름만, 실제 처리량은 vLLM(P3a-2 이후)에서 측정한다.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx

RESULTS = Path(__file__).resolve().parent / "results"
KEYWORDS = ["AI", "클라우드", "데이터", "시스템", "플랫폼", "유지보수"]


def pct(values: list[float], p: float) -> float | None:
    """선형 보간 백분위수."""
    if not values:
        return None
    xs = sorted(values)
    k = (len(xs) - 1) * p / 100
    lo = int(k)
    hi = min(lo + 1, len(xs) - 1)
    return round(xs[lo] + (xs[hi] - xs[lo]) * (k - lo), 2)


def parse_sse(body: str) -> list[dict[str, Any]]:
    return [
        json.loads(block.removeprefix("data: "))
        for block in body.split("\n\n")
        if block.startswith("data: ")
    ]


class Stats:
    def __init__(self) -> None:
        self.ms: dict[str, list[float]] = {"search": [], "analyze": []}
        self.errors: Counter[str] = Counter()

    def report(self) -> dict[str, Any]:
        ops = {
            op: {
                "ok": len(v),
                "p50_ms": pct(v, 50),
                "p95_ms": pct(v, 95),
                "max_ms": max(v) if v else None,
            }
            for op, v in self.ms.items()
        }
        return {
            "ops": ops,
            "errors": dict(self.errors),
            "verdict": "ok" if not self.errors else "fail",
        }


async def _login(c: httpx.AsyncClient, account: tuple[str, str], stats: Stats) -> int | None:
    """로그인하고 기본 프로필 ID를 돌려준다. 로그인은 IP당 분당 5회 제한(§6.1)이라
    같은 서버에서 여러 계정을 쓰면 Retry-After만큼 기다린다(측정 시간에는 넣지 않는다)."""
    for _ in range(5):
        r = await c.post("/api/v1/auth/login", json={"email": account[0], "password": account[1]})
        if r.status_code != 429:
            break
        await asyncio.sleep(float(r.headers.get("retry-after", "15")))
    if r.status_code != 200:
        stats.errors[f"login:{r.status_code}"] += 1
        return None
    profiles = (await c.get("/api/v1/profiles")).json().get("items", [])
    if not profiles:
        stats.errors["profile:missing"] += 1
        return None
    return int(next((p["id"] for p in profiles if p.get("is_default")), profiles[0]["id"]))


async def _user(
    c: httpx.AsyncClient,
    pid: int,
    rounds: int,
    keywords: list[str],
    stats: Stats,
    seed: int,
) -> None:
    rnd = random.Random(seed)
    for _ in range(rounds):
        t0 = time.perf_counter()
        r = await c.post(
            "/api/v1/bids/search", json={"keywords": [rnd.choice(keywords)], "days": 30}
        )
        if r.status_code != 200:
            stats.errors[f"search:{r.status_code}"] += 1
            continue
        stats.ms["search"].append((time.perf_counter() - t0) * 1000)
        items = r.json().get("items", [])
        if not items:
            continue
        bid = rnd.choice(items[:5])["bid_id"]
        t0 = time.perf_counter()
        r = await c.post(
            f"/api/v1/bids/{bid}/analyze",
            json={"profile_id": pid},
            headers={"Accept": "text/event-stream"},
        )
        if r.status_code != 200:
            stats.errors[f"analyze:{r.status_code}"] += 1
            continue
        events = parse_sse(r.text)
        types = [e.get("type") for e in events]
        if "done" not in types:
            stats.errors["analyze:stream_interrupted"] += 1
        elif "error" in types:
            err = next(e for e in events if e.get("type") == "error")
            stats.errors[f"analyze:{err.get('code')}"] += 1
        else:
            stats.ms["analyze"].append((time.perf_counter() - t0) * 1000)


async def run(
    base: str,
    accounts: list[tuple[str, str]],
    *,
    users: int,
    rounds: int,
    keywords: list[str],
    transport: httpx.AsyncBaseTransport | None = None,
) -> dict[str, Any]:
    stats = Stats()
    clients = [
        httpx.AsyncClient(base_url=base, headers={"Origin": base}, timeout=300, transport=transport)
        for _ in range(users)
    ]
    try:
        sessions = []
        for i, c in enumerate(clients):  # 로그인은 순서대로 (측정 밖)
            pid = await _login(c, accounts[i % len(accounts)], stats)
            if pid is not None:
                sessions.append((c, pid))
        started = time.perf_counter()
        await asyncio.gather(
            *(_user(c, pid, rounds, keywords, stats, i) for i, (c, pid) in enumerate(sessions))
        )
    finally:
        for c in clients:
            await c.aclose()
    report = stats.report()
    report.update(users=users, rounds=rounds, wall_s=round(time.perf_counter() - started, 2))
    return report


def _accounts(path: Path) -> list[tuple[str, str]]:
    out = []
    for line in path.read_text().splitlines():
        if line.strip() and not line.startswith("#"):
            email, password = line.split(maxsplit=1)
            out.append((email, password.strip()))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:4173")
    ap.add_argument("--accounts", type=Path, required=True)
    ap.add_argument("--users", type=int, default=10)
    ap.add_argument("--rounds", type=int, default=3)
    ap.add_argument("--label", default="fake")
    args = ap.parse_args()
    report = asyncio.run(
        run(
            args.base.rstrip("/"),
            _accounts(args.accounts),
            users=args.users,
            rounds=args.rounds,
            keywords=KEYWORDS,
        )
    )
    RESULTS.mkdir(exist_ok=True)
    out = RESULTS / f"{datetime.now():%Y-%m-%d}_load_{args.label}.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"→ {out}")
    return 0 if report["verdict"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
