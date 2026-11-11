"""로그 설정. 서비스키·비밀번호·토큰이 어떤 로그에도 남지 않게 한다 (규칙 4, §9.5).

- G2B 서비스키는 쿼리스트링에 실린다. httpx·httpcore는 INFO에서 요청 URL 전체를 찍으므로
  WARNING으로 올린다.
- 모든 핸들러에 마스킹 필터를 단다(다른 라이브러리가 URL·본문을 찍어도 안전).
"""

from __future__ import annotations

import logging
import re

_KEY = re.compile(r"(ServiceKey=)[^&\s'\"]+", re.IGNORECASE)
# 비밀번호·토큰 (§9.5 로그, §9.8-12): key=value, "key": "value", JWT 형태
_SECRET_FIELDS = r"(?:password|current_password|new_password|token|access_token|refresh_token)"
_KV = re.compile(rf"(\b{_SECRET_FIELDS}=)[^&\s;'\",]+", re.IGNORECASE)
_JSON = re.compile(rf"(['\"]{_SECRET_FIELDS}['\"]\s*:\s*['\"])[^'\"]*", re.IGNORECASE)
_JWT = re.compile(r"\beyJ[\w-]+\.[\w-]+\.[\w-]+")


def mask_secrets(text: str) -> str:
    text = _KEY.sub(r"\1***", text)
    text = _KV.sub(r"\1***", text)
    text = _JSON.sub(r"\1***", text)
    return _JWT.sub("***", text)


class MaskServiceKey(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        masked = mask_secrets(msg)
        if masked != msg:
            record.msg, record.args = masked, None
        return True


def configure_logging(level: int = logging.INFO) -> None:
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    for name in ("httpx", "httpcore"):
        logging.getLogger(name).setLevel(logging.WARNING)
    for handler in logging.getLogger().handlers:
        if not any(isinstance(f, MaskServiceKey) for f in handler.filters):
            handler.addFilter(MaskServiceKey())
