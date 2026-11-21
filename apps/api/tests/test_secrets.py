"""Plan 6 A1: source credentials are stored encrypted, and the plain value never leaves the connector's hands.

- put_secret / active_secret round trip; rotating adds a version and revokes the previous one; secret_meta shows only
  the last 4 characters
- credentials.rotate stores the secret it is given; re-authentication renews the active secret's term; rotating
  without a secret is refused
- the plain value is in no journal row, stream event, domain event, screen response or log line, and not in the
  stored ciphertext
- a ciphertext that does not open with the configured key raises SecretUnreadable, never garbage
- outside DI_ENV=dev, DI_SECRET_KEY is required and must be a Fernet key
"""

import json
import logging

import pytest
from cryptography.fernet import Fernet
from pydantic import ValidationError
from sqlalchemy import text

from di.config import Settings
from di.connectors import secrets
from di.db import SessionLocal, engine
from tests import starting
from tests.helpers import call, client, h

PLAIN = "rotated-Secret-4f9c-XYZW"


def setup_module():
    starting.reset()


def teardown_module():
    with engine.begin() as c:
        c.execute(text("DELETE FROM source_secret"))


def test_round_trip_and_versions():
    with SessionLocal() as s:
        m1 = secrets.put_secret(s, "erp", "auth", "first-secret-0001", 90, "test")
        m2 = secrets.put_secret(s, "erp", "auth", "second-secret-0002", 180, "test")
        assert (m1.version, m2.version) == (1, 2)
        assert secrets.active_secret(s, "erp") == "second-secret-0002"
        meta = secrets.secret_meta(s, "erp")
        assert meta.last4 == "0002" and meta.version == 2 and (meta.expires_at - meta.issued_at).days == 180
        assert set(meta.public()) == {"kind", "version", "issued_at", "expires_at", "last4"}
        rows = s.execute(text("SELECT version, active FROM source_secret WHERE source_id = 'erp' ORDER BY version")).all()
        assert [tuple(r) for r in rows] == [(1, False), (2, True)]
        assert secrets.active_secret(s, "erp", "webhook") is None and secrets.secret_meta(s, "oms") is None
        s.rollback()


def test_rotate_stores_and_reauth_renews():
    r = call("credentials.rotate", {"source_id": "crm", "days": 90, "secret": PLAIN}, "developer")
    assert r["ok"], r
    cred = r["output"]["credential"]
    assert cred["last4"] == "XYZW" and cred["version"] == 1 and cred["kind"] == "auth"
    with SessionLocal() as s:
        assert secrets.active_secret(s, "crm") == PLAIN
    r = call("credentials.rotate", {"source_id": "crm", "days": 180, "reauth": True}, "developer")
    assert r["ok"] and r["output"]["credential"]["version"] == 1, r  # same secret, a new term
    with SessionLocal() as s:
        meta = secrets.secret_meta(s, "crm")
        assert (meta.expires_at - meta.issued_at).days == 180
    no = call("credentials.rotate", {"source_id": "crm", "days": 90}, "developer")
    assert no["error"] == {"code": "validation_error", "message": "Enter the new secret."}
    src = client.get("/api/screens/integration/sources", headers=h("developer")).json()
    crm = next(x for x in src["sources"] if x["id"] == "crm")
    assert crm["credential"]["last4"] == "XYZW"


def test_secret_never_leaves(caplog):
    caplog.set_level(logging.DEBUG)
    r = call("credentials.rotate", {"source_id": "oms", "days": 90, "secret": PLAIN}, "developer")
    assert r["ok"], r
    assert PLAIN not in json.dumps(r)
    with engine.connect() as c:
        for q in (
            "SELECT input::text, coalesce(output_ref::text, '') FROM action_journal",
            "SELECT payload::text FROM stream_event",
            "SELECT payload::text FROM domain_event",
            "SELECT coalesce(url, '') || coalesce(error, '') FROM fetch_log",
        ):
            for row in c.execute(text(q)):
                assert PLAIN not in "".join(row), q
        token = c.execute(text("SELECT ciphertext FROM source_secret WHERE source_id = 'oms' AND active")).scalar_one()
    assert PLAIN.encode() not in bytes(token)
    for path in ("/api/screens/integration/sources", "/api/screens/integration/sources/oms", "/api/screens/integration/overview"):
        res = client.get(path, headers=h("developer"))
        assert PLAIN not in res.text, path
    assert PLAIN not in caplog.text


def test_wrong_key_is_unreadable():
    token = Fernet(Fernet.generate_key()).encrypt(b"made-with-another-key")
    with pytest.raises(secrets.SecretUnreadable):
        secrets.decrypt(token)


def test_key_required_outside_dev():
    strong = {"jwt_secret": "j" * 40, "webhook_secret": "w" * 40}
    with pytest.raises(ValidationError, match="DI_SECRET_KEY is required"):
        Settings(env="prod", secret_key="", **strong)
    with pytest.raises(ValidationError, match="urlsafe base64 of 32 bytes"):
        Settings(env="prod", secret_key="not-a-key", **strong)
    assert Settings(env="prod", secret_key=Fernet.generate_key().decode(), **strong).env == "prod"
