"""관리 CLI (SPEC §9.4). `python -m app.cli create-admin --email <주소>` (비밀번호는 프롬프트)."""

from __future__ import annotations

import argparse
import asyncio
import getpass
import sys

from sqlalchemy import select

from app.auth.passwords import PasswordPolicyError, hash_password, validate_password
from app.auth.service import normalize_email
from app.config import get_settings
from app.db.models.personal import User
from app.db.session import Database
from app.deps import utcnow


async def create_admin(db: Database, email: str, password: str) -> str:
    """새로 만들면 "created", 이미 있으면 역할만 올리고 "promoted"."""
    email = normalize_email(email)
    async with db.transaction() as s:
        user = await s.scalar(select(User).where(User.email == email))
        if user is not None:
            user.role = "admin"
            return "promoted"
        validate_password(password, get_settings().password_min_length)
        s.add(
            User(
                email=email,
                password_hash=hash_password(password),
                display_name=email.split("@")[0],
                role="admin",
                status="active",
                email_verified_at=utcnow(),
            )
        )
    return "created"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("create-admin", help="첫 관리자 만들기(이미 있으면 역할만 admin으로)")
    p.add_argument("--email", required=True)
    args = parser.parse_args(argv)

    settings = get_settings()
    password = getpass.getpass("비밀번호: ")
    if getpass.getpass("비밀번호 확인: ") != password:
        print("비밀번호가 서로 달라요.", file=sys.stderr)
        return 2

    async def run() -> str:
        db = Database(settings.database_url, pool_size=1, lock_pool_size=1)
        try:
            return await create_admin(db, args.email, password)
        finally:
            await db.dispose()

    try:
        result = asyncio.run(run())
    except PasswordPolicyError as e:
        print(f"비밀번호 조건에 맞지 않아요: {e.reason}", file=sys.stderr)
        return 2
    print({"created": "관리자를 만들었어요.", "promoted": "기존 계정을 관리자로 올렸어요."}[result])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
