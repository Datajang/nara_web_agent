"""§9.6 메일 문안과 링크 형식."""

from app.auth.mail import (
    Mail,
    MemoryMailer,
    already_registered_mail,
    build_mailer,
    build_message,
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


def test_link_mails_have_clickable_html_with_same_link():
    """링크는 HTML 본문에서 눌러지는 버튼·주소로 보인다(텍스트 본문도 그대로)."""
    cases = [
        (
            verify_mail(S, "a@corp.example", "TOKEN123"),
            "/verify-email?token=TOKEN123",
            "이메일 인증하기",
        ),
        (
            reset_mail(S, "a@corp.example", "TOK"),
            "/reset-password?token=TOK",
            "새 비밀번호 설정하기",
        ),
        (already_registered_mail(S, "a@corp.example"), "/login", "로그인하러 가기"),
    ]
    for m, path, label in cases:
        link = f"https://nara.example.com{path}"
        assert m.html and m.html.count(f'href="{link}"') == 2
        assert label in m.html and link in m.body


def test_html_escapes_service_name():
    s = Settings(app_origin="https://x.example", mail_backend="memory", service_name="<b>&</b>")
    m = verify_mail(s, "a@corp.example", "T")
    assert m.html and "<b>&</b>" not in m.html and "&lt;b&gt;&amp;&lt;/b&gt;" in m.html


def test_build_message_is_multipart_alternative_only_with_html():
    s = Settings(app_origin="https://x.example", mail_backend="memory", mail_from="bot@x.example")
    rich = build_message(s, verify_mail(s, "a@corp.example", "T"))
    plain = build_message(s, Mail("a@corp.example", "제목", "본문"))
    assert rich.get_content_type() == "multipart/alternative"
    parts = [p.get_content_type() for p in rich.iter_parts()]
    assert parts == ["text/plain", "text/html"]
    assert plain.get_content_type() == "text/plain"
