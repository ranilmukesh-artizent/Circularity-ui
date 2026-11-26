"""Plan 9, P9-3.18 (story TF-14): a non-return fee is posted from a closed contract line.

A line the fleet contract system moved to `closed_not_returned` raises one `non_return` item for the Fleet desk with the fee as a
value line; a person posts the fee with `nonReturnFee.post`, which queues one `nonreturnfee` instruction to SAP S/4HANA
through the existing instruction queue (`instructions.fees`, writer `writers_fleet.fee_post`) and closes the item. A second post
is a duplicate. The action is held for a person when an agent prepares it (HELD_FOR_PERSON, I-10): an agent never posts.
No model step (R16): the fee is the contract's own figure, so there is no model test. Maker-checker does not apply: the poster is
the only actor and nothing is approved; the permission `postFees` and the tenant boundary are tested below.

The tests use their own serial and line (never the mock's AGR-20991, which a synced stack holds), and the S/4 call is replaced
by a function that records the journal items; the mock's own side is the S/4 journal test of source-sim. It starts and ends with
the demo reset.
"""

import pytest
from sqlalchemy import text

from di.connectors.adapters.fleet_contracts import ADAPTER
from di.core.db import SessionLocal, engine
from di.services.agents.forbidden import forbidden, held_for_person
from di.services.canonical import store as canonical
from di.services.cases import process
from di.services.instructions import fees, queue, send, writers, writers_fleet
from tests import starting
from tests.helpers import call, client, h

ORG = "tool-fleet-nr"
ACTION = "nonReturnFee.post"
SERIAL, LINE = "TFT-14001", "FL-TF14-01"
KEYS = {"k": [SERIAL, "FC-TF14"]}


def _clean() -> None:
    with engine.begin() as c:
        for m in ("contract_line", "contract"):
            for t in ("provenance", "canonical", "conflict"):
                c.execute(text(f"DELETE FROM {t} WHERE model = :m AND key = ANY(:k)"), {"m": m, **KEYS})  # noqa: S608
        c.execute(text("DELETE FROM work_item WHERE type = 'non_return'"))
        c.execute(text("DELETE FROM instruction WHERE kind = 'nonreturnfee'"))


@pytest.fixture(autouse=True)
def world():
    starting.reset()
    _clean()
    assert call("org.create", {"id": ORG, "parent_id": "Customer A", "kind": "company", "name": "Tool fleet NR"}, "admin")["ok"]
    yield
    _clean()
    starting.reset()


def _line(status: str = "closed_not_returned", fee: float = 180.0) -> None:
    row = {"line_id": LINE, "contract_id": "FC-TF14", "status": status, "non_return_fee": fee, "tool_class": "AGR"}
    with SessionLocal() as s:
        canonical.apply(s, "fleet", [canonical.Fact("contract_line", SERIAL, k, v, resource="lines") for k, v in row.items()])
        s.commit()


def _sync() -> list[int]:
    """What the sync of the fleet source does once it has written the lines."""
    with SessionLocal() as s:
        ids = ADAPTER.after_sync(s)
        s.commit()
        return ids


def _mine() -> list[dict]:
    with SessionLocal() as s:
        rows = s.execute(text("SELECT * FROM work_item WHERE type = 'non_return' AND title = :t"), {"t": fees.title_of(LINE)})
        return [dict(r) for r in rows.mappings()]


def _instructions() -> list[dict]:
    with SessionLocal() as s:
        return [dict(r) for r in s.execute(text("SELECT * FROM instruction WHERE kind = 'nonreturnfee'")).mappings()]


@pytest.fixture
def sending(monkeypatch):
    monkeypatch.setattr(queue, "enabled", lambda: True)


# ------------------------------------------------------------------ the closed line shows its fee
def test_tf_14_closed_line_shows_fee():
    _line("returned", 0.0)
    assert _sync() is not None and _mine() == []  # a returned line raises nothing
    _line()
    _sync()
    _sync()  # a second sync raises nothing more
    (item,) = _mine()
    assert item["kind"] == "exception" and item["owner_role"] == "Planner" and item["status"] == "open"
    assert item["cause"].startswith(f"Contract line {LINE} closed without the tool {SERIAL}.")
    assert "$180" in item["cause"]
    with SessionLocal() as s:
        line = fees.line_row(s, LINE)
    assert line is not None and fees.value_line(line) == {
        "type": "v", "label": f"Non-return fee {LINE}", "basis": "contract fee for a tool not returned", "amt": 180.0,
    }  # fmt: skip
    mine = [
        i for i in client.get("/api/screens/mywork", headers=h("planner.a")).json()["items"] if i["title"] == fees.title_of(LINE)
    ]
    assert len(mine) == 1 and "$180" in mine[0]["cause"]


