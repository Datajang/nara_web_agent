"""§9.2-1, 9.2-5: argon2id 저장, bcrypt 호환, 흔한 비밀번호 거부."""

import bcrypt
import pytest

from app.auth.passwords import (
    PasswordPolicyError,
    hash_password,
    is_common,
    validate_password,
    verify_password,
)


def test_hash_is_argon2id_and_verifies():
    h = hash_password("correct-horse-battery")
    assert h.startswith("$argon2id$")
    assert verify_password("correct-horse-battery", h) == (True, None)
    assert verify_password("wrong-password-123", h)[0] is False


def test_bcrypt_hash_verifies_and_returns_argon2_rehash():
    legacy = bcrypt.hashpw(b"legacy-password-1", bcrypt.gensalt(rounds=4)).decode()
    ok, new_hash = verify_password("legacy-password-1", legacy)
    assert ok and new_hash is not None and new_hash.startswith("$argon2id$")


def test_missing_hash_runs_dummy_verify_and_fails():
    assert verify_password("anything-at-all", None) == (False, None)


@pytest.mark.parametrize(
    ("pw", "reason"),
    [("short123", "too_short"), ("x" * 129, "too_long"), ("1234567890", "too_common")],
)
def test_policy_rejects(pw, reason):
    with pytest.raises(PasswordPolicyError) as e:
        validate_password(pw, min_length=10)
    assert e.value.reason == reason


def test_policy_accepts_without_composition_rules():
    validate_password("아주 긴 한글 비밀번호", min_length=10)
    validate_password("alllowercaseletters", min_length=10)


def test_common_list_is_case_insensitive():
    assert is_common("PASSWORD") and is_common("password")
    assert not is_common("zebra-orchard-tulip-42")
