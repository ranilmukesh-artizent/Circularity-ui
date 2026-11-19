"""Deliver outbox events as CloudEvents webhooks (docs/BACKEND_STEPS.md, B6), the way SAP Event Mesh, Salesforce
platform events or ServiceNow outbound REST would notify di.

- Subscribe: POST /_sim/webhooks {"url": ..., "sources": ["erp","eam"] or [] for all, "secret": "..."}
- Each event in sim.outbox goes to every matching subscription as a structured CloudEvent (JSON, specversion 1.0),
  signed with `X-Sim-Signature: sha256=<HMAC of the body with the subscription secret>`.
- A delivery is retried with exponential backoff (2 s, 4 s … capped at 5 min) until the receiver answers 2xx,
  up to 12 attempts; then it is marked failed. An event is `delivered_at` once every subscription has it.
"""

import hashlib
import hmac
import json
import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import BigInteger, Column, DateTime, Integer, MetaData, String, Table, and_, insert, select, text, update
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.engine import Connection

from sim.db import engine
from sim.events import OUTBOX

log = logging.getLogger("sim.webhooks")
MAX_ATTEMPTS = 12

metadata = MetaData(schema="sim")
SUBSCRIPTIONS = Table(
    "subscriptions",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("url", String(500), nullable=False),
    Column("sources", ARRAY(String(40)), nullable=False),  # empty = every system
    Column("secret", String(200), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)
DELIVERIES = Table(
    "deliveries",
    metadata,
    Column("outbox_id", BigInteger, primary_key=True),
    Column("subscription_id", Integer, primary_key=True),
    Column("status", String(12), nullable=False),  # pending, delivered, failed
    Column("attempts", Integer, nullable=False, server_default="0"),
    Column("next_at", DateTime(timezone=True), nullable=False),
    Column("last_error", String(500)),
)

Post = Callable[[str, bytes, dict], int]  # (url, body, headers) -> status code


def create(conn: Connection) -> None:
    conn.execute(text("CREATE SCHEMA IF NOT EXISTS sim"))
    metadata.create_all(conn)


def subscribe(conn: Connection, url: str, sources: list[str], secret: str) -> int:
    return conn.execute(
        insert(SUBSCRIPTIONS)
        .values(url=url, sources=sources, secret=secret, created_at=datetime.now(UTC))
        .returning(SUBSCRIPTIONS.c.id)
    ).scalar_one()


def unsubscribe(conn: Connection, sub_id: int) -> bool:
    conn.execute(text("DELETE FROM sim.deliveries WHERE subscription_id = :i"), {"i": sub_id})
    return conn.execute(text("DELETE FROM sim.subscriptions WHERE id = :i"), {"i": sub_id}).rowcount > 0


def subscriptions(conn: Connection) -> list[dict]:
    return [
        {"id": r.id, "url": r.url, "sources": r.sources} for r in conn.execute(select(SUBSCRIPTIONS).order_by(SUBSCRIPTIONS.c.id))
    ]


def cloudevent(row) -> dict:
    return {
        "specversion": "1.0",
        "id": str(row.id),
        "source": f"/source-sim/{row.source}",
        "type": row.type,
        "subject": row.subject,
        "time": row.time.astimezone(UTC).isoformat().replace("+00:00", "Z"),
        "datacontenttype": "application/json",
        "data": row.data,
    }


def sign(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def _http_post(url: str, body: bytes, headers: dict) -> int:
    return httpx.post(url, content=body, headers=headers, timeout=5).status_code


def _fan_out(conn: Connection) -> None:
    """Create a pending delivery for every (undelivered event, matching subscription) pair that has none."""
    subs = conn.execute(select(SUBSCRIPTIONS)).all()
    if not subs:
        return
    rows = conn.execute(
        select(OUTBOX.c.id, OUTBOX.c.source).where(OUTBOX.c.delivered_at.is_(None)).order_by(OUTBOX.c.id).limit(500)
    ).all()
    now = datetime.now(UTC)
    for ev in rows:
        for s in subs:
            if s.sources and ev.source not in s.sources:
                continue
            conn.execute(
                text(
                    "INSERT INTO sim.deliveries (outbox_id, subscription_id, status, attempts, next_at) "
                    "VALUES (:o, :s, 'pending', 0, :n) ON CONFLICT DO NOTHING"
                ),
                {"o": ev.id, "s": s.id, "n": now},
            )


def deliver(post: Post = _http_post, limit: int = 100) -> int:
    """One delivery pass. Returns how many deliveries were attempted."""
    with engine.begin() as conn:
        _fan_out(conn)
    attempted = 0
    with engine.begin() as conn:
        due = conn.execute(
            select(DELIVERIES, SUBSCRIPTIONS.c.url, SUBSCRIPTIONS.c.secret)
            .join(SUBSCRIPTIONS, SUBSCRIPTIONS.c.id == DELIVERIES.c.subscription_id)
            .where(DELIVERIES.c.status == "pending", DELIVERIES.c.next_at <= datetime.now(UTC))
            .order_by(DELIVERIES.c.outbox_id)
            .limit(limit)
            .with_for_update(of=DELIVERIES, skip_locked=True)
        ).all()
        for d in due:
            ev = conn.execute(select(OUTBOX).where(OUTBOX.c.id == d.outbox_id)).one()
            body = json.dumps(cloudevent(ev), separators=(",", ":")).encode()
            headers = {"content-type": "application/cloudevents+json", "x-sim-signature": sign(d.secret, body)}
            attempted += 1
            try:
                status = post(d.url, body, headers)
                error = None if 200 <= status < 300 else f"HTTP {status}"
            except Exception as e:  # noqa: BLE001 - recorded and retried
                error = f"{type(e).__name__}: {e}"[:500]
            key = and_(DELIVERIES.c.outbox_id == d.outbox_id, DELIVERIES.c.subscription_id == d.subscription_id)
            if error is None:
                conn.execute(update(DELIVERIES).where(key).values(status="delivered", attempts=d.attempts + 1, last_error=None))
            else:
                n = d.attempts + 1
                conn.execute(
                    update(DELIVERIES)
                    .where(key)
                    .values(
                        status="failed" if n >= MAX_ATTEMPTS else "pending",
                        attempts=n,
                        last_error=error,
                        next_at=datetime.now(UTC) + timedelta(seconds=min(300, 2**n)),
                    )
                )
        # an event is delivered when no subscription is still pending for it
        conn.execute(
            text(
                "UPDATE sim.outbox o SET delivered_at = now() WHERE o.delivered_at IS NULL "
                "AND EXISTS (SELECT 1 FROM sim.deliveries d WHERE d.outbox_id = o.id) "
                "AND NOT EXISTS (SELECT 1 FROM sim.deliveries d WHERE d.outbox_id = o.id AND d.status = 'pending')"
            )
        )
    return attempted


def status(conn: Connection) -> dict:
    counts = dict(conn.execute(text("SELECT status, count(*) FROM sim.deliveries GROUP BY status")).all())
    undelivered = conn.execute(text("SELECT count(*) FROM sim.outbox WHERE delivered_at IS NULL")).scalar_one()
    return {"deliveries": counts, "undelivered_events": undelivered}
