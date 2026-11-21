"""Where a source's connector connects, and how it signs in (plan 6, task A2).

    connection_for(s, "erp")           → Connection(base_url, protocol, auth_kind, auth_params, paging, resources)
    save_connection(s, "erp", by="Developer", base_url="https://...")      → the row, written
    client_for(s, "erp", adapter, run_id)                                    → a SourceClient on that URL, signed in
    check_credential(s, "erp", now)                                          → raises SourceError when it has expired

One `source_connection` row per source. The 21 demo sources get a seeded row (`updated_by` NULL) whose URL is
settings.source_sim_url + the adapter's base_path, so they read source-sim exactly as before; a person can point one
elsewhere (source.update), and the next sync calls that URL. A source without a Python adapter is read by the configured
adapter (di.connectors.configured) from its row's paging and resources.

The secret is never in this table: it is in source_secret (di.connectors.secrets). A Python adapter signs in with
`adapter.auth(conn, secret)`: the stored secret when one was saved or rotated, else its built-in demo credential (the
synthetic credential source-sim's mock accepts, documented in apps/README.md). So the demo sources behave as before
until a person stores a credential, and a wrong stored secret is refused by the system like any wrong credential.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

from sqlalchemy import text
from sqlalchemy.orm import Session

from di.config import get_settings
from di.connectors import secrets
from di.connectors.http import SourceClient, SourceError

if TYPE_CHECKING:
    from di.connectors.base import Adapter

AUTH_KINDS = ("builtin", "none", "api_key", "bearer", "basic", "oauth_cc")


@dataclass(frozen=True)
class Connection:
    source_id: str
    base_url: str
    protocol: str = "rest"
    auth_kind: str = "builtin"  # builtin: the Python adapter's own scheme
    auth_params: dict[str, Any] = field(default_factory=dict)
    paging: dict[str, Any] = field(default_factory=dict)
    resources: list[dict[str, Any]] = field(default_factory=list)
    updated_by: str | None = None
    updated_at: datetime | None = None

    @property
    def origin(self) -> str:
        """scheme://host[:port] of the base URL: where a system's token endpoint outside the base path lives."""
        u = urlparse(self.base_url)
        return f"{u.scheme}://{u.netloc}"

    @property
    def host(self) -> str:
        return urlparse(self.base_url).hostname or ""

    @property
    def simulated(self) -> bool:
        """The URL is source-sim's (the dev stand-in for every system)."""
        return self.base_url.startswith(get_settings().source_sim_url.rstrip("/"))

    def public(self) -> dict[str, Any]:
        return {
            "base_url": self.base_url,
            "protocol": self.protocol,
            "auth_kind": self.auth_kind,
            "auth_params": self.auth_params,
            "resources": self.resources,
            "paging": self.paging,
        }


def sim_url(path: str = "") -> str:
    return get_settings().source_sim_url.rstrip("/") + path


def default_for(adapter: "Adapter") -> Connection:
    """The seeded connection of a demo source: source-sim's mock of its system."""
    return Connection(adapter.source_id, sim_url(adapter.base_path), getattr(adapter, "protocol", "rest"))


def _row(r) -> Connection:
    return Connection(
        r.source_id, r.base_url, r.protocol, r.auth_kind, dict(r.auth_params or {}), dict(r.paging or {}),
        list(r.resources or []), r.updated_by, r.updated_at,
    )  # fmt: skip


def connection_for(s: Session, source_id: str) -> Connection | None:
    """The source's stored connection; for a demo source without a row, its default; else None."""
    r = s.execute(text("SELECT * FROM source_connection WHERE source_id = :i"), {"i": source_id}).first()
    if r is not None:
        return _row(r)
    from di.connectors.registry import ADAPTERS

    a = ADAPTERS.get(source_id)
    return default_for(a) if a is not None else None


