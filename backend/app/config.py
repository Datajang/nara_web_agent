"""환경변수 설정 (SPEC 부록 A, §5.10).

저장소 루트 `.env`는 자동으로 읽지 않는다(v1 값·비밀값이 섞여 있고 테스트가 읽으면 안 됨).
`NARA_ENV_FILE`에 쉼표로 구분한 경로를 주면 그 파일들만 읽는다. 운영은 systemd EnvironmentFile.
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

# 개발용 기본 비밀키. ENV=production에서는 시작을 거부한다 (§9.5, v1 dev-secret-key 문제)
DEFAULT_SECRET_KEY = "dev-insecure-secret-key-change-me"


class ConfigError(RuntimeError):
    """운영 시작 검사 실패 (§9.7 ENV=production)."""


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore")

    database_url: str = "postgresql+asyncpg://nara@127.0.0.1:5433/nara"
    db_pool_size: int = 10
    lock_pool_size: int = 10  # §5.5 advisory lock 전용 풀

    # G2B (§5.2). 키 이름은 v1과 같다.
    nara_api_key: SecretStr = SecretStr("")
    nara_prespec_api_key: SecretStr = SecretStr("")
    g2b_daily_call_budget: int = 1000  # 포털 한도 1000회(사용자 확인), 두 소스 합산
    g2b_page_size: int = 999  # docs/decisions/2026-11-11-g2b-probe.md

    # 첨부 파일 (§5.6)
    g2b_file_host_allowlist: str = "www.g2b.go.kr"  # 쉼표 구분
    file_max_mb: int = 50

    collector_backfill_days: int = 90
    search_fill_wait_s: float = (
        5  # 커버리지 밖 검색: 이만큼만 기다리고 '수집 중'으로 응답 (P3a 결정)
    )

    # LLM (§8.1·§8.2, docs/LLM_SETUP.md). fake는 개발 화면용(운영 금지), none은 LLM 없이 기동
    llm_backend: Literal["vllm", "fake", "none"] = "vllm"
    llm_base_url: str = "http://127.0.0.1:8011/v1"
    llm_model: str = "brain"  # vLLM --served-model-name
    llm_model_id: str = "q35-9b"  # PROMPT_VERSION 접미사 (예: v1+q35-9b)
    llm_api_key: SecretStr = SecretStr("")
    llm_timeout_s: float = 180
    llm_max_concurrency: int = 4
    llm_tokenizer_path: str = ""  # Qwen tokenizer.json. 비우면 글자 수 × 1.2 (§8.3-1)
    llm_lock_wait_s: float = 120  # single-flight 대기 상한 (§5.5)
    summary_max_chunks: int = 12  # §8.3-4

    # 인증 (§9.7)
    env: Literal["development", "test", "production"] = "development"
    secret_key: SecretStr = SecretStr(DEFAULT_SECRET_KEY)
    app_origin: str = "http://localhost:5173"
    cookie_secure: bool = True
    access_token_minutes: int = 15
    refresh_token_days: int = 14
    allowed_email_domains: str = ""  # 쉼표 구분
    require_admin_approval: bool | None = None  # None이면 도메인 정책으로 결정
    password_min_length: int = 10
    login_max_failures: int = 5
    login_lock_minutes: int = 15
    verify_token_hours: int = 24
    reset_token_minutes: int = 60
    rate_limit_enabled: bool = True  # §6.1 인메모리 토큰 버킷(단일 워커)

    # 메일 (§9.2-8). memory는 테스트·개발 전용(P2 지시)
    mail_backend: Literal["console", "smtp", "memory"] = "console"
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: SecretStr = SecretStr("")
    mail_from: str = ""
    service_name: str = "나라장터 도우미"  # §9.6 [가정] 임시 이름

    # 운영 경보 (§11.7 [가정] 기준값). 비우면 메일 대신 로그만 남긴다
    alert_email: str = ""
    alert_collector_stale_h: float = 2
    alert_budget_ratio: float = 0.8
    alert_disk_ratio: float = 0.8
    alert_repeat_h: float = 6  # 같은 경보를 다시 보내기까지

    @property
    def file_hosts(self) -> frozenset[str]:
        return frozenset(
            h.strip().lower() for h in self.g2b_file_host_allowlist.split(",") if h.strip()
        )

    @property
    def email_domains(self) -> frozenset[str]:
        return frozenset(
            d.strip().lower().lstrip("@")
            for d in self.allowed_email_domains.split(",")
            if d.strip()
        )

    @property
    def approval_required(self) -> bool:
        """§9.1: 허용 도메인이 없으면 승인을 강제하고, 있으면 기본 false."""
        if not self.email_domains:
            return True
        return bool(self.require_admin_approval)


def check_startup(settings: Settings) -> list[str]:
    """시작 검사. 운영에서 위험한 설정이면 ConfigError, 경고는 문자열 목록으로 돌려준다."""
    warnings: list[str] = []
    if not settings.email_domains:
        warnings.append(
            "ALLOWED_EMAIL_DOMAINS가 비어 있어 누구나 가입할 수 있다: 관리자 승인을 강제한다"
        )
    if settings.env != "production":
        return warnings
    errors: list[str] = []
    secret = settings.secret_key.get_secret_value()
    if secret == DEFAULT_SECRET_KEY or len(secret.encode()) < 32:
        errors.append("SECRET_KEY가 기본값이거나 32바이트 미만")
    if settings.mail_backend != "smtp":
        errors.append(f"MAIL_BACKEND={settings.mail_backend}는 개발 전용")
    elif not (settings.smtp_host and settings.mail_from):
        errors.append("MAIL_BACKEND=smtp에는 SMTP_HOST·MAIL_FROM이 필요")
    if not settings.app_origin.startswith("https://"):
        errors.append("APP_ORIGIN은 https여야 한다")
    if not settings.cookie_secure:
        errors.append("COOKIE_SECURE=false는 개발 전용")
    if settings.llm_backend == "fake":
        errors.append("LLM_BACKEND=fake는 개발 전용")
    if errors:
        raise ConfigError("; ".join(errors))
    return warnings


@lru_cache
def get_settings() -> Settings:
    files = [p for p in os.environ.get("NARA_ENV_FILE", "").split(",") if p.strip()]
    return Settings(_env_file=tuple(files) or None)  # type: ignore[call-arg]
