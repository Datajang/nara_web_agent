"""비밀번호 해시와 정책 (SPEC §9.2-1, 9.2-5). argon2id 저장, v1 bcrypt는 검증 후 재해시."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher
from pwdlib.hashers.bcrypt import BcryptHasher

MAX_LENGTH = 128
# 첫 번째 해셔가 저장 형식. bcrypt는 검증만 하고 통과하면 argon2id로 다시 저장한다.
_HASHER = PasswordHash((Argon2Hasher(), BcryptHasher()))
# 이메일이 없을 때도 같은 비용의 검증을 하기 위한 더미 해시 (§9.2-4 응답 시간 차이 완화)
_DUMMY_HASH = _HASHER.hash("dummy-password-for-timing")
_COMMON_FILE = Path(__file__).parent / "data" / "common-passwords.txt"  # SecLists, MIT


class PasswordPolicyError(ValueError):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason  # too_short | too_long | too_common


@lru_cache(maxsize=1)
def _common() -> frozenset[str]:
    lines = _COMMON_FILE.read_text(encoding="utf-8").splitlines()
    return frozenset(line.strip().lower() for line in lines if line.strip())


def is_common(password: str) -> bool:
    return password.strip().lower() in _common()


def validate_password(password: str, min_length: int = 10) -> None:
    """길이와 흔한 비밀번호만 본다. 구성 규칙(대소문자·특수문자)은 요구하지 않는다."""
    if len(password) < min_length:
        raise PasswordPolicyError("too_short")
    if len(password) > MAX_LENGTH:
        raise PasswordPolicyError("too_long")
    if is_common(password):
        raise PasswordPolicyError("too_common")


def hash_password(password: str) -> str:
    return _HASHER.hash(password)


def verify_password(password: str, stored_hash: str | None) -> tuple[bool, str | None]:
    """(맞음, 새 해시). 새 해시가 있으면 저장을 바꾼다. stored_hash가 None이면 더미 검증."""
    if stored_hash is None:
        _HASHER.verify(password, _DUMMY_HASH)
        return False, None
    try:
        return _HASHER.verify_and_update(password, stored_hash)
    except Exception:  # 알 수 없는 해시 형식
        return False, None
