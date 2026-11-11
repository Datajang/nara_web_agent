"""로그 설정. G2B 서비스키는 쿼리스트링에 실리므로 어떤 로그에도 남지 않게 한다 (규칙 4).

- httpx·httpcore는 INFO에서 요청 URL 전체를 찍으므로 WARNING으로 올린다.
- 모든 핸들러에 `ServiceKey=...`를 가리는 필터를 단다(다른 라이브러리가 URL을 찍어도 안전).
"""

from __future__ import annotations

import logging
import re

_KEY = re.compile(r"(ServiceKey=)[^&\s'\"]+", re.IGNORECASE)


class MaskServiceKey(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        masked = _KEY.sub(r"\1***", msg)
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
