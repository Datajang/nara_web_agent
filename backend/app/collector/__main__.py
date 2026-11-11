"""수집기 CLI (SPEC §5.3, §13.3).

  python -m app.collector incremental [--source regular|prespec|all]
  python -m app.collector backfill [--days 90] [--source ...]
  python -m app.collector fill --from 2026-10-01 --to 2026-10-15 [--source ...]

설정은 환경변수(운영: systemd EnvironmentFile). 로컬은 NARA_ENV_FILE=../.env,.env 처럼 지정.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime, timedelta, timezone

from app.collector import runner
from app.logging_setup import configure_logging
from app.runtime import real_deps

KST = timezone(timedelta(hours=9))


def _date(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=KST)


async def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m app.collector")
    ap.add_argument("mode", choices=["incremental", "backfill", "fill"])
    ap.add_argument("--source", choices=["regular", "prespec", "all"], default="all")
    ap.add_argument(
        "--days", type=int, default=None, help="backfill 일수 (기본 COLLECTOR_BACKFILL_DAYS)"
    )
    ap.add_argument("--from", dest="date_from", type=_date)
    ap.add_argument("--to", dest="date_to", type=_date)
    args = ap.parse_args(argv)
    configure_logging()
    sources = ["regular", "prespec"] if args.source == "all" else [args.source]
    ok = True
    async with real_deps() as deps:
        for src in sources:
            if args.mode == "backfill":
                r = await runner.backfill(
                    deps, src, args.days or deps.settings.collector_backfill_days
                )
            elif args.mode == "incremental":
                r = await runner.incremental(deps, src)
            else:
                if not (args.date_from and args.date_to):
                    ap.error("fill에는 --from과 --to가 필요합니다")
                done = await runner.fill(
                    deps, src, args.date_from, args.date_to + timedelta(days=1)
                )
                print(f"{src} fill: {'완료' if done else '일부만 (상한 또는 실패)'}")
                ok &= done
                continue
            print(
                f"{src} {args.mode}: {r.status} fetched={r.fetched} inserted={r.inserted} "
                f"updated={r.updated} g2b_calls={r.g2b_calls}"
                + (f" error={r.error}" if r.error else "")
            )
            ok &= r.status == "ok"
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
