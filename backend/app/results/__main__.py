"""결과 메일 타이머(5분, nara-result-watch.timer) 한 번 실행 (설계 2026-11-25).

  python -m app.results

감시 맞추기(sync_watches) → 확인할 때가 된 공고 확인(check_due)
→ 감지 뒤 7일 안의 단계 발송(dispatch). G2B 호출 수는 usage_logs
(event=collector, cache.source=result_watch)에 남아 결과 메일 몫 예산에 센다.
"""

from __future__ import annotations

import asyncio
import logging
import sys

from app.auth.mail import build_mailer
from app.logging_setup import configure_logging
from app.results.checker import check_due
from app.results.dispatch import dispatch, pending
from app.results.watch import sync_watches
from app.runtime import real_deps

log = logging.getLogger(__name__)


async def main() -> int:
    async with real_deps() as deps:
        now = deps.clock()
        async with deps.db.transaction() as s:
            created = await sync_watches(s, now)
        changes = await check_due(deps, now)
        async with deps.db.session() as s:
            todo = await pending(s, now)
        sent = await dispatch(deps, build_mailer(deps.settings), todo)
        log.info("결과 메일: 새 감시 %d · 바뀐 공고 %d · 보낸 메일 %d", created, len(changes), sent)
    return 0


if __name__ == "__main__":
    configure_logging()
    sys.exit(asyncio.run(main()))
