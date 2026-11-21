"""Rotating DI_SECRET_KEY (plan 6 follow-up): the key may be a comma-separated list of Fernet keys, the first the
current one (it encrypts), the others old ones (they still decrypt); scripts/reencrypt_secrets.py re-encrypts every
stored credential with the current key, after which the old keys can go. The keys exist only in this test."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr, ValidationError
from sqlalchemy import text

from di.config import Settings
from di.connectors import secrets
from di.db import SessionLocal, engine
from tests import starting

A, B = Fernet.generate_key().decode(), Fernet.generate_key().decode()
PLAIN = "rotation-test-secret-7Q2K"


def setup_module():
    starting.reset()


def teardown_module():
    with engine.begin() as c:
        c.execute(text("DELETE FROM source_secret"))


@pytest.fixture
def key(monkeypatch):
    def use(raw: str) -> None:
        monkeypatch.setattr(secrets, "get_settings", lambda: SimpleNamespace(secret_key=SecretStr(raw)))

    return use


def test_old_keys_decrypt_and_reencrypt_moves_to_the_current_key(key):
    with SessionLocal() as s:
        s.execute(text("DELETE FROM source_secret"))
        key(A)
        secrets.put_secret(s, "erp", "auth", PLAIN, 90, "test")
        secrets.put_secret(s, "crm", "auth", PLAIN + "-crm", 90, "test")
        key(f"{B},{A}")  # B is current, A still reads
        assert secrets.active_secret(s, "erp") == PLAIN
        key(B)
        with pytest.raises(secrets.SecretUnreadable):
            secrets.active_secret(s, "erp")
        key(f"{B}, {A}")
        assert secrets.reencrypt(s) == {"reencrypted": 2, "unreadable": []}
        key(B)  # A can go
        assert secrets.active_secret(s, "erp") == PLAIN and secrets.active_secret(s, "crm") == PLAIN + "-crm"
        s.rollback()


def test_unreadable_rows_are_reported_and_left_alone(key):
    with SessionLocal() as s:
        s.execute(text("DELETE FROM source_secret"))
        key(A)
        secrets.put_secret(s, "erp", "auth", PLAIN, 90, "test")
        key(B)
        out = secrets.reencrypt(s)
        assert out["reencrypted"] == 0 and len(out["unreadable"]) == 1 and out["unreadable"][0]["source_id"] == "erp"
        key(A)
        assert secrets.active_secret(s, "erp") == PLAIN
        s.rollback()


def test_the_script_reencrypts_and_commits(key, capsys):
    path = Path(__file__).resolve().parents[1] / "scripts" / "reencrypt_secrets.py"
    spec = importlib.util.spec_from_file_location("reencrypt_secrets", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    with SessionLocal() as s:
        s.execute(text("DELETE FROM source_secret"))
        key(A)
        secrets.put_secret(s, "oms", "auth", PLAIN, 90, "test")
        s.commit()
    key(f"{B},{A}")
    assert mod.main() == 0
    printed = capsys.readouterr().out
    assert "1 re-encrypted" in printed and PLAIN not in printed and A not in printed and B not in printed
    key(B)
    with SessionLocal() as s:
        assert secrets.active_secret(s, "oms") == PLAIN


def test_settings_accept_a_key_list_outside_dev():
    strong = {"jwt_secret": "j" * 40, "webhook_secret": "w" * 40}
    assert Settings(env="prod", secret_key=f"{B},{A}", **strong).env == "prod"
    assert Settings(env="prod", secret_key=f" {B} , {A} ", **strong).env == "prod"
    with pytest.raises(ValidationError, match="urlsafe base64 of 32 bytes"):
        Settings(env="prod", secret_key=f"{B},not-a-key", **strong)
    with pytest.raises(ValidationError, match="urlsafe base64 of 32 bytes"):
        Settings(env="prod", secret_key=f"{B},", **strong)
