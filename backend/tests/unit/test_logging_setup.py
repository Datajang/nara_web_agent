"""규칙 4: CLI 로그에 서비스키가 남지 않는다 (httpx INFO 로그가 URL 전체를 찍는 문제 회귀 방지)."""

import io
import logging

from app.logging_setup import MaskServiceKey, configure_logging


def test_httpx_request_logs_are_suppressed():
    configure_logging()
    assert logging.getLogger("httpx").getEffectiveLevel() >= logging.WARNING
    assert logging.getLogger("httpcore").getEffectiveLevel() >= logging.WARNING


def test_service_key_masked_in_any_log_record():
    buf = io.StringIO()
    handler = logging.StreamHandler(buf)
    handler.addFilter(MaskServiceKey())
    log = logging.getLogger("test.mask")
    log.addHandler(handler)
    log.setLevel(logging.INFO)
    try:
        log.info("GET %s", "http://apis.data.go.kr/x?ServiceKey=SECRET123%2Babc&type=json")
    finally:
        log.removeHandler(handler)
    out = buf.getvalue()
    assert "SECRET123" not in out and "ServiceKey=***&type=json" in out