def save_connection(s: Session, source_id: str, by: str | None, **fields: Any) -> Connection:
    """Create or change the source's row. Fields not given keep their value (or the default for a new row)."""
    import json

    if "auth_kind" in fields and fields["auth_kind"] not in AUTH_KINDS:
        raise ValueError(f"unknown auth kind {fields['auth_kind']}")
    cur = connection_for(s, source_id)
    base = cur.public() if cur else {"base_url": "", "protocol": "rest", "auth_kind": "builtin", "auth_params": {},
                                     "resources": [], "paging": {}}  # fmt: skip
    v = base | {k: x for k, x in fields.items() if k in base and x is not None}
    if not v["base_url"]:
        raise ValueError("a connection needs a base URL")
    s.execute(
        text(
            "INSERT INTO source_connection (source_id, base_url, protocol, auth_kind, auth_params, paging, resources, "
            "updated_by, updated_at) VALUES (:i, :u, :p, :k, CAST(:ap AS jsonb), CAST(:pg AS jsonb), CAST(:rs AS jsonb), "
            ":by, now()) ON CONFLICT (source_id) DO UPDATE SET base_url = EXCLUDED.base_url, protocol = EXCLUDED.protocol, "
            "auth_kind = EXCLUDED.auth_kind, auth_params = EXCLUDED.auth_params, paging = EXCLUDED.paging, "
            "resources = EXCLUDED.resources, updated_by = EXCLUDED.updated_by, updated_at = now()"
        ),
        {"i": source_id, "u": v["base_url"], "p": v["protocol"], "k": v["auth_kind"], "ap": json.dumps(v["auth_params"]),
         "pg": json.dumps(v["paging"]), "rs": json.dumps(v["resources"]), "by": by},
    )  # fmt: skip
    out = connection_for(s, source_id)
    assert out is not None  # noqa: S101 - just written
    return out


def restore_default(s: Session, source_id: str) -> Connection | None:
    """A demo source back on its seeded connection (source-sim). None for a source without a Python adapter."""
    from di.connectors.registry import ADAPTERS

    a = ADAPTERS.get(source_id)
    if a is None:
        return None
    s.execute(text("DELETE FROM source_connection WHERE source_id = :i"), {"i": source_id})
    _seed(s, [a])
    return connection_for(s, source_id)


def _seed(s, adapters: list) -> None:
    for a in adapters:
        d = default_for(a)
        s.execute(
            text(
                "INSERT INTO source_connection (source_id, base_url, protocol) VALUES (:i, :u, :p) "
                "ON CONFLICT (source_id) DO UPDATE SET base_url = EXCLUDED.base_url, updated_at = now() "
                "WHERE source_connection.updated_by IS NULL AND source_connection.base_url <> EXCLUDED.base_url"
            ),
            {"i": d.source_id, "u": d.base_url, "p": d.protocol},
        )


def seed_demo(s) -> None:
    """The demo sources' default rows (start-up, demo reset). A row a person changed is kept; a seeded row follows
    DI_SOURCE_SIM_URL. Takes a Session or a Connection."""
    from di.connectors.registry import ADAPTERS

    _seed(s, list(ADAPTERS.values()))


def reset_demo(conn, keep: list[str]) -> None:
    """The demo reset: every source's row goes, then the demo sources (`keep`) get their seeded row again."""
    from di.connectors.registry import ADAPTERS

    conn.execute(text("DELETE FROM source_connection"))
    _seed(conn, [a for sid, a in ADAPTERS.items() if sid in keep])


# ---------------------------------------------------------------- signing in
def check_credential(s: Session, source_id: str, now: datetime | None = None) -> None:
    """A stored credential past its expiry is not used: the sync fails with auth_expired before any call. Expiry is on
    the workspace clock (di.clock), the clock its issue time was stamped with."""
    from di import clock

    meta = secrets.secret_meta(s, source_id)
    now = now or clock.now()
    if meta is not None and meta.expires_at is not None and meta.expires_at <= now:
        raise SourceError("auth", f"Credential expired on {meta.expires_at.date().isoformat()}")


def client_for(s: Session, source_id: str, adapter: "Adapter", run_id: int | None = None, timeout: float = 20) -> SourceClient:
    """A SourceClient on the source's URL, signed in with its stored secret (or the adapter's demo credential)."""
    conn = connection_for(s, source_id) or default_for(adapter)
    secret = secrets.active_secret(s, source_id)
    return SourceClient(source_id, conn.base_url, adapter.auth(conn, secret), s, run_id, timeout=timeout)
