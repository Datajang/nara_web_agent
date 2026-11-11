"""DB-first 검색을 사람이 확인하는 CLI (P1 완료 게이트용). HTTP API는 인증과 함께 P2·P3에서.

  python -m app.search AI 플랫폼 --days 30 [--source regular] [--open]

사용자 없이 실행하므로 스냅샷은 저장하지 않고 usage_logs만 남긴다.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from app.logging_setup import configure_logging
from app.runtime import real_deps
from app.search.query import SearchQuery
from app.search.service import search_bids


async def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m app.search")
    ap.add_argument("keywords", nargs="*")
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--source", choices=["all", "regular", "prespec"], default="all")
    ap.add_argument("--open", action="store_true", help="진행중만")
    ap.add_argument("--top", type=int, default=20)
    args = ap.parse_args(argv)
    configure_logging(logging.WARNING)
    q = SearchQuery(
        keywords=args.keywords,
        days=args.days,
        source=args.source,
        status="open" if args.open else "all",
        top_n=args.top,
    )
    async with real_deps() as deps:
        res = await search_bids(deps, None, q)
    print(
        f"결과 {len(res.items)}건 | cache_hit={res.cache_hit} g2b_calls={res.g2b_calls} "
        f"incomplete={res.incomplete} data_as_of={res.data_as_of}"
    )
    for b in res.items:
        deadline = b.deadline_at.isoformat(timespec="minutes") if b.deadline_at else "마감 미정"
        print(
            f"  b{b.id} [{b.source}] {b.title[:50]} | {b.org_name or '-'}"
            f" | {b.budget or '-'} | {deadline}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
