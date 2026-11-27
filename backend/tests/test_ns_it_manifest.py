"""P9-12.2 (story NS-IT-01): reconcile a pickup's manifest with what arrived, and keep the chain of custody.

Pickup `PU-01` lists 50 serials; 48 arrive, two never do (`SN-IT-0017`, `SN-IT-0042`) and `SN-IT-9999`, which no manifest
lists, arrives. The records are the ones the mock `it_logistics` serves (source-sim/sim/vendors/itad_logistics, built here as
literals) read through the real adapters' `resources()` and `map()` with a stand-in client (no source-sim). A sync ends with
the job `case.recordMatch` (di.services.cases.record_match.reconcile, X-08): a serial on the manifest with no case is
`EX-IT-MISSING` (critical, Warehouse Manager), a received serial the manifest does not list is `EX-IT-EXTRA`. The custody of a
case is the logistics' own events, with their source. Chain of custody is a record the platform keeps, not a legal claim:
Kinective's Legal team reviews any such use.
"""

import copy
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text

from di import worker
from di.connectors import extra
from di.connectors.base import Record
from di.connectors.registry import ADAPTERS
from di.core import clock
from di.core.db import SessionLocal, engine
from di.services.canonical import store as canonical
from di.services.canonical.schema import serial_key
from di.services.cases import intake
from di.services.cases import store as cases
from tests import starting
from tests.helpers import call

ORG = "Customer A"
PACK = Path(__file__).resolve().parents[1] / "di" / "services" / "modeler" / "packs" / "itad.json"
MANIFEST = [f"SN-IT-{n:04d}" for n in range(1, 51)]
LOST = ("SN-IT-0017", "SN-IT-0042")
EXTRA = "SN-IT-9999"
RECEIVED = [s for s in MANIFEST if s not in LOST] + [EXTRA]
CUSTODY = [
    {"event": "picked_up", "at": "2026-11-02T08:00:00+00:00", "by": "driver-d1"},
    {"event": "in_transit", "at": "2026-11-02T16:00:00+00:00", "by": "carrier-c1"},
    {"event": "received", "at": "2026-11-03T09:00:00+00:00", "by": "dock-w1"},
]


class StandInClient:
    """What an adapter's `resources()` needs of the source client, answering from literals."""

    def __init__(self, session: Any, docs: dict[str, Any]) -> None:
        self.session, self.source_id, self._docs = session, "it_logistics", docs

    def url(self, path: str) -> str:
        return f"http://source-sim/itad-logistics/api{path}"

    def get_json(self, path: str) -> Any:
        return self._docs[path]

    def note_records(self, n: int) -> None:
        return None


def _clean() -> None:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM job WHERE kind IN ('case.gateRecheck', 'case.recordMatch')"))
        conn.execute(text("DELETE FROM work_item"))
        conn.execute(text("DELETE FROM pack_version"))
        conn.execute(text("DELETE FROM customer_overlay"))
        conn.execute(text("DELETE FROM provenance WHERE key LIKE :p"), {"p": "%:SN-IT-%"})
        conn.execute(text("DELETE FROM canonical WHERE key LIKE :p"), {"p": "%:SN-IT-%"})


def _ok(r: dict) -> dict:
    assert r.get("ok"), r
    return r["output"]


@pytest.fixture(autouse=True)
def fresh():
    starting.reset()
    _clean()
    doc: dict[str, Any] = copy.deepcopy(json.loads(PACK.read_text(encoding="utf-8")))
    doc["version"] = "1.9.1"  # the shipped pack, imported and published as the org's
    pid = _ok(call("pack.import", {"doc": doc}, "admin"))["id"]
    _ok(call("pack.submit", {"id": pid}, "admin"))
    _ok(call("pack.approve", {"id": pid}, "approver"))
    with SessionLocal() as s:
        for sid in ("it_cmdb", "it_logistics"):
            extra.register(s, sid, ORG)
        s.commit()
    yield
    _clean()
    starting.reset()


def _sync() -> None:
    """The pickups resource of the adapter, written to the canonical store (one sync of it_logistics)."""
    adapter: Any = ADAPTERS["it_logistics"]
    docs = {"/pickups": [{"pickupId": "PU-01", "manifest": MANIFEST, "custody": CUSTODY, "received": RECEIVED}]}
    with SessionLocal() as s:
        read = next(r for r in adapter.resources() if r.name == "pickups").read
        for rec in read(StandInClient(s, docs), None):  # type: ignore[arg-type]
            canonical.apply(s, "it_logistics", adapter.map(rec))
        s.commit()


def _open(serial: str) -> str:
    body = {"org_unit_id": ORG, "template_key": "itad", "asset_key": serial_key(ORG, serial), "reason": "lease_end",
            "facts": {"serial": serial}}  # fmt: skip
    with SessionLocal() as s:
        c = intake.open_case(s, body, "system")
        s.commit()
    return str(c["id"])


def _case(cid: str) -> dict[str, Any]:
    with SessionLocal() as s:
        c = cases.get(s, cid)
    assert c is not None
    return c


def _items(type_: str) -> list[dict[str, Any]]:
    with SessionLocal() as s:
        rows = s.execute(text("SELECT * FROM work_item WHERE type = :t ORDER BY id"), {"t": type_}).mappings()
        return [dict(r) for r in rows]


def _end_of_sync() -> None:
    worker.HANDLERS["case.recordMatch"]({"source_id": "it_logistics"})


