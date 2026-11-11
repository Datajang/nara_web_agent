"""§11.4 클라이언트 IP: 127.0.0.1(nginx)에서 온 요청만 X-Forwarded-For를 믿는다.

nginx는 X-Forwarded-For를 $remote_addr로 덮어쓰므로 값은 하나다. 덮어쓰지 않는 설정이어도
클라이언트가 보낸 값으로 속일 수 없게 마지막 값(nginx가 붙인 값)을 쓴다.
"""

from starlette.requests import Request

from app.api.deps import client_ip


def _req(host: str | None, xff: str | None = None) -> Request:
    headers = [(b"x-forwarded-for", xff.encode())] if xff is not None else []
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": headers,
        "client": (host, 5555) if host else None,
    }
    return Request(scope)


def test_direct_request_uses_socket_address():
    assert client_ip(_req("203.0.113.7")) == "203.0.113.7"


def test_untrusted_peer_cannot_spoof_with_header():
    assert client_ip(_req("203.0.113.7", "198.51.100.1")) == "203.0.113.7"


def test_trusted_proxy_header_is_used():
    assert client_ip(_req("127.0.0.1", "198.51.100.1")) == "198.51.100.1"
    assert client_ip(_req("::1", "198.51.100.2")) == "198.51.100.2"


def test_client_supplied_prefix_is_ignored():
    """nginx가 $proxy_add_x_forwarded_for를 쓰면 '<클라이언트가 보낸 값>, <실제 IP>'가 된다."""
    assert client_ip(_req("127.0.0.1", "1.2.3.4, 198.51.100.9")) == "198.51.100.9"


def test_malformed_header_falls_back_to_peer():
    assert client_ip(_req("127.0.0.1", "not-an-ip")) == "127.0.0.1"
    assert client_ip(_req("127.0.0.1", "")) == "127.0.0.1"


def test_missing_client():
    assert client_ip(_req(None)) == "unknown"
