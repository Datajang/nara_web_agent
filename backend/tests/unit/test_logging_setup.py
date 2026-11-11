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


# ---------- §11.7 JSON 한 줄 로그 ----------

import json  # noqa: E402

from app.logging_setup import JsonFormatter, log_context  # noqa: E402


def _json_line(record_fn) -> dict:
    buf = io.StringIO()
    handler = logging.StreamHandler(buf)
    handler.setFormatter(JsonFormatter())
    handler.addFilter(MaskServiceKey())
    log = logging.getLogger("test.json")
    log.addHandler(handler)
    log.setLevel(logging.INFO)
    log.propagate = False
    try:
        record_fn(log)
    finally:
        log.removeHandler(handler)
    lines = buf.getvalue().splitlines()
    assert len(lines) == 1, lines  # 한 줄
    return json.loads(lines[0])


def test_json_log_has_spec_fields():
    with log_context(request_id="r-abc123") as ctx:
        ctx["user_id"] = 7
        out = _json_line(
            lambda log: log.info(
                "done", extra={"event": "analyze", "bid_key": "R26BK1-000", "duration_ms": 42}
            )
        )
    assert {k: out[k] for k in ("level", "event", "request_id", "user_id", "bid_key")} == {
        "level": "INFO",
        "event": "analyze",
        "request_id": "r-abc123",
        "user_id": 7,
        "bid_key": "R26BK1-000",
    }
    assert out["duration_ms"] == 42 and out["msg"] == "done"
    assert out["ts"].endswith("Z") or "+00:00" in out["ts"]


def test_json_log_defaults_event_to_logger_and_omits_empty_context():
    out = _json_line(lambda log: log.warning("hello %s", "x"))
    assert out["event"] == "test.json" and out["msg"] == "hello x"
    assert "request_id" not in out and "user_id" not in out


def test_json_log_masks_secrets_and_exceptions_stay_on_one_line():
    def emit(log):
        try:
            raise ValueError("boom ServiceKey=SECRET999")
        except ValueError:
            log.exception("failed url=http://x/?ServiceKey=SECRET999&a=1")

    out = _json_line(emit)
    raw = json.dumps(out)
    assert "SECRET999" not in raw
    assert "ValueError" in out["exc"]


def test_configure_logging_json_from_env(monkeypatch):
    monkeypatch.setenv("LOG_FORMAT", "json")
    root = logging.getLogger()
    saved = root.handlers[:]
    root.handlers = []
    try:
        configure_logging()
        assert any(isinstance(h.formatter, JsonFormatter) for h in root.handlers)
    finally:
        root.handlers = saved
