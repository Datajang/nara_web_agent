"""환경변수 설정 (SPEC 부록 A, §5.10).

저장소 루트 `.env`는 자동으로 읽지 않는다(v1 값·비밀값이 섞여 있고 테스트가 읽으면 안 됨).
`NARA_ENV_FILE`에 쉼표로 구분한 경로를 주면 그 파일들만 읽는다. 운영은 systemd EnvironmentFile.
"""

from __future__ import annotations

import os
from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


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
    llm_max_concurrency: int = 4

    @property
    def file_hosts(self) -> frozenset[str]:
        return frozenset(
            h.strip().lower() for h in self.g2b_file_host_allowlist.split(",") if h.strip()
        )


@lru_cache
def get_settings() -> Settings:
    files = [p for p in os.environ.get("NARA_ENV_FILE", "").split(",") if p.strip()]
    return Settings(_env_file=tuple(files) or None)  # type: ignore[call-arg]
