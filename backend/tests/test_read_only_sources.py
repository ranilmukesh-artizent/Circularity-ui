"""P9-0.14 (I-18, G §6 items 12 and 13): a source connected read-only is never written to.

- lifecycle.access_of reads the source's current `rw` (saved config over the demo reference)
- send.send marks an instruction for a read-only source failed, with a note, and never calls the writer
- the demo's write targets stay "read_write", so RT-1048 and the demo are unchanged
"""

import pytest
from sqlalchemy import text

from di.connectors import lifecycle
from di.core.db import SessionLocal, engine
from di.services.cases import store as case_store
from di.services.instructions import queue, send, writers
from tests import starting
from tests.helpers import call, client, h


def setup_module():
    starting.reset()


def teardown_module():
    starting.reset()


@pytest.fixture
def instruction():
    """An `order` instruction for the OMS on a case's current approval, removed afterwards."""
    with SessionLocal() as s:
        c = next(x for x in case_store.all_cases(s) if x.get("exec"))
        ref = c["exec"]["ref"]
        step = len(c["exec"]["steps"]) + 60
        iid = s.execute(
            text(
                "INSERT INTO instruction (case_id, approval_ref, step, kind, system, idem_key, match_refs, queued_at) "
                "VALUES (:c, :r, :n, 'order', 'oms', :k, '[]'::jsonb, now()) RETURNING id"
            ),
            {"c": c["id"], "r": ref, "n": step, "k": f"{ref}.{step}.order"},
        ).scalar_one()
        s.commit()
    yield iid
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM instruction WHERE id = :i"), {"i": iid})


def _fake_writer(seen: list):
    def w(s, ins, c, prev):
        seen.append(ins["kind"])
        return writers.Sent([{"call": "fake", "body": {}}], "DOC-1")

    return w


def _make_read_only(sid: str) -> dict:
    got = client.get(f"/api/screens/integration/sources/{sid}", headers=h("developer")).json()
    s = got["source"]
    keys = ("type", "name", "vendor", "ver", "env", "url", "method", "cfg", "interval", "auth", "owner")
    body = {"mode": "edit", "id": sid, "d": {k: s[k] for k in keys}, "maps": got["mappings"],
            "ops": {"read": [], "write": []}, "note": ""}  # fmt: skip
    return call("source.update", body, "developer")


def test_demo_write_targets_are_read_write():  # G6-12
    ids = ("oms", "repair", "tms", "wms", "erp")
    with SessionLocal() as s:
        assert {i: lifecycle.access_of(s, i) for i in ids} == dict.fromkeys(ids, "read_write")
        assert lifecycle.access_of(s, "no-such-source") == "read_write"


def test_read_write_source_sends_as_before(monkeypatch, instruction):  # G6-12
    seen: list = []
    monkeypatch.setitem(writers.WRITERS, "order", _fake_writer(seen))
    assert send.send(instruction) == "sent"
    assert seen == ["order"]


def test_read_only_source_refuses_instruction(monkeypatch, instruction):  # G6-12, G6-13
    r = _make_read_only("oms")
    assert r["ok"], r
    with SessionLocal() as s:
        assert lifecycle.access_of(s, "oms") == "read"
    seen: list = []
    monkeypatch.setitem(writers.WRITERS, "order", _fake_writer(seen))
    assert send.send(instruction) == "failed"
    assert seen == []
    with SessionLocal() as s:
        row = queue.get(s, instruction)
    assert row["status"] == "failed"
    assert row["last_error"].endswith(
        "is connected read-only here: instructions are not sent. Change its access to Read / write to send them."
    )
