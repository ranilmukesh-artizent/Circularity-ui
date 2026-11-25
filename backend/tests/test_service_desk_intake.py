"""Plan 9, P9-4.3 (story SD-01): one case per service ticket or batch.

A ticket the `sdesk` source landed (table `service_ticket`) opens one tool-fleet case with the reason `service_ticket`
(`service_desk.intake.open_from_ticket`, through `cases.intake.open_case`: the only intake) and the flow `service_desk`. A
batch ticket (many tools) is one case that keeps every line. Every line is checked against the contract right (GR-07) and the
safety recall register (GR-12); the case is gated by its worst line, and the page lists the result of each line. The tickets
here are written to the table as the source's sync lands them (the sync itself is `test_service_desk_sources.py`, which needs
source-sim). No model step: a line's fault code, cover and age are structured fields; its free text is shown, never read.

It starts and ends with the demo reset.
"""

import json

import pytest
from sqlalchemy import text

from di.core.db import SessionLocal, engine
from di.repositories import service_tickets
from di.services.actions.registry import ACTIONS, ActionError
from di.services.agents.forbidden import FORBIDDEN_ACTIONS
from di.services.canonical import store as canonical
from di.services.cases import intake, store
from di.services.modeler.pack import load_pack
from di.services.service_desk import intake as sd
from tests import starting
from tests.helpers import call, client, h, tool_case_facts

ORG = "tool-fleet-a"
CLASSES = ("CMH", "BRK", "DCD", "CRH", "AGR", "LSR")
REPAIR = {"recall_id": "RC-2026-017", "tool_class": "BRK", "serial_from": "BRK-51000", "serial_to": "BRK-51999",
          "remedy": "repair", "affected_parts": ["Impact mechanism"], "status": "active"}  # fmt: skip


def _line(serial: str, cls: str, age: int, fault: str = "MOT", cover: str = "fleet") -> dict:
    return {"serial": serial, "model_class": cls, "age_months": age, "fault_code": fault, "fault_text": "Runs hot, loses power",
            "cover_type": cover, "cover_until": "2027-06-30"}  # fmt: skip


def _clean() -> None:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM provenance WHERE model IN ('contract_line', 'contract', 'recall')"))
        conn.execute(text("DELETE FROM canonical WHERE model IN ('contract_line', 'contract', 'recall')"))
        conn.execute(text("DELETE FROM service_ticket"))


@pytest.fixture(autouse=True)
def fresh():
    starting.reset()
    _clean()
    assert call("org.create", {"id": ORG, "parent_id": "workspace", "kind": "company", "name": "Tool fleet A"}, "admin")["ok"]
    yield
    starting.reset()
    _clean()


def _ticket(number: str, lines: list[dict], batch: str | None = None, org: str | None = ORG) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO service_ticket (number, org_unit_id, account, market, site, batch_id, lines, requester_role, "
                "loaner_promised, opened_at, source) VALUES (:n, :o, 'ACC-US-0042', 'US', 'Austin', :b, CAST(:l AS jsonb), "
                "'Site manager', false, '2026-11-01T09:00:00+00:00', 'sdesk')"
            ),
            {"n": number, "o": org, "b": batch, "l": json.dumps(lines)},
        )


def _contracts(lines: list[dict]) -> None:
    for x in lines:
        tool_case_facts(x["serial"], {"cls": x["model_class"]})


def _row(number: str):
    with SessionLocal() as s:
        row = next((t for t in service_tickets.pending(s, ORG) if t.number == number), None)
        assert row is not None, number
        return row


def _open(number: str) -> dict:
    with SessionLocal() as s:
        c = sd.open_from_ticket(s, _row(number), "system")
        s.commit()
    return c


def _items(case_id: str, type_: str) -> list[dict]:
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT type, owner_role, status FROM work_item WHERE case_id = :c AND type = :t ORDER BY id"),
            {"c": case_id, "t": type_},
        )
        return [dict(r._mapping) for r in rows]


# ------------------------------------------------------------------ the pure case facts
def test_sd_01_ticket_case_facts_and_life_used():
    lines = [_line("CRH-46042", "CRH", 18)]
    _ticket("CS0010042", lines)
    f = sd.ticket_case("RT-1", _row("CS0010042"))
    assert f["flow"] == "service_desk" and f["ticket"] == "CS0010042" and f["batch"] is False
    assert (f["account"], f["market"], f["site"]) == ("ACC-US-0042", "US", "Austin")
    assert f["lines"] == [{"n": 1, **lines[0], "life_used_pct": 50}]  # 18 of 36 months (CRH is rated 36)
    rated = {"CMH": 48, "BRK": 48, "DCD": 60, "CRH": 36, "AGR": 36, "LSR": 60}
    assert rated == sd.RATED and load_pack("tool_fleet").valuer.params["service_desk"]["rated_months"] == rated


