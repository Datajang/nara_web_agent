"""서비스 계층 의존성 묶음. 외부 호출(G2B·LLM·다운로드)은 모두 인터페이스 뒤에 둔다 (규칙 3)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime

from app.config import Settings
from app.db.session import Database
from app.files.download import Downloader
from app.g2b.client import G2BClient
from app.llm.base import LLMClient


def utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass
class Deps:
    db: Database
    g2b: G2BClient | None
    llm: LLMClient | None
    downloader: Downloader | None
    settings: Settings
    clock: Callable[[], datetime] = field(default=utcnow)
