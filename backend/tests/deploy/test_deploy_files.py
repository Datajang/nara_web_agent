"""§11.3·§11.4·§9.5 배포 파일 검사. 운영 서버에 올리기 전에 저장소에서 어긋남을 잡는다."""

from __future__ import annotations

import re
import subprocess

import pytest
from pydantic import SecretStr

from app.config import Settings, check_startup
from tests.deploy.units import API_PORT, DEPLOY, VLLM_PORT, env_example, nginx_locations, one, unit

SERVICES = [
    "nara-vllm.service",
    "nara-api.service",
    "nara-collector.service",
    "nara-backup.service",
    "nara-alert.service",
]
TIMERS = ["nara-collector.timer", "nara-backup.timer", "nara-alert.timer"]
APP_SERVICES = ["nara-api.service", "nara-collector.service", "nara-alert.service"]


def test_v1_deploy_files_are_gone():
    """v1 유닛(EXAONE·/app/nara-web)은 git 기록(61519ad)에만 남긴다."""
    for name in ("nara-api.service", "nara-vllm.service", "nginx.conf"):
        assert not (DEPLOY / name).exists(), name


@pytest.mark.parametrize("name", SERVICES)
def test_services_run_as_nara(name):
    u = unit(name)
    assert one(u, "Service", "User") == "nara"
    assert "/app/nara-web" not in (DEPLOY / "systemd" / name).read_text()


@pytest.mark.parametrize("name", TIMERS)
def test_each_timer_has_service_and_catches_up(name):
    assert (DEPLOY / "systemd" / name.replace(".timer", ".service")).exists()
    u = unit(name)
    assert u["Timer"]["OnCalendar"]
    assert one(u, "Timer", "Persistent") == "true"
    assert one(u, "Install", "WantedBy") == "timers.target"


@pytest.mark.parametrize("name", APP_SERVICES + ["nara-backup.service"])
def test_app_services_read_env_file_and_are_sandboxed(name):
    u = unit(name)
    assert one(u, "Service", "EnvironmentFile") == "/etc/nara/nara.env"
    assert one(u, "Service", "NoNewPrivileges") == "true"
    assert one(u, "Service", "ProtectSystem") == "strict"
    assert one(u, "Service", "PrivateTmp") == "true"


@pytest.mark.parametrize("name", APP_SERVICES)
def test_app_services_use_release_venv_and_private_tmpdir(name):
    u = unit(name)
    assert one(u, "Service", "WorkingDirectory") == "/opt/nara/app/backend"
    assert one(u, "Service", "ExecStart").startswith("/opt/nara/venv/bin/")
    assert "/var/lib/nara" in one(u, "Service", "ReadWritePaths").split()
    assert "TMPDIR=/var/lib/nara/tmp" in u["Service"]["Environment"]


def test_api_unit():
    u = unit("nara-api.service")
    exec_start = one(u, "Service", "ExecStart")
    assert f"--host 127.0.0.1 --port {API_PORT}" in exec_start
    assert "--workers 1" in exec_start  # §6.1 인메모리 속도 제한
    assert "--no-access-log" in exec_start  # 요청 로그는 앱이 JSON으로 남긴다(쿼리스트링 제외)
    assert "--proxy-headers" not in exec_start  # XFF는 앱이 127.0.0.1에서만 믿는다(§11.4)
    assert one(u, "Unit", "Wants") == "nara-vllm.service"  # 약한 의존: vLLM이 죽어도 API는 산다
    assert "postgresql.service" in one(u, "Unit", "After")
    assert one(u, "Service", "Restart") == "always"


def test_vllm_unit_matches_measured_flags():
    """docs/LLM_SETUP.md에서 측정한 FP8 명령. 키는 인자 대신 VLLM_API_KEY 환경변수로."""
    u = unit("nara-vllm.service")
    cmd = one(u, "Service", "ExecStart")
    assert cmd.startswith("/opt/nara/vllm-venv/bin/vllm serve Qwen/Qwen3.5-9B ")
    for flag in (
        "--served-model-name brain",
        "--quantization fp8",
        "--max-model-len 32768",
        "--max-num-seqs 8",
        "--gpu-memory-utilization 0.90",
        "--language-model-only",
        "--reasoning-parser qwen3",
        "--enable-auto-tool-choice",
        "--tool-call-parser qwen3_coder",
        """--default-chat-template-kwargs '{"enable_thinking": false}'""",
        f"--host 127.0.0.1 --port {VLLM_PORT}",
    ):
        assert flag in cmd, flag
    assert "--api-key" not in cmd  # ps에 보이지 않게
    assert "HF_HOME=/var/lib/hf-cache" in u["Service"]["Environment"]
    assert one(u, "Service", "EnvironmentFile") == "/etc/nara/vllm.env"
    assert int(one(u, "Service", "TimeoutStartSec")) >= 600