def test_sd_01_unknown_class_is_a_validation_error():
    _ticket("CS0010043", [_line("XXX-1", "XXX", 10)])
    with pytest.raises(ActionError) as e:
        sd.ticket_case("RT-1", _row("CS0010043"))
    assert e.value.code == "validation_error"


# ------------------------------------------------------------------ one case per ticket
def test_sd_01_one_case_per_ticket():
    lines = [_line("CRH-46042", "CRH", 18)]
    _contracts(lines)
    _ticket("CS0010042", lines)
    c = _open("CS0010042")
    assert c["template"] == "tool_fleet" and c["flow"] == "service_desk" and c["intake"]["reason"] == "service_ticket"
    assert c["intake"]["key"] == "CS0010042:service_ticket" and c["recommendation"] is not None
    d = c["serviceDesk"]
    assert d["ticket"] == "CS0010042" and d["batch"] is False and len(d["lines"]) == 1
    ln = d["lines"][0]
    assert (ln["model_class"], ln["fault_code"], ln["age_months"], ln["cover_type"], ln["life_used_pct"]) == (
        "CRH",
        "MOT",
        18,
        "fleet",
        50,
    )
    with engine.connect() as conn:
        assert conn.execute(text("SELECT case_id FROM service_ticket WHERE number = 'CS0010042'")).scalar() == c["id"]
    with SessionLocal() as s:
        assert service_tickets.pending(s, ORG) == []


def test_sd_01_batch_keeps_lines():
    lines = [_line(f"{CLASSES[i % 6]}-{45000 + i}", CLASSES[i % 6], 6 + 2 * i) for i in range(22)]
    _contracts(lines)
    _ticket("CS0010050", lines, batch="BATCH-0050")
    c = _open("CS0010050")
    d = c["serviceDesk"]
    assert d["batch"] is True and len(d["lines"]) == 22 and [x["n"] for x in d["lines"]] == list(range(1, 23))
    assert [x["serial"] for x in d["lines"]] == [x["serial"] for x in lines]
    with SessionLocal() as s:
        cases = s.execute(text("SELECT count(*) FROM case_record WHERE data->'intake'->>'reason' = 'service_ticket'")).scalar()
    assert cases == 1


def test_sd_01_duplicate_refused():
    lines = [_line("CRH-46042", "CRH", 18)]
    _contracts(lines)
    _ticket("CS0010042", lines)
    first = _open("CS0010042")
    with SessionLocal() as s, pytest.raises(ActionError) as e:
        sd.open_from_ticket(s, _row_again("CS0010042"), "system")
    assert e.value.code == "duplicate"
    assert str(e.value) == f"{first['id']} is already open for CS0010042 (service_ticket)."


def _row_again(number: str):
    """The ticket as the source reads it again after its case was opened (a re-sync keeps `case_id`; this is the row as read)."""
    with engine.begin() as conn:
        conn.execute(text("UPDATE service_ticket SET case_id = NULL WHERE number = :n"), {"n": number})
    return _row(number)


# ------------------------------------------------------------------ the two gates on every line
def test_sd_01_contract_and_recall_checked():
    # line 1 has an active contract; line 2 has none; line 3 is under an active repair recall
    ok, none_, hit = _line("CRH-46042", "CRH", 18), _line("CMH-46043", "CMH", 20), _line("BRK-51007", "BRK", 30)
    _contracts([ok, hit])
    with SessionLocal() as s:
        canonical.apply(
            s, "recall", [canonical.Fact("recall", REPAIR["recall_id"], k, v, resource="notices") for k, v in REPAIR.items()]
        )
        s.commit()
    _ticket("CS0010060", [ok, none_, hit])
    c = _open("CS0010060")
    with SessionLocal() as s:
        shown = sd.view(s, c)
    assert shown is not None
    by = {x["serial"]: {g["id"]: g for g in x["gates"]} for x in shown["lines"]}
    assert by["CRH-46042"]["G-CON-2"]["passed"] and by["CRH-46042"]["G-TOOL-REC"]["passed"]
    assert (
        not by["CMH-46043"]["G-CON-2"]["passed"]
        and by["CMH-46043"]["G-CON-2"]["reason"] == "No active contract for serial CMH-46043"
    )
    assert by["BRK-51007"]["G-CON-2"]["passed"] and not by["BRK-51007"]["G-TOOL-REC"]["passed"]
    assert "RC-2026-017" in by["BRK-51007"]["G-TOOL-REC"]["reason"]
    # the case is gated by its worst line: the one without a contract holds it, and the exception is the Fleet desk's
    assert c["serial"] == "CMH-46043" and c["gateHold"]["gates"] == ["G-CON-2"] and c["recommendation"] is None
    items = _items(c["id"], "no_active_contract")
    assert len(items) == 1 and items[0]["owner_role"] == "Planner" and items[0]["status"] == "open"


