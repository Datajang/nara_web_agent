"""운영자용 메일 설정 확인 명령 (docs/ops/OWNER_GUIDE.md 1단계). 배포 직후 인증 메일부터 확인."""

import aiosmtplib
import pytest

from app import cli
from app.auth.mail import MemoryMailer
from app.config import Settings

S = Settings(
    mail_backend="smtp",
    smtp_host="smtp.example.com",
    smtp_port=587,
    smtp_user="bot@example.com",
    smtp_password="secret-app-pw",
    mail_from="bot@example.com",
)


async def test_test_mail_goes_to_the_address_and_names_the_server_without_secrets():
    m = MemoryMailer()
    ok, msg = await cli.send_test_mail(S, m, "me@example.com")
    assert ok and "me@example.com" in msg
    (mail,) = m.outbox
    assert mail.to == "me@example.com" and "메일 설정 확인" in mail.subject
    assert "smtp.example.com:587" in mail.body and "bot@example.com" in mail.body
    assert "secret-app-pw" not in mail.body + msg


class _Refusing:
    async def send(self, mail):
        raise aiosmtplib.SMTPAuthenticationError(535, "5.7.8 Username and Password not accepted")


async def test_failure_says_why_and_what_to_check_without_secrets():
    ok, msg = await cli.send_test_mail(S, _Refusing(), "me@example.com")
    assert not ok
    assert "SMTPAuthenticationError" in msg and "SMTP_USER" in msg  # 다음에 볼 곳
    assert "secret-app-pw" not in msg


async def test_rejects_a_malformed_address_before_sending():
    m = MemoryMailer()
    ok, _ = await cli.send_test_mail(S, m, "not-an-address")
    assert not ok and m.outbox == []


def test_cli_exit_code_follows_the_result(monkeypatch, capsys):
    monkeypatch.setattr(cli, "get_settings", lambda: S)
    monkeypatch.setattr(cli, "build_mailer", lambda s: _Refusing())
    assert cli.main(["send-test-mail", "--to", "me@example.com"]) == 1
    assert "SMTPAuthenticationError" in capsys.readouterr().err
    box = MemoryMailer()
    monkeypatch.setattr(cli, "build_mailer", lambda s: box)
    assert cli.main(["send-test-mail", "--to", "me@example.com"]) == 0
    assert len(box.outbox) == 1


@pytest.mark.parametrize("backend", ["console", "memory"])
async def test_non_smtp_backend_is_called_out(backend):
    s = Settings(mail_backend=backend)
    ok, msg = await cli.send_test_mail(s, MemoryMailer(), "me@example.com")
    assert ok and "MAIL_BACKEND" in msg  # 실제로 나가지 않는다는 안내
