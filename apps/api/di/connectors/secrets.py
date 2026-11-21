"""Source credentials, encrypted at rest (plan 6, task A1).

    put_secret(s, "crm", "auth", value, days=180, by="developer")  → SecretMeta (a new active version)
    active_secret(s, "crm")                                         → the plain secret, for the connector only
    secret_meta(s, "crm")                                           → SecretMeta: kind, version, dates, last 4 characters
    renew(s, "crm", days=180)                                       → the active secret's term starts again

Secrets are Fernet ciphertext in `source_secret` (one row per version; one active per source and kind). The key is
DI_SECRET_KEY (urlsafe base64 of 32 bytes); in dev an empty key is derived from a fixed seed (di.config refuses that
outside dev). Rotation: DI_SECRET_KEY may list several keys, comma-separated (MultiFernet): the first encrypts, every
one decrypts; reencrypt(s) (scripts/reencrypt_secrets.py) rewrites every row with the first, then the old keys can go.
The plain value is returned only by active_secret, to the connector that signs in; it is never logged, journaled (the
pipeline drops `secret`), streamed or sent to the browser.
"""

import base64
import hashlib
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from sqlalchemy import text
from sqlalchemy.orm import Session

from di.config import DEV_SECRET_SEED, get_settings

log = logging.getLogger("di.secrets")


class SecretUnreadable(Exception):
    """The stored ciphertext does not open with the configured key (DI_SECRET_KEY changed)."""


@dataclass(frozen=True)
class SecretMeta:
    kind: str
    version: int
    issued_at: datetime
    expires_at: datetime | None
    last4: str

    def public(self) -> dict:
        return {
            "kind": self.kind,
            "version": self.version,
            "issued_at": self.issued_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "last4": self.last4,
        }


def keys_of(raw: str) -> list[str]:
    """DI_SECRET_KEY's keys: comma-separated, the first the current one (it encrypts), the others old ones."""
    return [k.strip() for k in raw.split(",") if k.strip()]


@lru_cache
def _fernet(raw: str) -> MultiFernet:
    if keys := keys_of(raw):
        return MultiFernet([Fernet(k.encode()) for k in keys])
    log.warning("DI_SECRET_KEY is not set: source credentials use the development key")
    return MultiFernet([Fernet(base64.urlsafe_b64encode(hashlib.sha256(DEV_SECRET_SEED.encode()).digest()))])


def _f() -> MultiFernet:
    return _fernet(get_settings().secret_key.get_secret_value())


def encrypt(value: str) -> bytes:
    return _f().encrypt(value.encode())


def decrypt(token: bytes) -> str:
    try:
        return _f().decrypt(bytes(token)).decode()
    except InvalidToken as e:
        raise SecretUnreadable("The stored credential cannot be read with the configured DI_SECRET_KEY.") from e


def reencrypt(s: Session) -> dict:
    """Re-encrypt every stored credential (every version, active or not) with the current key, in the caller's
    transaction (scripts/reencrypt_secrets.py commits). A row no configured key opens is left as it is and reported
    by source, kind and version. Returns {"reencrypted": n, "unreadable": [{source_id, kind, version}]}."""
    f = _f()
    done, bad = 0, []
    rows = s.execute(
        text("SELECT source_id, kind, version, ciphertext FROM source_secret ORDER BY source_id, kind, version FOR UPDATE")
    ).all()
    for r in rows:
        key = {"s": r.source_id, "k": r.kind, "v": r.version}
        try:
            token = f.rotate(bytes(r.ciphertext))
        except InvalidToken:
            bad.append({"source_id": r.source_id, "kind": r.kind, "version": r.version})
            continue
        s.execute(text("UPDATE source_secret SET ciphertext = :c WHERE source_id = :s AND kind = :k AND version = :v"),
                  key | {"c": token})  # fmt: skip
        done += 1
    return {"reencrypted": done, "unreadable": bad}


def _meta(row) -> SecretMeta:
    return SecretMeta(row.kind, row.version, row.issued_at, row.expires_at, row.last4)


def put_secret(
    s: Session, source_id: str, kind: str, value: str, days: int | None, by: str, now: datetime | None = None
) -> SecretMeta:
    """Store a new version and make it the active one; earlier versions stay, inactive (revoked)."""
    if not value:
        raise ValueError("empty secret")
    now = now or datetime.now(UTC)
    s.execute(
        text("UPDATE source_secret SET active = false WHERE source_id = :s AND kind = :k AND active"),
        {"s": source_id, "k": kind},
    )
    row = s.execute(
        text(
            "INSERT INTO source_secret (source_id, kind, version, ciphertext, last4, issued_at, expires_at, active, created_by) "
            "SELECT :s, :k, COALESCE(MAX(version), 0) + 1, :c, :l, :at, :exp, true, :by "
            "FROM source_secret WHERE source_id = :s AND kind = :k "
            "RETURNING kind, version, issued_at, expires_at, last4"
        ),
        {
            "s": source_id,
            "k": kind,
            "c": encrypt(value),
            "l": value[-4:],
            "at": now,
            "exp": now + timedelta(days=days) if days else None,
            "by": by,
        },
    ).one()
    return _meta(row)


def active_secret(s: Session, source_id: str, kind: str = "auth") -> str | None:
    token = s.execute(
        text("SELECT ciphertext FROM source_secret WHERE source_id = :s AND kind = :k AND active"),
        {"s": source_id, "k": kind},
    ).scalar()
    return None if token is None else decrypt(token)


def secret_meta(s: Session, source_id: str, kind: str = "auth") -> SecretMeta | None:
    row = s.execute(
        text(
            "SELECT kind, version, issued_at, expires_at, last4 FROM source_secret "
            "WHERE source_id = :s AND kind = :k AND active"
        ),
        {"s": source_id, "k": kind},
    ).first()
    return None if row is None else _meta(row)


def renew(s: Session, source_id: str, days: int, kind: str = "auth", now: datetime | None = None) -> SecretMeta | None:
    """Re-authentication without a new secret (OAuth consent): the active secret's term starts again."""
    now = now or datetime.now(UTC)
    row = s.execute(
        text(
            "UPDATE source_secret SET issued_at = :at, expires_at = :exp WHERE source_id = :s AND kind = :k AND active "
            "RETURNING kind, version, issued_at, expires_at, last4"
        ),
        {"s": source_id, "k": kind, "at": now, "exp": now + timedelta(days=days)},
    ).first()
    return None if row is None else _meta(row)
