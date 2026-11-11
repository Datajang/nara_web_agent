"""운영 경보 점검 (§11.7 알림 기준). systemd 타이머(nara-alert.timer)가 10분마다 부른다.

    python -m app.ops.check --readyz-url http://127.0.0.1:8010/readyz

기준 [가정]: 수집 2시간 넘게 성공 없음 / G2B 호출 예산 80% 초과 / 디스크 80% 초과 /
/readyz 3회 연속 실패. 같은 경보는 ALERT_REPEAT_H 동안 다시 보내지 않고, 해소되면 지운다.
경보가 하나라도 있으면 종료 코드 1(`systemctl --failed`에서도 보인다).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import shutil
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import httpx

from app.auth.mail import Mail, Mailer, build_mailer
from app.deps import Deps
from app.logging_setup import configure_logging
from app.ops.status import collector_state, last_collector_ok
from app.usage.budget import DbCallBudget

log = logging.getLogger(__name__)
READYZ_FAILS = 3


@dataclass(frozen=True)
class Alert:
    key: str
    message: str


def disk_ratio(path: str) -> float:
    usage = shutil.disk_usage(path)
    return usage.used / usage.total if usage.total else 0.0


async def readyz_ok(url: str) -> bool:
    try:
        async with httpx.AsyncClient(timeout=10, trust_env=False) as client:
            r = await client.get(url)
        return r.status_code == 200 and r.json().get("db") == "ok"
    except (httpx.HTTPError, ValueError):
        return False


async def evaluate(
    deps: Deps,
    *,
    readyz_failures: int,
    disk_usage: Callable[[str], float],
    disk_paths: Iterable[str],
) -> list[Alert]:
    st = deps.settings
    alerts: list[Alert] = []
    last_ok = await last_collector_ok(deps)
    state = collector_state(deps, last_ok)
    if state == "never":
        alerts.append(Alert("collector_stale", "수집 성공 기록이 없습니다."))
    elif state == "stale" and last_ok is not None:
        hours = (deps.clock() - last_ok).total_seconds() / 3600
        alerts.append(
            Alert(
                "collector_stale",
                f"수집이 {hours:.1f}시간째 성공하지 못했습니다"
                f"(마지막 성공 {last_ok:%Y-%m-%d %H:%M} UTC).",
            )
        )
    used = await DbCallBudget(deps.db, st.g2b_daily_call_budget).used_today()
    if st.g2b_daily_call_budget and used >= st.alert_budget_ratio * st.g2b_daily_call_budget:
        alerts.append(
            Alert("g2b_budget", f"G2B 호출이 오늘 {used}/{st.g2b_daily_call_budget}회입니다.")
        )
    for path in disk_paths:
        ratio = disk_usage(path)
        if ratio >= st.alert_disk_ratio:
            alerts.append(Alert(f"disk:{path}", f"디스크 {path} 사용률 {ratio:.0%}입니다."))
    if readyz_failures >= READYZ_FAILS:
        alerts.append(Alert("readyz", f"/readyz가 {readyz_failures}회 연속 실패했습니다."))
    return alerts


def _load(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text())
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save(path: Path, state: dict[str, Any]) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False))
    tmp.replace(path)


async def run_check(
    deps: Deps,
    mailer: Mailer,
    *,
    state_path: Path,
    readyz: Callable[[], bool | Awaitable[bool]],
    disk_usage: Callable[[str], float] = disk_ratio,
    disk_paths: Iterable[str] = ("/",),
) -> int:
    st = deps.settings
    now = deps.clock()
    state = _load(state_path)
    ok = readyz()
    if not isinstance(ok, bool):
        ok = await ok
    failures = 0 if ok else int(state.get("readyz_failures", 0)) + 1
    alerts = await evaluate(
        deps, readyz_failures=failures, disk_usage=disk_usage, disk_paths=disk_paths
    )
    sent: dict[str, str] = {
        k: v for k, v in state.get("sent", {}).items() if k in {a.key for a in alerts}
    }  # 해소된 경보는 지워서 다음에 다시 울리게 한다
    repeat = timedelta(hours=st.alert_repeat_h)
    due = [
        a
        for a in alerts
        if a.key not in sent or now - datetime.fromisoformat(sent[a.key]) >= repeat
    ]
    for a in alerts:
        log.warning("alert %s: %s", a.key, a.message, extra={"event": "alert"})
    if due:
        if st.alert_email:
            body = "\n".join(f"- {a.message}" for a in due)
            body += "\n\n런북: docs/ops/RUNBOOK.md"
            await mailer.send(
                Mail(st.alert_email, f"[{st.service_name}] 운영 경보 {len(due)}건", body)
            )
        else:
            log.warning("ALERT_EMAIL이 비어 있어 경보 메일을 보내지 않았습니다")
        for a in due:
            sent[a.key] = now.isoformat()
    _save(state_path, {"sent": sent, "readyz_failures": failures})
    return 1 if alerts else 0


async def main(argv: list[str] | None = None) -> int:
    from app.runtime import real_deps

    ap = argparse.ArgumentParser(prog="python -m app.ops.check")
    ap.add_argument("--readyz-url", default="http://127.0.0.1:8010/readyz")
    ap.add_argument("--state", type=Path, default=Path("/var/lib/nara/alert-state.json"))
    ap.add_argument("--disk", action="append", help="사용률을 볼 경로 (여러 번)")
    args = ap.parse_args(argv)
    configure_logging()
    async with real_deps() as deps:
        return await run_check(
            deps,
            build_mailer(deps.settings),
            state_path=args.state,
            readyz=lambda: readyz_ok(args.readyz_url),
            disk_paths=args.disk or ["/"],
        )


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