@pytest.fixture
def after_pickup(monkeypatch: pytest.MonkeyPatch) -> None:
    """The workspace clock is a week after the pickup (the pinned clock of the suite is before the literals' dates)."""
    monkeypatch.setattr(clock, "now", lambda: datetime(2026, 11, 10, 9, 0, tzinfo=UTC))


def test_ns_it_01_missing_serials_are_critical(after_pickup: None):
    _sync()
    ids = {serial: _open(serial) for serial in RECEIVED}
    _end_of_sync()
    _end_of_sync()  # a second sync opens nothing again
    missing = _items("EX-IT-MISSING")
    assert len(missing) == 2 and all(sum(s in i["title"] for i in missing) == 1 for s in LOST)
    for i in missing:
        assert (i["kind"], i["status"], i["case_id"], i["org_unit_id"]) == ("exception", "open", None, ORG)
        assert i["owner_role"] == "Warehouse Manager" and i["priority"] == 10  # critical: sorts first in My work
        assert i["action"] == "Find the unit with the carrier or the pickup site, or record it as lost"
    (extra_item,) = _items("EX-IT-EXTRA")
    assert extra_item["case_id"] == ids[EXTRA] and extra_item["owner_role"] == "Warehouse Manager"
    assert extra_item["status"] == "open" and extra_item["priority"] == 100
    on_manifest = [ids[s] for s in RECEIVED if s != EXTRA]
    assert len(on_manifest) == 48 and all(_case(c)["recordMatch"]["found"] is True for c in on_manifest)
    assert _case(ids[EXTRA])["recordMatch"]["found"] is False
    assert _items("not_in_system_of_record") == [] and _items("expected_return_missing") == []


def test_ns_it_01_missing_serials_open_though_the_clock_is_before_the_pickup():
    """The mock's manifest is dated 2 to 3 Nov 2026 and the running stack's clock starts at 7 Oct (smoke P9-12): a time after
    the clock cannot be waited on, so the pack's zero-day wait still opens the item for each serial that never arrived."""
    assert clock.now() < datetime(2026, 11, 2, tzinfo=UTC)
    _sync()
    for serial in RECEIVED:
        _open(serial)
    _end_of_sync()
    missing = _items("EX-IT-MISSING")
    assert len(missing) == 2 and all(sum(s in i["title"] for i in missing) == 1 for s in LOST)


def test_ns_it_01_chain_of_custody_on_case(after_pickup: None):
    _sync()
    cid = _open("SN-IT-0001")
    events = _case(cid)["custody"]
    assert [e["event"] for e in events] == ["picked_up", "in_transit", "received"]
    assert {e["source"] for e in events} == {"it_logistics"}
    assert [e["by"] for e in events] == ["driver-d1", "carrier-c1", "dock-w1"]
    assert events[-1]["at"] == CUSTODY[-1]["at"]
    age_days = (clock.now() - datetime.fromisoformat(events[-1]["at"]).astimezone(UTC)).total_seconds() / 86400
    assert round(age_days, 2) == 7.0  # each event carries its time: the page shows its age (here a week)
    with SessionLocal() as s:  # the serial that never arrived has the first two events only, in the record
        lost = canonical.get(s, "asset", serial_key(ORG, LOST[0]))
    assert lost is not None and [e["event"] for e in lost["data"]["custody"]] == ["picked_up", "in_transit"]
    assert lost["data"]["disposition"] == "in_transit" and lost["data"]["pickup"] == "PU-01"


def test_ns_it_01_the_cmdb_adapter_maps_identity_and_lease_terms():
    ci = {
        "ciId": "CI00005", "serial": "SN-IT-0005", "model": "DT-30 S5", "assetClass": "desktop", "ownerOrg": ORG,
        "securityLevel": "standard", "leaseRef": "LS-IT-0005", "lessorReturnRequired": True, "consentToResell": False,
        "newPrice": 900.0, "media": [{"mediaSerial": "MS-IT-0005-1", "type": "ssd"}], "org_unit_id": ORG,
    }  # fmt: skip
    facts = ADAPTERS["it_cmdb"].map(Record("cis", "SN-IT-0005", ci))
    got = {(f.model, f.field): f.value for f in facts}
    key = serial_key(ORG, "SN-IT-0005")
    assert {f.key for f in facts} == {key}
    assert got[("asset", "asset_class")] == "desktop" and got[("asset", "lessor_return_required")] is True
    assert got[("asset", "consent_to_resell")] is False and got[("asset", "lease_ref")] == "LS-IT-0005"
    assert got[("asset", "media")] == ci["media"] and got[("market", "new_price")] == 900.0
    assert got[("asset", "owner_tenant")] == ORG


def test_ns_it_01_erasures_group_by_serial():
    adapter: Any = ADAPTERS["it_logistics"]
    rows = [{"mediaSerial": f"MS-IT-0005-{k}", "method": "purge", "verification": "passed"} for k in (1, 2)]
    rows.append({"mediaSerial": "MS-IT-0006-1", "method": "clear", "verification": "passed"})
    with SessionLocal() as s:
        read = next(r for r in adapter.resources() if r.name == "erasures").read
        recs = list(read(StandInClient(s, {"/erasures": rows}), None))  # type: ignore[arg-type]
    assert [r.ext_id for r in recs] == ["SN-IT-0005", "SN-IT-0006"]
    (fact,) = adapter.map(recs[0])
    assert (fact.model, fact.field, len(fact.value)) == ("condition", "erasures", 2) and fact.key == serial_key(ORG, "SN-IT-0005")
