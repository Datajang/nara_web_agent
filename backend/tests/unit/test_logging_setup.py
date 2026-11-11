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


def test_passwords_tokens_and_jwts_masked():
    """§9.8-12: 비밀번호·토큰 문자열이 로그에 남지 않는다."""
    buf = io.StringIO()
    handler = logging.StreamHandler(buf)
    handler.addFilter(MaskServiceKey())
    log = logging.getLogger("test.mask2")
    log.addHandler(handler)
    log.setLevel(logging.INFO)
    jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiI3In0.c2lnbmF0dXJlLXZhbHVl"
    try:
        log.info('body {"email": "a@b.c", "password": "hunter2-secret"}')
        log.info("link https://x/verify-email?token=RAWTOKEN123&a=1")
        log.info("cookie refresh_token=OPAQUE456; access_token=%s", jwt)
        log.info("new_password=pw-new-999 current_password=pw-old-888")
    finally:
        log.removeHandler(handler)
    out = buf.getvalue()
    for secret in ("hunter2-secret", "RAWTOKEN123", "OPAQUE456", jwt, "pw-new-999", "pw-old-888"):
        assert secret not in out
    assert "a@b.c" in out  # 이메일은 남는다(감사용)
