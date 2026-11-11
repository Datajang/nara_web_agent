"""로그 설정. 서비스키·비밀번호·토큰이 어떤 로그에도 남지 않게 한다 (규칙 4, §9.5).

- G2B 서비스키는 쿼리스트링에 실린다. httpx·httpcore는 INFO에서 요청 URL 전체를 찍으므로
  WARNING으로 올린다.
- 모든 핸들러에 마스킹 필터를 단다(다른 라이브러리가 URL·본문을 찍어도 안전).
- 운영은 `LOG_FORMAT=json`: 한 줄 JSON (§11.7 필드 ts, level, event, request_id, user_id,
  bid_key, duration_ms). journald가 수집한다.
"""

from __future__ import annotations

import json
import logging
import os
import re
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

_KEY = re.compile(r"(ServiceKey=)[^&\s'\"]+", re.IGNORECASE)
# 비밀번호·토큰 (§9.5 로그, §9.8-12): key=value, "key": "value", JWT 형태
_SECRET_FIELDS = r"(?:password|current_password|new_password|token|access_token|refresh_token)"
_KV = re.compile(rf"(\b{_SECRET_FIELDS}=)[^&\s;'\",]+", re.IGNORECASE)
_JSON = re.compile(rf"(['\"]{_SECRET_FIELDS}['\"]\s*:\s*['\"])[^'\"]*", re.IGNORECASE)
_JWT = re.compile(r"\beyJ[\w-]+\.[\w-]+\.[\w-]+")

# 요청 단위 문맥. dict를 공유해 하위 작업(의존성·스레드풀)이 user_id를 채우면 미들웨어도 본다.
_context: ContextVar[dict[str, Any] | None] = ContextVar("log_context", default=None)
_CONTEXT_FIELDS = ("request_id", "user_id")
# extra로 받아 JSON에 싣는 필드. 이 목록 밖의 extra는 버린다(본문·이메일이 새지 않게).
_EXTRA_FIELDS = ("bid_key", "duration_ms", "method", "path", "status", "source", "stage")


def mask_secrets(text: str) -> str:
    text = _KEY.sub(r"\1***", text)
    text = _KV.sub(r"\1***", text)
    text = _JSON.sub(r"\1***", text)
    return _JWT.sub("***", text)


def current_context() -> dict[str, Any]:
    """지금 요청의 로그 문맥. 요청 밖이면 버려지는 빈 dict."""
    ctx = _context.get()
    return ctx if ctx is not None else {}


@contextmanager
def log_context(**fields: Any) -> Iterator[dict[str, Any]]:
    ctx = dict(fields)
    token = _context.set(ctx)
    try:
        yield ctx
    finally:
        _context.reset(token)


class MaskServiceKey(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        masked = mask_secrets(msg)
        if masked != msg:
            record.msg, record.args = masked, None
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        out: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "event": getattr(record, "event", None) or record.name,
            "msg": mask_secrets(record.getMessage()),
        }
        ctx = current_context()
        for key in _CONTEXT_FIELDS:
            value = getattr(record, key, None)
            if value is None:
                value = ctx.get(key)
            if value is not None:
                out[key] = value
        for key in _EXTRA_FIELDS:
            value = getattr(record, key, None)
            if value is not None:
                out[key] = value
        if record.exc_info:
            out["exc"] = mask_secrets(self.formatException(record.exc_info))
        return json.dumps(out, ensure_ascii=False, default=str)


def configure_logging(level: int = logging.INFO, fmt: str | None = None) -> None:
    fmt = fmt or os.environ.get("LOG_FORMAT", "text")
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    root = logging.getLogger()
    if fmt == "json":
        for handler in root.handlers:
            handler.setFormatter(JsonFormatter())
    for name in ("httpx", "httpcore"):
        logging.getLogger(name).setLevel(logging.WARNING)
    for handler in root.handlers:
        if not any(isinstance(f, MaskServiceKey) for f in handler.filters):
            handler.addFilter(MaskServiceKey())
