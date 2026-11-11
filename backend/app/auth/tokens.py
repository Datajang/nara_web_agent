"""토큰 (SPEC §9.3). access는 JWT, 이메일·refresh 토큰은 불투명 난수이고 DB에는 sha256만."""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta

import jwt

_ALG = "HS256"


@dataclass(frozen=True)
class AccessClaims:
    user_id: int
    role: str


def create_access_token(user_id: int, role: str, now: datetime, secret: str, minutes: int) -> str:
    exp = now + timedelta(minutes=minutes)
    claims = {
        "sub": str(user_id),
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
    }
    return jwt.encode(claims, secret, algorithm=_ALG)


def decode_access_token(token: str, secret: str, now: datetime) -> AccessClaims | None:
    """만료는 주입된 시계로 판정한다(테스트가 시간을 돌릴 수 있게)."""
    try:
        claims = jwt.decode(
            token,
            secret,
            algorithms=[_ALG],
            options={"verify_exp": False, "verify_iat": False, "require": ["sub", "exp"]},
        )
        if int(claims["exp"]) < now.timestamp():
            return None
        return AccessClaims(user_id=int(claims["sub"]), role=str(claims.get("role", "")))
    except (jwt.PyJWTError, ValueError, KeyError):
        return None


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def new_token() -> tuple[str, str]:
    """(원문, sha256 해시). 32바이트 urlsafe 난수."""
    raw = secrets.token_urlsafe(32)
    return raw, hash_token(raw)
