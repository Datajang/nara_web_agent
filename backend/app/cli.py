"""관리 CLI (SPEC §9.4).

- `python -m app.cli create-admin --email <주소>` (비밀번호는 프롬프트)
- `python -m app.cli send-test-mail --to <주소>`: 메일 설정 확인 (docs/ops/OWNER_GUIDE.md 1단계)
- `python -m app.cli team-assign --team <이름> [--owner <주소>] [--email <주소> ...]`:
  활성 계정을 팀에 배정. 팀이 없으면 --owner를 팀장으로 새로 만든다.
  하나라도 문제가 있으면 아무것도 바꾸지 않는다
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import re
import sys
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.mail import Mail, Mailer, build_mailer
from app.auth.passwords import PasswordPolicyError, hash_password, validate_password
from app.auth.service import normalize_email
from app.config import Settings, get_settings
from app.db.models.personal import Team, User
from app.db.session import Database
from app.deps import utcnow
from app.teams import service as teams


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


class TeamAssignError(Exception):
    pass


async def _check(s: AsyncSession, team: Team | None, wanted: list[str]) -> dict[str, User]:
    users = {u.email: u for u in await s.scalars(select(User).where(User.email.in_(wanted)))}
    problems = []
    for e in wanted:
        u = users.get(e)
        if u is None:
            problems.append(f"{e}: 가입한 계정이 없어요")
        elif u.status != "active":
            problems.append(f"{e}: 활성 계정이 아니에요({u.status})")
        elif u.team is not None and u.team is not team:
            problems.append(f"{e}: 이미 다른 팀 소속이에요({u.team.name})")
    if problems:
        raise TeamAssignError("아무것도 바꾸지 않았어요.\n" + "\n".join(problems))
    return users


async def assign_team(
    db: Database, team_name: str, emails: list[str], owner: str | None, now: datetime
) -> list[str]:
    """계정들을 팀에 배정한다. 검사를 모두 통과해야 바꾼다(한 트랜잭션). 결과 문구 목록을 돌려준다.

    - 이름이 같은 팀이 둘 이상이면 거부. 없으면 owner가 팀장인 새 팀(초대 코드 포함)을 만든다
    - 계정은 활성이어야 하고 다른 팀 소속이면 거부(옮기려면 그 팀에서 먼저 나가야 한다)
    - owner를 주면 그 계정이 팀장, 기존 팀장은 팀원이 된다(팀장은 한 명)
    """
    name = team_name.strip()
    owner_email = normalize_email(owner) if owner else None
    wanted = list(dict.fromkeys(normalize_email(e) for e in emails))
    if owner_email and owner_email not in wanted:
        wanted.insert(0, owner_email)
    out: list[str] = []
    async with db.transaction() as s:
        found = list(await s.scalars(select(Team).where(Team.name == name)))
        if len(found) > 1:
            raise TeamAssignError(f"이름이 '{name}'인 팀이 {len(found)}개예요. 먼저 정리해 주세요.")
        team = found[0] if found else None
        if team is None and owner_email is None:
            raise TeamAssignError(
                f"'{name}' 팀이 없어요. 새로 만들려면 --owner로 팀장을 정해 주세요."
            )
        users = await _check(s, team, wanted)
        if team is None:
            team = Team(name=name, invite_code="", created_at=now, updated_at=now)
            s.add(team)
            await teams.set_code(s, team)
            out.append(f"'{name}' 팀을 새로 만들었어요")
        for e in wanted:
            u = users[e]
            if u.team is team:
                out.append(f"{e}: 이미 '{name}' 소속이에요")
            else:
                teams.join_as(u, team, "member", now)
                out.append(f"{e}: '{name}'에 넣었어요")
        if owner_email:
            await s.flush()
            owners = await s.scalars(
                select(User).where(User.team_id == team.id, User.team_role == "owner")
            )
            for u in owners:
                if u.email != owner_email:
                    u.team_role = "member"
                    out.append(f"{u.email}: 팀장 → 팀원")
            if users[owner_email].team_role != "owner":
                users[owner_email].team_role = "owner"
                out.append(f"{owner_email}: 팀장으로 정했어요")
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("create-admin", help="첫 관리자 만들기(이미 있으면 역할만 admin으로)")
    p.add_argument("--email", required=True)
    t = sub.add_parser("send-test-mail", help="메일 설정 확인용 시험 메일 보내기")
    t.add_argument("--to", required=True)
    a = sub.add_parser("team-assign", help="활성 계정을 팀에 배정(팀이 없으면 --owner로 새로 만듦)")
    a.add_argument("--team", required=True, help="팀 이름")
    a.add_argument("--owner", help="팀장으로 정할 계정(기존 팀장은 팀원이 된다)")
    a.add_argument("--email", action="append", default=[], help="넣을 계정(여러 번 쓸 수 있다)")
    args = parser.parse_args(argv)

    settings = get_settings()
    if args.cmd == "team-assign":
        if not args.email and not args.owner:
            parser.error("--email이나 --owner를 하나 이상 주세요")

        async def assign() -> list[str]:
            db = Database(settings.database_url, pool_size=1, lock_pool_size=1)
            try:
                return await assign_team(db, args.team, args.email, args.owner, utcnow())
            finally:
                await db.dispose()

        try:
            lines = asyncio.run(assign())
        except TeamAssignError as e:
            print(e, file=sys.stderr)
            return 1
        print("\n".join(lines))
        return 0
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
