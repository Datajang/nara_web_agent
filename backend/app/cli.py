"""관리 CLI (SPEC §9.4).

- `python -m app.cli create-admin --email <주소>` (비밀번호는 프롬프트)
- `python -m app.cli send-test-mail --to <주소>`: 메일 설정 확인 (docs/ops/OWNER_GUIDE.md 1단계)
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import re
import sys

from sqlalchemy import select

from app.auth.mail import Mail, Mailer, build_mailer
from app.auth.passwords import PasswordPolicyError, hash_password, validate_password
from app.auth.service import normalize_email
from app.config import Settings, get_settings
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


_ADDRESS = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


async def send_test_mail(settings: Settings, mailer: Mailer, to: str) -> tuple[bool, str]:
    """설정된 메일 백엔드로 시험 메일 1통. 결과 문구에 비밀번호는 넣지 않는다."""
    if not _ADDRESS.match(to):
        return False, f"받는 주소 형식이 아니에요: {to}"
    server = f"{settings.smtp_host}:{settings.smtp_port}"
    body = (
        f"{settings.service_name} 메일 설정 확인용 메일입니다.\n\n"
        f"보낸 서버: {server}\n보낸 주소: {settings.mail_from}\n\n"
        "이 메일이 받은편지함에 왔다면 가입 인증·비밀번호 재설정 메일도 갑니다. "
        "스팸함에 있었다면 '스팸 아님'으로 표시해 주세요."
    )
    try:
        await mailer.send(Mail(to, f"[{settings.service_name}] 메일 설정 확인", body))
    except Exception as e:  # 원인 종류와 서버 응답만 보여 준다
        return False, (
            f"보내지 못했어요: {type(e).__name__}: {str(e)[:200]}\n"
            "확인할 곳: SMTP_HOST·SMTP_PORT(587=STARTTLS, 465=SSL)·SMTP_USER·SMTP_PASSWORD"
            "(Gmail은 앱 비밀번호)·MAIL_FROM"
        )
    if settings.mail_backend != "smtp":
        return True, (
            f"MAIL_BACKEND={settings.mail_backend}라 실제로 나가지 않았어요(개발용). "
            "운영은 MAIL_BACKEND=smtp"
        )
    return True, f"{to}로 보냈어요({server}). 받은편지함과 스팸함을 확인해 주세요."


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("create-admin", help="첫 관리자 만들기(이미 있으면 역할만 admin으로)")
    p.add_argument("--email", required=True)
    t = sub.add_parser("send-test-mail", help="메일 설정 확인용 시험 메일 보내기")
    t.add_argument("--to", required=True)
    args = parser.parse_args(argv)

    settings = get_settings()
    if args.cmd == "send-test-mail":
        ok, msg = asyncio.run(send_test_mail(settings, build_mailer(settings), args.to))
        print(msg, file=sys.stdout if ok else sys.stderr)
        return 0 if ok else 1
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
