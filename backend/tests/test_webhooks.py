"""Plan 6 A7: per-source webhook intake, POST /api/webhooks/{source_id}.

The event is a CloudEvent signed with HMAC-SHA256 over the body (`X-Signature: sha256=<hex>`; source-sim's
`X-Sim-Signature` is accepted too). The secret is the source's own (`source_secret` kind `webhook`), or the global
DI_WEBHOOK_SECRET when the source has none (the demo sources). An event seen before (same source and id) is answered
200 `{"duplicate": true}` and queues nothing; an event whose `time` is more than 300 s behind the workspace clock
(di/core/clock.py: the pinned as-of time in the suite, source-sim's simulated clock in the running stack, the clock
source-sim stamps its events with) is refused 400 `stale_event`; a wrong signature 401.
"""

import hashlib
import hmac
import json
import uuid
from datetime import timedelta

import pytest
from sqlalchemy import text

from di.connectors.secrets import put_secret
from di.connectors.sync import ensure_sources
from di.core import clock
from di.core.config import get_settings
from di.core.db import SessionLocal, engine
from tests.helpers import client

SID = "dlr"
GLOBAL = get_settings().webhook_secret.get_secret_value()


def sign(body: bytes, secret: str = GLOBAL) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def event(age_s: float = 0, **kw) -> dict:
    t = clock.now() - timedelta(seconds=age_s)
    return {
        "specversion": "1.0",
        "id": kw.pop("id", None) or f"t-{uuid.uuid4()}",
        "source": f"/vendor/{SID}",
        "type": "offer.updated",
        "time": t.isoformat().replace("+00:00", "Z"),
        **kw,
    }


def post(ev: dict, sid: str = SID, secret: str = GLOBAL, header: str = "x-signature"):
    body = json.dumps(ev).encode()
    return client.post(
        f"/api/webhooks/{sid}", content=body, headers={header: sign(body, secret), "content-type": "application/json"}
    )


def sync_jobs(sid: str = SID) -> int:
    with SessionLocal() as s:
        return s.execute(
            text("SELECT count(*) FROM job WHERE kind = 'sync.source' AND payload->>'source_id' = :s"), {"s": sid}
        ).scalar_one()


def drop_jobs() -> None:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM job WHERE kind = 'sync.source'"))


@pytest.fixture(autouse=True)
def clean():
    with SessionLocal() as s:
        ensure_sources(s)
    drop_jobs()
    yield
    drop_jobs()
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM source_secret WHERE source_id = :s AND kind = 'webhook'"), {"s": SID})
        conn.execute(text("DELETE FROM webhook_event WHERE event_id LIKE 't-%'"))


def test_an_event_queues_one_sync_and_a_replay_is_a_duplicate():
    ev = event()
    r = post(ev)
    assert r.status_code == 202, r.text
    out = r.json()
    assert out["accepted"] is True and out["source_id"] == SID and out["queued_job"]
    drop_jobs()  # the sync ran: a replay must not queue another
    again = post(ev)
    assert again.status_code == 200 and again.json()["duplicate"] is True, again.text
    assert sync_jobs() == 0
    with SessionLocal() as s:
        row = s.execute(
            text("SELECT event_type FROM webhook_event WHERE source_id = :s AND event_id = :e"), {"s": SID, "e": ev["id"]}
        ).one()
    assert row.event_type == "offer.updated"


def test_source_sims_signature_header_is_accepted():
    assert post(event(), header="x-sim-signature").status_code == 202


def test_an_event_ten_minutes_old_is_refused_as_stale():
    r = post(event(age_s=600))
    assert r.status_code == 400 and r.json()["error"]["code"] == "stale_event", r.text
    assert post(event(age_s=290)).status_code == 202  # inside the 300 s window
    assert sync_jobs() == 1


def test_a_refused_stale_event_is_not_remembered():
    ev = event(age_s=600)
    assert post(ev).status_code == 400
    with SessionLocal() as s:
        assert s.execute(text("SELECT count(*) FROM webhook_event WHERE event_id = :e"), {"e": ev["id"]}).scalar_one() == 0


def test_a_wrong_signature_is_refused():
    ev = event()
    r = post(ev, secret="not-the-secret")
    assert r.status_code == 401 and r.json()["error"]["code"] == "bad_signature"
    body = json.dumps(ev).encode()
    no_sig = client.post(f"/api/webhooks/{SID}", content=body)
    assert no_sig.status_code == 401 and sync_jobs() == 0


def test_a_source_with_its_own_webhook_secret_uses_only_that_one():
    with SessionLocal() as s:
        put_secret(s, SID, "webhook", "whsec-test-0123456789", None, "test")
        s.commit()
    assert post(event()).status_code == 401  # the global secret no longer opens this source
    assert post(event(), secret="whsec-test-0123456789").status_code == 202


def test_events_need_an_id_and_a_time():
    ev = event()
    del ev["time"]
    r = post(ev)
    assert r.status_code == 400 and r.json()["error"]["code"] == "validation_error"
    r = post(event() | {"id": ""})
    assert r.status_code == 400 and r.json()["error"]["code"] == "validation_error"
    r = post(event() | {"time": "yesterday"})
    assert r.status_code == 400 and r.json()["error"]["code"] == "validation_error"


def test_an_unknown_source_is_404():
    r = post(event(), sid="nope-no-such-source")
    assert r.status_code == 404


def test_a_paused_source_accepts_but_does_not_sync():
    with engine.begin() as conn:
        was = conn.execute(text("SELECT status FROM source_system WHERE id = :s"), {"s": SID}).scalar_one()
        conn.execute(text("UPDATE source_system SET status = 'paused' WHERE id = :s"), {"s": SID})
    try:
        r = post(event())
        assert r.status_code == 202 and r.json()["queued_job"] is None
    finally:
        with engine.begin() as conn:
            conn.execute(text("UPDATE source_system SET status = :w WHERE id = :s"), {"s": SID, "w": was})