def test_collector_and_backup_and_alert_schedules():
    collector = unit("nara-collector.timer")
    assert one(collector, "Timer", "RandomizedDelaySec") == "60"
    backup = unit("nara-backup.timer")
    assert one(backup, "Timer", "OnCalendar") == "*-*-* 03:30:00 Asia/Seoul"
    alert = unit("nara-alert.timer")
    assert one(alert, "Timer", "OnCalendar") == "*:0/10"
    cmd = one(unit("nara-alert.service"), "Service", "ExecStart")
    assert f"--readyz-url http://127.0.0.1:{API_PORT}/readyz" in cmd
    backup_svc = unit("nara-backup.service")
    assert one(backup_svc, "Service", "ExecStart") == "/opt/nara/app/deploy/backup.sh"
    assert "/var/backups/nara" in one(backup_svc, "Service", "ReadWritePaths").split()


# ---------- nginx (§11.4, §9.5) ----------

SECURITY_HEADERS = {
    "Strict-Transport-Security": '"max-age=31536000; includeSubDomains"',
    "X-Content-Type-Options": '"nosniff"',
    "Referrer-Policy": '"strict-origin-when-cross-origin"',
    "X-Frame-Options": '"DENY"',
    "Content-Security-Policy": (
        "\"default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
        "frame-ancestors 'none'\""
    ),
}


def _nginx() -> str:
    return (DEPLOY / "nginx" / "nara.conf").read_text()


def test_security_snippet_has_every_header_always():
    text = (DEPLOY / "nginx" / "snippets" / "nara-security.conf").read_text()
    for name, value in SECURITY_HEADERS.items():
        assert f"add_header {name} {value} always;" in text, name


def test_every_location_includes_security_snippet():
    """location에 add_header가 하나라도 있으면 서버 수준 헤더가 상속되지 않는다(§11.4)."""
    locs = nginx_locations(_nginx())
    assert {"/api/", "/assets/", "/"} <= set(locs)
    for name, body in locs.items():
        if "return 404" in body:
            continue
        assert "include snippets/nara-security.conf;" in body, name


def test_api_location_streams_sse_and_overwrites_forwarded_for():
    api = nginx_locations(_nginx())["/api/"]
    assert f"proxy_pass http://127.0.0.1:{API_PORT};" in api
    assert "proxy_buffering off;" in api
    assert "proxy_read_timeout 300s;" in api
    assert "proxy_http_version 1.1;" in api
    assert 'proxy_set_header Connection "";' in api
    # 클라이언트가 보낸 XFF를 이어 붙이지 않고 덮어쓴다(속도 제한·로그인 잠금 IP 위조 방지)
    assert "proxy_set_header X-Forwarded-For $remote_addr;" in api
    assert "$proxy_add_x_forwarded_for" not in _nginx()


def test_health_endpoints_hidden_and_static_caching():
    text = _nginx()
    locs = nginx_locations(text)
    for probe in ("= /healthz", "= /readyz"):
        assert "return 404;" in locs[probe], probe
    assert 'add_header Cache-Control "public, max-age=31536000, immutable";' in locs["/assets/"]
    assert 'add_header Cache-Control "no-cache";' in locs["/"]
    assert "try_files $uri /index.html;" in locs["/"]
    assert "root /opt/nara/frontend/dist;" in text
    assert "client_max_body_size 1m;" in text
    assert "server_tokens off;" in text
    assert "return 301 https://$host$request_uri;" in text
    assert re.search(r"listen 443 ssl http2;", text)


# ---------- nara.env.example (부록 A) ----------

EXTRA_KEYS = {"LOG_FORMAT", "HTTPS_PROXY", "BACKUP_GCS_URI"}


def test_env_example_keys_are_known_and_hold_no_secrets():
    env = env_example()
    known = {name.upper() for name in Settings.model_fields} | EXTRA_KEYS
    assert set(env) <= known, set(env) - known
    for key in (
        "SECRET_KEY",
        "NARA_API_KEY",
        "NARA_PRESPEC_API_KEY",
        "SMTP_PASSWORD",
        "LLM_API_KEY",
    ):
        assert env[key] == "", key  # 값은 서버에서만 채운다
    assert env["ENV"] == "production" and env["LOG_FORMAT"] == "json"
    assert env["LLM_BASE_URL"] == f"http://127.0.0.1:{VLLM_PORT}/v1"
    assert env["APP_ORIGIN"] == "https://nara.example.com"
    assert ":5434/" in env["DATABASE_URL"]  # PG13(5432)·개발 Docker(5433)와 겹치지 않게


def test_env_example_passes_startup_check_once_filled():
    env = {k.lower(): v for k, v in env_example().items() if k not in EXTRA_KEYS}
    env.update(
        secret_key=SecretStr("x" * 48),
        smtp_host="smtp.example.com",
        mail_from="noreply@example.com",
    )
    settings = Settings(**{k: v for k, v in env.items() if v != ""})
    check_startup(settings)  # ConfigError면 실패


# ---------- 스크립트 문법 ----------


@pytest.mark.parametrize("name", ["deploy.sh", "backup.sh", "restore.sh"])
def test_scripts_are_strict_bash(name):
    path = DEPLOY / name
    text = path.read_text()
    assert text.startswith("#!/usr/bin/env bash\n")
    assert "set -euo pipefail" in text
    assert path.stat().st_mode & 0o111, "실행 권한"
    subprocess.run(["bash", "-n", str(path)], check=True)