def test_sd_01_a_recalled_line_is_quarantined_with_no_priced_option():
    hit = _line("BRK-51007", "BRK", 30)
    _contracts([hit])
    with SessionLocal() as s:
        canonical.apply(
            s, "recall", [canonical.Fact("recall", REPAIR["recall_id"], k, v, resource="notices") for k, v in REPAIR.items()]
        )
        s.commit()
    _ticket("CS0010061", [hit])
    c = _open("CS0010061")
    assert c["serial"] == "BRK-51007"
    open_ids = {r["id"] for r in c["routes"] if not r["excluded"]}
    assert not open_ids & {"release", "redeploy", "resell"}  # a repair recall blocks them until Quality releases the tool
    q = _items(c["id"], "recall_quarantine")
    assert len(q) == 1 and q[0]["owner_role"] == "Approver"  # Quality is an Approver role in the pack


# ------------------------------------------------------------------ the post-sync hook
def test_sd_01_hook_opens_pending_tickets_once_and_a_dry_run_writes_nothing():
    lines = [_line("CRH-46042", "CRH", 18)]
    _contracts(lines)
    _ticket("CS0010042", lines)
    with SessionLocal() as s:  # a dry run: the sync's session is rolled back with the cases
        assert len(sd.open_all_pending(s)) == 1
        s.rollback()
    with SessionLocal() as s:
        assert (
            s.execute(text("SELECT count(*) FROM case_record WHERE data->'intake'->>'reason' = 'service_ticket'")).scalar() == 0
        )
        assert len(service_tickets.pending(s, ORG)) == 1
    with SessionLocal() as s:
        assert len(sd.open_all_pending(s)) == 1
        s.commit()
    with SessionLocal() as s:
        assert sd.open_all_pending(s) == []  # nothing pending: nothing opens twice


def test_sd_01_a_shared_ticket_stays_pending():
    lines = [_line("CRH-46042", "CRH", 18)]
    _contracts(lines)
    _ticket("CS0010042", lines, org=None)
    with SessionLocal() as s:
        assert sd.open_all_pending(s) == []  # no org unit to own the case: it stays pending


# ------------------------------------------------------------------ the case page, the manual path, parity
def test_sd_01_the_case_page_shows_the_ticket():
    lines = [_line("CRH-46042", "CRH", 18)]
    _contracts(lines)
    _ticket("CS0010042", lines)
    c = _open("CS0010042")
    r = client.get(f"/api/screens/case/{c['id']}", headers=h("admin"))
    assert r.status_code == 200, r.text
    d = r.json()["case"]["serviceDesk"]
    assert d["ticket"] == "CS0010042" and d["account"] == "ACC-US-0042" and d["loanerPromised"] is False
    ln = d["lines"][0]
    assert ln["family"] == "Cordless rotary hammer, 22 V" and ln["life_used_pct"] == 50
    assert [g["id"] for g in ln["gates"]] == ["G-CON-2", "G-TOOL-REC"] and all(g["passed"] for g in ln["gates"])


def test_sd_01_a_book_case_has_no_service_desk_block():
    r = client.get("/api/screens/case/RT-1048", headers=h("admin"))
    assert r.status_code == 200 and "serviceDesk" not in r.json()["case"]


def test_sd_01_the_manual_path_and_no_new_action():
    assert "service_ticket" in intake.REASONS
    with SessionLocal() as s:
        assert store.get(s, "RT-1048") is not None
    assert not [a for a in ACTIONS if a.startswith("service_desk.") or a.startswith("ticket.")]
    assert not any("ticket" in a for a in FORBIDDEN_ACTIONS)
