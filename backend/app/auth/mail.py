"""메일 (SPEC §9.2-8, §9.6). 백엔드: memory(테스트·개발), console(개발), smtp(운영).

링크가 있는 메일은 텍스트 본문과 HTML 본문(눌러지는 버튼·링크)을 함께 보낸다(multipart/alternative).
"""

from __future__ import annotations

import html as _html
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
    body: str  # 텍스트 본문(HTML을 못 보는 메일 앱용, 항상 있음)
    html: str | None = None


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


def build_message(settings: Settings, mail: Mail) -> EmailMessage:
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = settings.mail_from, mail.to, mail.subject
    msg.set_content(mail.body)
    if mail.html:
        msg.add_alternative(mail.html, subtype="html")
    return msg


class SmtpMailer:
    def __init__(self, settings: Settings) -> None:
        self.s = settings

    async def send(self, mail: Mail) -> None:
        msg = build_message(self.s, mail)
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


def _html_body(settings: Settings, before: str, link: str, label: str, after: str) -> str:
    """버튼 하나와, 버튼이 안 눌릴 때 쓸 주소 링크. 메일 앱 호환을 위해 인라인 스타일만."""
    e = _html.escape
    href = e(link, quote=True)
    p = 'style="margin:0 0 16px;font-size:15px;line-height:1.6;color:#1f2937"'
    small = 'style="margin:0 0 8px;font-size:13px;line-height:1.6;color:#6b7280"'
    button = (
        'style="display:inline-block;padding:12px 20px;border-radius:6px;background:#2563eb;'
        'color:#ffffff;font-size:15px;font-weight:600;text-decoration:none"'
    )
    return (
        '<!doctype html><html lang="ko"><body style="margin:0;padding:24px;background:#f3f4f6">'
        '<div style="max-width:520px;margin:0 auto;padding:24px;background:#ffffff;'
        'border-radius:8px;font-family:sans-serif">'
        f'<p style="margin:0 0 16px;font-size:13px;color:#6b7280">{e(settings.service_name)}</p>'
        f"<p {p}>{e(before)}</p>"
        f'<p style="margin:0 0 24px"><a href="{href}" {button}>{e(label)}</a></p>'
        f"<p {small}>버튼이 눌리지 않으면 아래 주소를 눌러 주세요.</p>"
        f'<p {small}><a href="{href}" style="color:#2563eb;word-break:break-all">{e(link)}</a></p>'
        f'<p style="margin:16px 0 0;font-size:13px;color:#6b7280">{e(after)}</p>'
        "</div></body></html>"
    )


def verify_mail(settings: Settings, to: str, token: str) -> Mail:
    link = f"{settings.app_origin}/verify-email?token={token}"
    hours = settings.verify_token_hours
    before = f"가입을 완료하려면 {hours}시간 안에 아래 링크를 눌러 주세요."
    after = "본인이 가입하지 않았다면 이 메일을 무시해 주세요."
    body = f"{before}\n\n{link}\n\n{after}"
    html = _html_body(settings, before, link, "이메일 인증하기", after)
    return Mail(to, _subject(settings, "이메일 인증"), body, html)


def reset_mail(settings: Settings, to: str, token: str) -> Mail:
    link = f"{settings.app_origin}/reset-password?token={token}"
    hours = max(1, settings.reset_token_minutes // 60)
    before = f"{hours}시간 안에 아래 링크에서 새 비밀번호를 설정해 주세요."
    after = "요청하지 않았다면 무시해도 됩니다."
    body = f"{before}\n\n{link}\n\n{after}"
    html = _html_body(settings, before, link, "새 비밀번호 설정하기", after)
    return Mail(to, _subject(settings, "비밀번호 재설정"), body, html)


def already_registered_mail(settings: Settings, to: str) -> Mail:
    before = (
        "이 주소로 이미 가입된 계정이 있어요. 비밀번호를 잊었다면 로그인 화면의 "
        "'비밀번호 재설정'을 이용해 주세요."
    )
    link = f"{settings.app_origin}/login"
    after = "본인이 가입을 시도하지 않았다면 이 메일을 무시해 주세요."
    body = f"{before}\n\n{link}"
    html = _html_body(settings, before, link, "로그인하러 가기", after)
    return Mail(to, _subject(settings, "이미 가입된 계정입니다"), body, html)


def build_mailer(settings: Settings) -> Mailer:
    if settings.mail_backend == "memory":
        return MemoryMailer()
    if settings.mail_backend == "smtp":
        return SmtpMailer(settings)
    return ConsoleMailer()
