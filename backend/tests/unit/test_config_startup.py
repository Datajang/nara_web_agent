"""§9.8-9: ENV=production에서 기본·짧은 SECRET_KEY면 시작하지 않는다."""

import pytest
from pydantic import SecretStr

from app.config import DEFAULT_SECRET_KEY, ConfigError, Settings, check_startup

GOOD = SecretStr("k" * 48)


def prod(**kw):
    base = dict(
        env="production",
        secret_key=GOOD,
        app_origin="https://nara.example.com",
        mail_backend="smtp",
        smtp_host="smtp.example.com",
        mail_from="noreply@example.com",
        allowed_email_domains="corp.example",
    )
    base.update(kw)
    return Settings(**base)


def test_production_rejects_default_secret():
    with pytest.raises(ConfigError):
        check_startup(prod(secret_key=SecretStr(DEFAULT_SECRET_KEY)))


def test_production_rejects_short_secret():
    with pytest.raises(ConfigError):
        check_startup(prod(secret_key=SecretStr("short-key")))


@pytest.mark.parametrize("backend", ["memory", "console"])
def test_production_rejects_dev_mail_backends(backend):
    with pytest.raises(ConfigError):
        check_startup(prod(mail_backend=backend))


def test_production_smtp_requires_host_and_from():
    with pytest.raises(ConfigError):
        check_startup(prod(smtp_host=""))


def test_open_signup_forces_approval_and_warns():
    s = prod(allowed_email_domains="", require_admin_approval=False)
    assert s.approval_required is True
    assert any("ALLOWED_EMAIL_DOMAINS" in w for w in check_startup(s))


def test_domain_policy_defaults_to_no_approval():
    s = prod()
    assert s.approval_required is False and check_startup(s) == []


def test_development_allows_default_secret():
    assert isinstance(check_startup(Settings(env="development")), list)


def test_create_app_refuses_bad_production_config(db_url):
    from app.db.session import Database
    from tests.conftest import build_api

    with pytest.raises(ConfigError):
        build_api(Database(db_url), prod(secret_key=SecretStr(DEFAULT_SECRET_KEY)))


def test_production_rejects_fake_llm():
    with pytest.raises(ConfigError):
        check_startup(prod(llm_backend="fake"))


def test_llm_backend_selection():
    from app.llm.client import OpenAICompatLLM
    from app.llm.fake import FakeLLM
    from app.main import build_llm

    assert build_llm(Settings(llm_backend="none")) is None
    assert isinstance(build_llm(Settings(llm_backend="fake")), FakeLLM)
    real = build_llm(Settings(llm_backend="vllm", llm_model_id="q35-9b"))
    assert isinstance(real, OpenAICompatLLM) and real.model_id == "q35-9b"
