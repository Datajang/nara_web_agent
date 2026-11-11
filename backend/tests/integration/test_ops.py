"""§11.7 운영: /readyz의 수집 시각, 요청 로그의 user_id, 경보 점검(app.ops.check)."""

import json
import logging
from datetime import timedelta

from app.auth.mail import MemoryMailer
from app.db.models import CollectorRun, UsageLog
from app.ops import check
from tests.conftest import NOW, make_auth_settings
from tests.helpers import create_user, login


async def _run(db, *, status: str, finished_ago_h: float) -> None:
    async with db.transaction() as s:
        s.add(
            CollectorRun(
                source="regular",
                mode="incremental",
                window_from=NOW - timedelta(days=1),
                window_to=NOW,
                status=status,
                started_at=NOW - timedelta(hours=finished_ago_h, minutes=1),
                finished_at=NOW - timedelta(hours=finished_ago_h),
            )
        )


# ---------- /readyz ----------


async def test_readyz_reports_collector_never(full_api):
    async with full_api.client() as c:
        r = await c.get("/readyz")
    assert r.status_code == 200
    assert r.json()["collector"] == "never" and r.json()["collector_last_ok_at"] is None


async def test_readyz_collector_fresh_then_stale(full_api, db):
    await _run(db, status="ok", finished_ago_h=0.5)
    await _run(db, status="failed", finished_ago_h=0.1)  # 실패는 성공 시각을 바꾸지 않는다
    async with full_api.client() as c:
        fresh = (await c.get("/readyz")).json()
        full_api.clock.advance(hours=2)
        stale = await c.get("/readyz")
    assert fresh["collector"] == "ok"
    assert fresh["collector_last_ok_at"].startswith(
        (NOW - timedelta(hours=0.5)).strftime("%Y-%m-%dT%H:%M")
    )
    # 수집 지연은 경보(check)가 잡는다. readyz는 DB가 살아 있으면 200을 유지한다.
    assert stale.status_code == 200 and stale.json()["collector"] == "stale"


# ---------- 요청 로그 ----------


async def test_request_log_carries_user_id(api, client, caplog):
    uid = await create_user(api.db, "logme@corp.example")
    await login(client, "logme@corp.example")
    caplog.set_level(logging.INFO, logger="app.request")
    r = await client.get("/api/v1/me")
    assert r.status_code == 200
    rec = [x for x in caplog.records if getattr(x, "path", None) == "/api/v1/me"][-1]
    assert rec.user_id == uid and rec.request_id == r.headers["x-request-id"]
    assert "logme@corp.example" not in caplog.text


# ---------- 경보 점검 ----------


def _deps(full_api, **settings):
    deps = full_api.ctx.deps
    deps.settings = make_auth_settings(g2b_daily_call_budget=1000, **settings)
    return deps


async def _check(full_api, tmp_path, *, readyz=True, disk=0.1, **settings):
    mailer = MemoryMailer()
    code = await check.run_check(
        _deps(full_api, **settings),
        mailer,
        state_path=tmp_path / "state.json",
        readyz=lambda: readyz,
        disk_usage=lambda _path: disk,
        disk_paths=["/"],
    )
    return code, mailer


async def test_check_all_good_sends_nothing(full_api, db, tmp_path):
    await _run(db, status="ok", finished_ago_h=0.2)
    code, mailer = await _check(full_api, tmp_path, alert_email="ops@corp.example")
    assert code == 0 and mailer.outbox == []


async def test_check_collector_stale_and_budget_and_disk(full_api, db, tmp_path):
    await _run(db, status="ok", finished_ago_h=3)
    async with db.transaction() as s:
        s.add(UsageLog(event="collector", g2b_calls=850, cache={}))
    code, mailer = await _check(full_api, tmp_path, disk=0.91, alert_email="ops@corp.example")
    assert code == 1
    (mail,) = mailer.outbox
    assert mail.to == "ops@corp.example" and "경보" in mail.subject
    for needle in ("수집", "G2B", "850", "디스크", "91%"):
        assert needle in mail.body
    state = json.loads((tmp_path / "state.json").read_text())
    assert set(state["sent"]) == {"collector_stale", "g2b_budget", "disk:/"}


async def test_check_repeats_only_after_quiet_period(full_api, db, tmp_path):
    await _run(db, status="ok", finished_ago_h=3)
    _, first = await _check(full_api, tmp_path, alert_email="ops@corp.example")
    _, again = await _check(full_api, tmp_path, alert_email="ops@corp.example")
    full_api.clock.advance(hours=7)
    _, later = await _check(full_api, tmp_path, alert_email="ops@corp.example")
    assert (len(first.outbox), len(again.outbox), len(later.outbox)) == (1, 0, 1)


async def test_check_readyz_needs_three_consecutive_failures(full_api, db, tmp_path):
    await _run(db, status="ok", finished_ago_h=0.2)
    results = []
    for ok in (False, False, True, False, False, False):
        code, mailer = await _check(full_api, tmp_path, readyz=ok, alert_email="ops@corp.example")
        results.append(len(mailer.outbox))
    assert results == [0, 0, 0, 0, 0, 1]


async def test_check_without_alert_email_only_logs(full_api, db, tmp_path, caplog):
    caplog.set_level(logging.WARNING)
    code, mailer = await _check(full_api, tmp_path)  # 수집 기록 없음
    assert code == 1 and mailer.outbox == []
    assert "ALERT_EMAIL" in caplog.text


async def test_check_recovered_alert_can_fire_again(full_api, db, tmp_path):
    _, a = await _check(full_api, tmp_path, disk=0.95, alert_email="ops@corp.example")
    await _run(db, status="ok", finished_ago_h=0.1)
    _, b = await _check(full_api, tmp_path, disk=0.1, alert_email="ops@corp.example")
    _, c = await _check(full_api, tmp_path, disk=0.95, alert_email="ops@corp.example")
    assert len(a.outbox) == 1 and b.outbox == [] and len(c.outbox) == 1
