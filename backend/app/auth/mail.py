"""메일 (SPEC §9.2-8, §9.6). 백엔드: memory(테스트·개발), console(개발), smtp(운영)."""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass, field
from email.message import EmailMessage
from typing import Protocol

import aiosmtplib

from app.config import Settings


@dataclass(frozen=True)
class Mail:
    to: str
    subject: str
    body: str


class Mailer(Protocol):
    async def send(self, mail: Mail) -> None: ...


@dataclass
class MemoryMailer:
    outbox: list[Mail] = field(default_factory=list)

    async def send(self, mail: Mail) -> None:
        self.outbox.append(mail)


log = logging.getLogger(__name__)


class ConsoleMailer:
    """개발용: 링크를 표준출력에 찍는다. 로그(logging)를 거치지 않아 마스킹 대상이 아니다.
    운영(ENV=production)에서는 시작 검사가 막는다."""

    async def send(self, mail: Mail) -> None:
        print(f"\n[메일] To: {mail.to}\n제목: {mail.subject}\n{mail.body}\n", file=sys.stdout)


class SmtpMailer:
    def __init__(self, settings: Settings) -> None:
        self.s = settings

    async def send(self, mail: Mail) -> None:
        msg = EmailMessage()
        msg["From"], msg["To"], msg["Subject"] = self.s.mail_from, mail.to, mail.subject
        msg.set_content(mail.body)
        await aiosmtplib.send(
            msg,
            hostname=self.s.smtp_host,
            port=self.s.smtp_port,
            username=self.s.smtp_user or None,
            password=self.s.smtp_password.get_secret_value() or None,
            start_tls=self.s.smtp_port == 587,
            use_tls=self.s.smtp_port == 465,
            timeout=15,
        )
        log.info("mail sent subject_len=%d", len(mail.subject))


def _subject(settings: Settings, text: str) -> str:
    return f"[{settings.service_name}] {text}"


def verify_mail(settings: Settings, to: str, token: str) -> Mail:
    link = f"{settings.app_origin}/verify-email?token={token}"
    hours = settings.verify_token_hours
    body = (
        f"가입을 완료하려면 {hours}시간 안에 아래 링크를 눌러 주세요.\n\n{link}\n\n"
        "본인이 가입하지 않았다면 이 메일을 무시해 주세요."
    )
    return Mail(to, _subject(settings, "이메일 인증"), body)


def reset_mail(settings: Settings, to: str, token: str) -> Mail:
    link = f"{settings.app_origin}/reset-password?token={token}"
    hours = max(1, settings.reset_token_minutes // 60)
    body = (
        f"{hours}시간 안에 아래 링크에서 새 비밀번호를 설정해 주세요.\n\n{link}\n\n"
        "요청하지 않았다면 무시해도 됩니다."
    )
    return Mail(to, _subject(settings, "비밀번호 재설정"), body)


def already_registered_mail(settings: Settings, to: str) -> Mail:
    body = (
        "이 주소로 이미 가입된 계정이 있어요. 비밀번호를 잊었다면 로그인 화면의 "
        f"'비밀번호 재설정'을 이용해 주세요.\n\n{settings.app_origin}/login"
    )
    return Mail(to, _subject(settings, "이미 가입된 계정입니다"), body)


def build_mailer(settings: Settings) -> Mailer:
    if settings.mail_backend == "memory":
        return MemoryMailer()
    if settings.mail_backend == "smtp":
        return SmtpMailer(settings)
    return ConsoleMailer()
