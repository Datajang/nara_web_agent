"""deploy.sh·backup.sh·restore.sh를 가짜 명령(PATH 앞에 둔 스크립트)으로 실제 실행한다.

운영 서버 명령은 실행하지 않는다. git·uv·npm·systemctl·curl·pg_dump·age 등은 호출 기록만 남긴다.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from tests.deploy.units import DEPLOY

FAKES = {
    # git: describe는 지금 태그, rev-parse --verify는 FAKE_TAGS 안의 태그만 성공
    "git": r"""
case "$1" in
  describe) cat "$FAKE_STATE/current" ;;
  rev-parse) for t in $FAKE_TAGS; do [ "refs/tags/$t" = "${@: -1}" ] && exit 0; done; exit 1 ;;
  checkout) echo "${@: -1}" | sed "s#^refs/tags/##" > "$FAKE_STATE/current" ;;
esac
""",
    "npm": r"""
if [ "$1 $2" = "run build" ]; then
  mkdir -p dist; echo "<html>$(cat "$FAKE_STATE/current")" > dist/index.html
fi
""",
    "curl": r"""
n=$(cat "$FAKE_STATE/curl_count" 2>/dev/null || echo 0); echo $((n+1)) > "$FAKE_STATE/curl_count"
[ "${FAKE_CURL_FAIL:-}" = "always" ] && exit 22
[ "${FAKE_CURL_FAIL:-}" = "$(cat "$FAKE_STATE/current")" ] && exit 22
exit 0
""",
    "runuser": r"""
while [ "$1" != "--" ]; do shift; done; shift; exec "$@"
""",
    "pg_dump": r"""
[ -n "${PGPASSWORD:-}" ] || { echo "PGPASSWORD 없음" >&2; exit 2; }
echo "DUMP:$PGUSER@$PGHOST:$PGPORT/$PGDATABASE"
""",
    "age": r"""
