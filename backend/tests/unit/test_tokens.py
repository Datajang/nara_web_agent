"""§9.3 access JWT와 불투명 토큰."""

from datetime import UTC, datetime, timedelta

from app.auth.tokens import create_access_token, decode_access_token, hash_token, new_token

T0 = datetime(2026, 11, 10, 6, 0, tzinfo=UTC)
SECRET = "s" * 40


def test_access_token_roundtrip_with_injected_clock():
    tok = create_access_token(7, "admin", T0, SECRET, minutes=15)
    claims = decode_access_token(tok, SECRET, T0 + timedelta(minutes=14))
    assert claims is not None and claims.user_id == 7 and claims.role == "admin"


def test_access_token_expires():
    tok = create_access_token(7, "member", T0, SECRET, minutes=15)
    assert decode_access_token(tok, SECRET, T0 + timedelta(minutes=15, seconds=1)) is None


def test_access_token_rejects_wrong_secret_and_tampering():
    tok = create_access_token(7, "member", T0, SECRET, minutes=15)
    assert decode_access_token(tok, "x" * 40, T0) is None
    head, body, sig = tok.split(".")
    assert decode_access_token(f"{head}.{body}x.{sig}", SECRET, T0) is None
    assert decode_access_token("garbage", SECRET, T0) is None


def test_new_token_is_random_urlsafe_and_hashed():
    raw1, h1 = new_token()
    raw2, _ = new_token()
    assert raw1 != raw2 and len(raw1) >= 43
    assert h1 == hash_token(raw1) and len(h1) == 64 and raw1 not in h1
