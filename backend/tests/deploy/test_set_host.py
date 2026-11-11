"""deploy/set-host.sh: 접속 주소(임시 sslip.io → 나중에 실제 도메인)를 한 번에 바꾼다.

nginx 설정 생성·인증서 발급(없을 때만)·APP_ORIGIN 갱신·nginx 다시 읽기·API 재시작.
가짜 명령으로 실행한다.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from tests.deploy.units import DEPLOY

LOGGED = ["certbot", "nginx", "systemctl"]


@pytest.fixture
def box(tmp_path: Path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    calls = tmp_path / "calls.log"
    for name in LOGGED:
        f = bin_dir / name
        f.write_text(f'#!/usr/bin/env bash\necho "{name} $*" >> "{calls}"\n')
        f.chmod(0o755)
    nginx = tmp_path / "nginx"
    for d in ("sites-available", "sites-enabled", "snippets"):
        (nginx / d).mkdir(parents=True)
    env_file = tmp_path / "nara.env"
    env_file.write_text("ENV=production\nAPP_ORIGIN=https://old.example.org\nSECRET_KEY=keep\n")
    le = tmp_path / "le"
    env = {
        **os.environ,
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "NARA_NGINX_DIR": str(nginx),
        "NARA_ENV_FILE_PATH": str(env_file),
        "NARA_LE_DIR": str(le),
    }

    def run(*args: str, **extra: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["bash", str(DEPLOY / "set-host.sh"), *args],
            env={**env, **extra},
            capture_output=True,
            text=True,
            timeout=30,
        )

    def log() -> list[str]:
        return calls.read_text().splitlines() if calls.exists() else []

    return run, log, nginx, env_file, le


def test_switch_to_ip_host_issues_cert_and_updates_origin(box):
    run, log, nginx, env_file, _ = box
    r = run("34-0-113-5.sslip.io")
    assert r.returncode == 0, r.stderr
    conf = (nginx / "sites-available" / "nara").read_text()
    assert "server_name 34-0-113-5.sslip.io;" in conf
    assert "/etc/letsencrypt/live/34-0-113-5.sslip.io/fullchain.pem" in conf
    assert "nara.example.com" not in conf
    assert (nginx / "sites-enabled" / "nara").is_symlink()
    assert (nginx / "snippets" / "nara-security.conf").exists()
    env = env_file.read_text().splitlines()
    assert env.count("APP_ORIGIN=https://34-0-113-5.sslip.io") == 1
    assert "SECRET_KEY=keep" in env and not any("old.example.org" in x for x in env)
    calls = log()
    certbot = next(i for i, c in enumerate(calls) if c.startswith("certbot certonly"))
    check = calls.index("nginx -t")
    assert certbot < check
    assert "--standalone" in calls[certbot] and "-d 34-0-113-5.sslip.io" in calls[certbot]
    assert calls[-1] == "systemctl restart nara-api"


def test_existing_cert_is_reused(box):
    run, log, *_, le = box
    (le / "live" / "nara.corp.example").mkdir(parents=True)
    (le / "live" / "nara.corp.example" / "fullchain.pem").write_text("x")
    assert run("nara.corp.example").returncode == 0
    assert not any(c.startswith("certbot") for c in log())


@pytest.mark.parametrize("bad", ["", "https://x.com", "a b.com", "x.com;rm", "-d.com", "localhost"])
def test_invalid_host_changes_nothing(box, bad):
    run, log, nginx, env_file, _ = box
    before = env_file.read_text()
    r = run(bad)
    assert r.returncode != 0
    assert log() == [] and env_file.read_text() == before
    assert not (nginx / "sites-available" / "nara").exists()


def test_certbot_email_is_used_when_given(box):
    run, log, *_ = box
    assert run("34-0-113-5.sslip.io", CERTBOT_EMAIL="ops@corp.example").returncode == 0
    line = next(c for c in log() if c.startswith("certbot"))
    assert "-m ops@corp.example" in line and "--register-unsafely-without-email" not in line
