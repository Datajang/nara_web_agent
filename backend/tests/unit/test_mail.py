"""§9.6 메일 문안과 링크 형식."""

from app.auth.mail import (
    MemoryMailer,
    already_registered_mail,
    build_mailer,
    reset_mail,
    verify_mail,
)
from app.config import Settings

S = Settings(app_origin="https://nara.example.com", mail_backend="memory")


def test_verify_mail_has_subject_and_link():
    m = verify_mail(S, "a@corp.example", "TOKEN123")
    assert m.to == "a@corp.example"
    assert m.subject == "[나라장터 도우미] 이메일 인증"
    assert "https://nara.example.com/verify-email?token=TOKEN123" in m.body
    assert "24시간" in m.body


def test_reset_mail_has_subject_and_link():
    m = reset_mail(S, "a@corp.example", "TOK")
    assert m.subject == "[나라장터 도우미] 비밀번호 재설정"
    assert "https://nara.example.com/reset-password?token=TOK" in m.body
    assert "1시간" in m.body


def test_already_registered_mail_has_no_token():
    m = already_registered_mail(S, "a@corp.example")
    assert m.subject == "[나라장터 도우미] 이미 가입된 계정입니다"
    assert "token=" not in m.body


def test_build_mailer_memory():
    assert isinstance(build_mailer(S), MemoryMailer)