out=""; while [ $# -gt 0 ]; do [ "$1" = "-o" ] && out="$2"; shift; done
if [ -n "$out" ]; then { echo "AGE("; cat; } > "$out"; else sed '1d'; fi
""",
    "psql": r"""
case "$*" in *alembic_version*) echo 0004 ;; *count*) echo 42 ;; esac
""",
}
LOGGED = ["uv", "systemctl", "sleep", "gcloud", "createdb", "pg_restore", "dropdb", "alembic"]


@pytest.fixture
def sandbox(tmp_path: Path):
    bin_dir, state = tmp_path / "bin", tmp_path / "state"
    bin_dir.mkdir()
    state.mkdir()
    calls = tmp_path / "calls.log"
    for name in [*FAKES, *LOGGED]:
        body = FAKES.get(name, "")
        script = bin_dir / name
        script.write_text(f'#!/usr/bin/env bash\necho "{name} $*" >> "{calls}"\n{body}')
        script.chmod(0o755)
    root = tmp_path / "opt"
    app = root / "app"
    for sub in ("backend", "frontend", "deploy/systemd"):
        (app / sub).mkdir(parents=True)
    (app / "deploy/systemd/nara-api.service").write_text("[Unit]\n")
    (root / "venv/bin").mkdir(parents=True)
    (root / "venv/bin/alembic").symlink_to(bin_dir / "alembic")
    (state / "current").write_text("v0.1.0")
    env_file = tmp_path / "nara.env"
    env_file.write_text(
        "ENV=production\nDATABASE_URL=postgresql+asyncpg://nara:s3cr3tpw@127.0.0.1:5434/nara\n"
    )
    env = {
        **os.environ,
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "FAKE_STATE": str(state),
        "FAKE_TAGS": "v0.1.0 v0.2.0",
        "NARA_ROOT": str(root),
        "NARA_ENV_FILE_PATH": str(env_file),
        "NARA_SYSTEMD_DIR": str(tmp_path / "systemd"),
        "PG_BIN": str(bin_dir),
    }
    (tmp_path / "systemd").mkdir()

    class Box:
        def __init__(self) -> None:
            self.tmp, self.root, self.state, self.env = tmp_path, root, state, env

        def run(self, script: str, *args: str, **extra: str) -> subprocess.CompletedProcess[str]:
            return subprocess.run(
                ["bash", str(DEPLOY / script), *args],
                env={**self.env, **extra},
                capture_output=True,
                text=True,
                timeout=30,
            )

        def calls(self) -> list[str]:
            return calls.read_text().splitlines() if calls.exists() else []

    return Box()


def _index(calls: list[str], prefix: str) -> int:
    return next(i for i, c in enumerate(calls) if c.startswith(prefix))


# ---------- deploy.sh (§11.6) ----------


def test_deploy_runs_steps_in_order(sandbox):
    r = sandbox.run("deploy.sh", "v0.2.0")
    assert r.returncode == 0, r.stderr
    calls = sandbox.calls()
    order = [
        "git fetch --tags",
        "git checkout",
        "uv sync --locked --no-dev",
        "npm ci",
        "npm run build",
        "alembic upgrade head",
        "systemctl daemon-reload",
        "systemctl restart nara-api",
        "curl -fsS",
    ]
    idx = [_index(calls, p) for p in order]
    assert idx == sorted(idx), calls
    assert not any(c.startswith("systemctl restart nara-vllm") for c in calls)
    assert (sandbox.root / ".prev").read_text().strip() == "v0.1.0"
    dist = sandbox.root / "frontend" / "dist"
    assert dist.is_symlink() and (dist / "index.html").read_text().strip() == "<html>v0.2.0"
    assert (sandbox.tmp / "systemd" / "nara-api.service").exists()  # 유닛 복사


def test_deploy_rejects_unknown_tag_before_touching_anything(sandbox):
    r = sandbox.run("deploy.sh", "v9.9.9")
    assert r.returncode != 0 and "v9.9.9" in r.stderr
    assert not any(c.startswith(("git checkout", "systemctl", "uv")) for c in sandbox.calls())
    assert not (sandbox.root / ".prev").exists()


def test_deploy_rolls_back_when_health_fails(sandbox):
    r = sandbox.run("deploy.sh", "v0.2.0", FAKE_CURL_FAIL="v0.2.0")
    assert r.returncode != 0
    assert "v0.1.0" in r.stderr  # 어디로 되돌렸는지 알린다
    calls = [c for c in sandbox.calls() if c.startswith("git checkout")]
    assert calls[0].endswith("v0.2.0") and calls[-1].endswith("v0.1.0")
    assert (sandbox.state / "current").read_text().strip() == "v0.1.0"
    assert (sandbox.root / ".prev").read_text().strip() == "v0.1.0"  # 롤백이 덮어쓰지 않음
    assert (sandbox.root / "frontend/dist/index.html").read_text().strip() == "<html>v0.1.0"
    assert int((sandbox.state / "curl_count").read_text()) == 30 + 1  # 30회 재시도 후 롤백 확인 1회


def test_deploy_stops_if_rollback_also_fails(sandbox):
    r = sandbox.run("deploy.sh", "v0.2.0", FAKE_CURL_FAIL="always")
    assert r.returncode != 0 and "롤백" in r.stderr
    assert len([c for c in sandbox.calls() if c.startswith("git checkout")]) == 2  # 무한 반복 없음


def test_deploy_restarts_vllm_only_when_asked(sandbox):
    assert sandbox.run("deploy.sh", "v0.2.0", NARA_RESTART_VLLM="1").returncode == 0
    assert "systemctl restart nara-vllm" in sandbox.calls()


# ---------- backup.sh (§11.5) ----------


def _backup_dir(sandbox) -> Path:
    d = sandbox.tmp / "backups"
    (d / "weekly").mkdir(parents=True, exist_ok=True)
    return d


def test_backup_encrypts_dump_without_password_in_argv(sandbox):
    out = _backup_dir(sandbox)
    r = sandbox.run(
        "backup.sh",
        NARA_BACKUP_DIR=str(out),
        NARA_BACKUP_PUBKEY=str(sandbox.tmp / "pub.txt"),
        NARA_BACKUP_DATE="2026-11-11",
    )
    assert r.returncode == 0, r.stderr
    f = out / "nara-2026-11-11.dump.age"
    assert f.read_text().splitlines() == ["AGE(", "DUMP:nara@127.0.0.1:5434/nara"]
    assert oct(f.stat().st_mode & 0o777) == "0o600"
    assert not (out / "weekly" / "nara-2026-11-11.dump.age").exists()  # 수요일
    log = "\n".join(sandbox.calls())
    assert "s3cr3tpw" not in log and "s3cr3tpw" not in r.stdout + r.stderr
    assert "-Fc" in log and "gcloud" not in log


def test_backup_keeps_14_daily_and_4_weekly(sandbox):
    out = _backup_dir(sandbox)
    for day in range(1, 21):
        (out / f"nara-2026-10-{day:02d}.dump.age").write_text("old")
    for day in ("09-06", "09-13", "09-20", "09-27", "10-04", "10-11"):
        (out / "weekly" / f"nara-2026-{day}.dump.age").write_text("old")
    r = sandbox.run(
        "backup.sh",
        NARA_BACKUP_DIR=str(out),
        NARA_BACKUP_PUBKEY=str(sandbox.tmp / "pub.txt"),
        NARA_BACKUP_DATE="2026-11-15",  # 일요일
        BACKUP_GCS_URI="gs://bucket/nara",
    )
    assert r.returncode == 0, r.stderr
    daily = sorted(p.name for p in out.glob("nara-*.dump.age"))
    assert len(daily) == 14 and daily[-1] == "nara-2026-11-15.dump.age"
    assert daily[0] == "nara-2026-10-08.dump.age"
    weekly = sorted(p.name for p in (out / "weekly").glob("*.dump.age"))
    assert weekly == [
        "nara-2026-09-27.dump.age",
        "nara-2026-10-04.dump.age",
        "nara-2026-10-11.dump.age",
        "nara-2026-11-15.dump.age",
    ]
    assert any(c.startswith("gcloud storage cp") for c in sandbox.calls())


def test_backup_failure_leaves_no_partial_file(sandbox):
    out = _backup_dir(sandbox)
    env_file = Path(sandbox.env["NARA_ENV_FILE_PATH"])
    env_file.write_text("DATABASE_URL=postgresql+asyncpg://nara@127.0.0.1:5434/nara\n")  # 비번 없음
    r = sandbox.run(
        "backup.sh",
        NARA_BACKUP_DIR=str(out),
        NARA_BACKUP_PUBKEY=str(sandbox.tmp / "pub.txt"),
        NARA_BACKUP_DATE="2026-11-11",
    )
    assert r.returncode != 0
    assert list(out.glob("*.age*")) == []


# ---------- restore.sh (§11.5 복원 연습) ----------


def _dump(sandbox) -> Path:
    f = sandbox.tmp / "nara-2026-11-11.dump.age"
    f.write_text("AGE(\nDUMP\n")
    return f


def test_restore_into_scratch_db_and_report(sandbox):
    r = sandbox.run(
        "restore.sh",
        str(_dump(sandbox)),
        "nara_restore_test",
        NARA_AGE_IDENTITY=str(sandbox.tmp / "key.txt"),
    )
    assert r.returncode == 0, r.stderr
    calls = sandbox.calls()
    order = ["createdb", "pg_restore", "psql"]
    idx = [_index(calls, p) for p in order]
    assert idx == sorted(idx), calls
    assert "nara_restore_test" in calls[_index(calls, "createdb")]
    assert "alembic_version: 0004" in r.stdout
    for table in ("bids", "users", "analyses", "feedback"):
        assert f"{table}: 42" in r.stdout


def test_restore_refuses_live_database(sandbox):
    r = sandbox.run(
        "restore.sh", str(_dump(sandbox)), "nara", NARA_AGE_IDENTITY=str(sandbox.tmp / "k")
    )
    assert r.returncode != 0 and "운영 DB" in r.stderr
    assert not any(c.startswith(("createdb", "pg_restore", "dropdb")) for c in sandbox.calls())


def test_restore_requires_identity(sandbox):
    r = sandbox.run("restore.sh", str(_dump(sandbox)), "nara_restore_test")
    assert r.returncode != 0 and "NARA_AGE_IDENTITY" in r.stderr