def test_tf_14_a_fee_of_zero_raises_nothing():
    _line(fee=0.0)
    _sync()
    assert _mine() == []


# ------------------------------------------------------------------ the post
def test_tf_14_post_fee_sends_instruction(sending):
    _line()
    _sync()
    r = call(ACTION, {"line_id": LINE}, "planner.a")
    assert r["ok"] is True, r
    (ins,) = _instructions()
    assert (ins["system"], ins["kind"], ins["status"]) == ("erp", "nonreturnfee", "queued")
    assert ins["idem_key"] == f"FEE.{LINE}.18000" and ins["detail"]["fee"] == 180.0 and ins["detail"]["serial"] == SERIAL
    (item,) = _mine()
    assert item["status"] == "done" and item["outcome"] == "Fee posted: $180" and item["closed_by"] == "planner-a"
    again = call(ACTION, {"line_id": LINE}, "planner.a")
    assert again["ok"] is False and again["error"]["code"] == "duplicate", again
    assert len(_instructions()) == 1


def test_tf_14_the_writer_posts_the_fee_to_s4_and_the_queue_sends_it(sending, monkeypatch):
    seen: list = []

    def journal(s, ins, ref, header, items):  # the signature of writers.post_journal
        seen.append((ref, header, items))
        return "0100000042", {"AccountingDocument": "0100000042", "duplicate": False}

    monkeypatch.setattr(writers, "post_journal", journal)
    _line()
    _sync()
    assert call(ACTION, {"line_id": LINE}, "planner.a")["ok"]
    (ins,) = _instructions()
    assert send.send(ins["id"]) == "sent"
    ref, header, items = seen[0]
    assert (ref, header) == (f"FEE-{LINE}", f"Fee {LINE}")
    assert f"<GLAccount>{writers.GL_FEE}</GLAccount>" in items[0] and ">-180.00<" in items[0]  # the fee, a credit
    assert f"<GLAccount>{writers.GL_CLEARING}</GLAccount>" in items[1] and ">180.00<" in items[1]  # against the clearing item
    (done,) = _instructions()
    assert done["status"] == "sent" and done["doc_ref"] == "0100000042" and done["detail"]["fee"] == 180.0
    with pytest.raises(writers.NotApplicable):
        writers_fleet.fee_post(None, {"detail": {"line_id": "", "fee": 0}, "idem_key": "x"}, {}, {})  # type: ignore[arg-type]


def test_tf_14_posting_a_line_without_a_fee_is_refused():
    _line("returned", 0.0)
    r = call(ACTION, {"line_id": LINE}, "planner.a")
    assert r["ok"] is False and r["error"]["code"] == "validation_error", r
    r = call(ACTION, {"line_id": "FL-NOPE"}, "planner.a")
    assert r["ok"] is False and r["error"]["code"] == "not_found", r


# ------------------------------------------------------------------ who may post (R21)
def test_non_return_fee_needs_post_fees():
    _line()
    _sync()
    r = call(ACTION, {"line_id": LINE}, "warehouse1")
    assert r["ok"] is False and r["error"]["code"] == "out_of_scope", r
    assert _mine()[0]["status"] == "open" and _instructions() == []


def test_non_return_fee_agent_held(sending):
    _line()
    _sync()
    assert held_for_person(ACTION) and not forbidden(ACTION)
    hdr = h("planner.a") | {"X-Circularity-Preparer": "coordinator"}
    r = client.post(f"/api/actions/{ACTION}", json={"line_id": LINE}, headers=hdr).json()
    # a commit: the agent can only prepare it, a person presses the button
    assert r["ok"] is False and r["error"]["code"] == "approval_required", r
    assert _mine()[0]["status"] == "open" and _instructions() == []  # nothing was sent


def test_non_return_fee_tenant_boundary(sending):
    _line()
    with SessionLocal() as s:  # an item of the org unit that owns the tool (what `fees.org_of` finds from its case)
        process.open_item(
            s, kind="exception", case_id=None, org_unit_id=ORG, type=fees.EXCEPTION, title=fees.title_of(LINE), cause="c",
            action="a", owner_role="Planner", due_hours=None, by="system",
        )  # fmt: skip
        s.commit()
    r = call(ACTION, {"line_id": LINE}, "planner.b")
    assert r["ok"] is False and r["error"]["code"] == "tenant_boundary", r
    assert _mine()[0]["status"] == "open" and _instructions() == []
    assert call(ACTION, {"line_id": LINE}, "planner.a")["ok"] is True  # Customer A's own planner may
