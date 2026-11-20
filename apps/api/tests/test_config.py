"""D2: settings refuse the shipped signing secrets outside development, and keep secrets out of reprs and logs."""

import pytest
from pydantic import SecretStr, ValidationError

from di.config import DEV_JWT_SECRET, DEV_WEBHOOK_SECRET, Settings

STRONG = {"jwt_secret": "j" * 32, "webhook_secret": "w" * 40}


def settings(**kw) -> Settings:
    return Settings(_env_file=None, **kw)


def test_dev_keeps_the_dev_defaults():
    s = settings(env="dev", jwt_secret=DEV_JWT_SECRET, webhook_secret=DEV_WEBHOOK_SECRET)
    assert isinstance(s.jwt_secret, SecretStr) and isinstance(s.webhook_secret, SecretStr)
    assert s.jwt_secret.get_secret_value() == DEV_JWT_SECRET
    assert DEV_JWT_SECRET not in repr(s) and DEV_WEBHOOK_SECRET not in repr(s)


def test_empty_secrets_mean_the_dev_defaults():
    s = settings(env="dev", jwt_secret="", webhook_secret="")
    assert s.jwt_secret.get_secret_value() == DEV_JWT_SECRET
    assert s.webhook_secret.get_secret_value() == DEV_WEBHOOK_SECRET


@pytest.mark.parametrize("env", ["test", "prod"])
@pytest.mark.parametrize(
    "secrets",
    [
        {"jwt_secret": DEV_JWT_SECRET, "webhook_secret": STRONG["webhook_secret"]},
        {"jwt_secret": STRONG["jwt_secret"], "webhook_secret": DEV_WEBHOOK_SECRET},
        {"jwt_secret": "", "webhook_secret": STRONG["webhook_secret"]},
        {"jwt_secret": "short-secret", "webhook_secret": STRONG["webhook_secret"]},
        {"jwt_secret": STRONG["jwt_secret"], "webhook_secret": "x" * 31},
    ],
)
def test_outside_dev_the_default_or_a_short_secret_is_refused(env, secrets):
    with pytest.raises(ValidationError) as e:
        settings(env=env, **secrets)
    assert "_SECRET" in str(e.value)
    for v in secrets.values():  # the refusal does not echo the secret
        if len(v) > 8:
            assert v not in str(e.value)


def test_outside_dev_strong_secrets_are_accepted():
    s = settings(env="prod", **STRONG)
    assert s.env == "prod" and s.jwt_secret.get_secret_value() == STRONG["jwt_secret"]


def test_choices_are_checked():
    with pytest.raises(ValidationError):
        settings(env="staging")
    with pytest.raises(ValidationError):
        settings(clock="wall")
    with pytest.raises(ValidationError):
        Settings(_env_file=None, ASK_PROVIDER="openai")
    assert settings(clock="sim").clock == "sim"
    assert Settings(_env_file=None, ASK_PROVIDER="none").ask_provider == "none"
