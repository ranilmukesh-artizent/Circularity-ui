"""Client credentials of an agent (plan 9, P9-13.9; F §7 "Per-agent identity").

Owns: issuing a credential (client id + a 32-byte secret shown once), storing only its scrypt hash
(`scrypt$<salt>$<hash>`, n=2**14 r=8 p=1), verifying a client_credentials request, revoking, listing (no secret, no
hash) and minting the agent's access token (`sub "agent:<id>"`, `own` the owner's account, `azp` the client id).
Never: logs or returns a stored secret, approves or confirms anything. An agent token acts as the owner's account,
prepared by the agent (di.core.auth resolves it; the action pipeline's forbidden list and autonomy still apply).
"""

import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from sqlalchemy import text
from sqlalchemy.orm import Session

from di.core import policy, state
from di.core.config import get_settings
from di.services.agents import registry

TOKEN_SECONDS = 900
PREFIX = "agent:"
_SCRYPT = {"n": 2**14, "r": 8, "p": 1}


def _scrypt(secret: str, salt: bytes) -> bytes:
    return hashlib.scrypt(secret.encode(), salt=salt, **_SCRYPT)


def hash_secret(secret: str) -> str:
    salt = secrets.token_bytes(16)
    return f"scrypt${salt.hex()}${_scrypt(secret, salt).hex()}"


def check_secret(secret: str, stored: str) -> bool:
    try:
        scheme, salt, digest = stored.split("$")
        return scheme == "scrypt" and hmac.compare_digest(_scrypt(secret, bytes.fromhex(salt)), bytes.fromhex(digest))
    except ValueError:
        return False


def issue(s: Session, agent_id: str, owner: str) -> dict[str, str]:
    """A new credential for a registered agent, owned by `owner`; the secret is returned this once."""
    client_id = "agc_" + secrets.token_hex(8)
    secret = secrets.token_urlsafe(32)
    s.execute(
        text("INSERT INTO agent_credential (client_id, agent_id, owner, secret_hash) VALUES (:c, :a, :o, :h)"),
        {"c": client_id, "a": agent_id, "o": owner, "h": hash_secret(secret)},
    )
    return {"client_id": client_id, "client_secret": secret}


def revoke(s: Session, client_id: str) -> bool:
    r = s.execute(
        text("UPDATE agent_credential SET revoked_at = now() WHERE client_id = :c AND revoked_at IS NULL"), {"c": client_id}
    )
    return bool(r.rowcount)  # type: ignore[attr-defined]


def listing(s: Session, agent_id: str) -> list[dict[str, Any]]:
    rows = s.execute(
        text(
            "SELECT client_id, owner, created_at, last_used_at, revoked_at FROM agent_credential "
            "WHERE agent_id = :a ORDER BY created_at, client_id"
        ),
        {"a": agent_id},
    ).mappings()
    return [{k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in r.items()} for r in rows]


def live(s: Session, client_id: str) -> dict[str, Any] | None:
    """The credential row if it is not revoked and its agent is enabled; else None."""
    row = (
        s.execute(
            text(
                "SELECT client_id, agent_id, owner, secret_hash FROM agent_credential WHERE client_id = :c AND revoked_at IS NULL"
            ),
            {"c": client_id},
        )
        .mappings()
        .first()
    )
    if row is None:
        return None
    agent = registry.get(s, row["agent_id"])
    if agent is None or not agent.enabled or (state.get(s, "access_settings", "agents_off") or {}).get(agent.id):
        return None
    return dict(row)


def owner_active(s: Session, owner: str, issued_at: int | None = None) -> bool:
    """The owner's account exists and was not deactivated (SCIM `account_revoked`) at or after `issued_at` (default now)."""
    from di.core import auth

    ctx = auth.load_context(s)
    if policy.account(owner, ctx) is None:
        return False
    gone = state.get(s, "account_revoked", owner) or {}
    if gone.get("active") is False:  # SCIM deactivated: refused until reactivated, however long ago
        return False
    return not auth.revoked(s, owner, issued_at if issued_at is not None else int(datetime.now(UTC).timestamp()))


def authenticate(s: Session, client_id: str, secret: str) -> dict[str, Any] | None:
    """The live credential when the secret matches and its owner is active, else None (always one scrypt run)."""
    row = live(s, client_id)
    ok = check_secret(secret, row["secret_hash"] if row else hash_secret("x"))
    if row is None or not ok or not owner_active(s, row["owner"]):
        return None
    return row


def tools_refusal(s: Session, agent_id: str, action_id: str) -> dict[str, str] | None:
    """An agent token reaches only the actions in its registry row's tools. An action no agent may run is left to the
    action pipeline, which refuses it with approval_required whatever the tools say."""
    from di.services.agents.forbidden import forbidden

    agent = registry.get(s, agent_id)
    if agent is None:
        return {"code": "out_of_scope", "message": "Unknown agent."}
    if forbidden(action_id) or action_id in agent.tools:
        return None
    return {"code": "out_of_scope", "message": f"{agent.name} cannot call {action_id}: it is not one of its tools."}


def mint(s: Session, cred: dict[str, Any]) -> dict[str, Any]:
    from di.core.auth import AUDIENCE, ISSUER

    now = datetime.now(UTC)
    claims = {
        "iss": ISSUER, "aud": AUDIENCE, "sub": PREFIX + cred["agent_id"], "own": cred["owner"], "azp": cred["client_id"],
        "exp": now + timedelta(seconds=TOKEN_SECONDS), "iat": now,
    }  # fmt: skip
    s.execute(text("UPDATE agent_credential SET last_used_at = now() WHERE client_id = :c"), {"c": cred["client_id"]})
    token = jwt.encode(claims, get_settings().jwt_secret.get_secret_value(), "HS256")
    return {"access_token": token, "token_type": "bearer", "expires_in": TOKEN_SECONDS}
