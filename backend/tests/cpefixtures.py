"""The telecom CPE lots as the real adapter writes them (plan 9, P9-12.6; no source-sim): a lot of one model and grade for a
week, its serials, and the factory-reset record of each serial the subscriber-returns system holds. Shared by `test_ns_cpe.py`
and `test_telecom_cpe_paths.py`. Every record goes through the adapter's own `resources()` and `map()` with a stand-in client."""

import copy
import json
from pathlib import Path
from typing import Any

from sqlalchemy import text

from di.connectors import extra
from di.connectors.registry import ADAPTERS
from di.core.db import SessionLocal, engine
from di.services.canonical import store as canonical
from di.services.canonical.schema import serial_key
from di.services.cases import intake
from di.services.cases import store as cases
from tests import starting
from tests.helpers import call

ORG = "Customer A"
PACK = Path(__file__).resolve().parents[1] / "di" / "services" / "modeler" / "packs" / "telecom_cpe.json"
AT = "2026-11-20T08:00:00+00:00"
# sample lots: id -> (units, grade, first serial number, serial numbers with no reset record)
LOTS: dict[str, tuple[int, str, int, tuple[int, ...]]] = {
    "LOT-R7-B-W47": (500, "B", 1, ()),
    "LOT-R7-B-W48": (900, "B", 1001, ()),
    "LOT-R7-C-W47": (400, "C", 2001, ()),
    "LOT-R7-B-W47-GAP": (500, "B", 3001, (3101, 3202, 3303)),
}


class StandInClient:
    """What an adapter's `resources()` needs of the source client, answering from literals."""

    def __init__(self, session: Any, docs: dict[str, Any]) -> None:
        self.session, self.source_id, self._docs = session, "cpe_bss", docs

    def url(self, path: str) -> str:
        return f"http://source-sim/cpe-returns/api{path}"

    def get_json(self, path: str) -> Any:
        return self._docs[path]

    def note_records(self, n: int) -> None:
        return None


def serial(n: int) -> str:
    return f"SN-CPE-R7-{n:04d}"


def lot_key(lot_id: str) -> str:
    return serial_key(ORG, lot_id)


def ok(r: dict) -> dict:
    assert r.get("ok"), r
    return r["output"]


def clean() -> None:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM job WHERE kind IN ('case.gateRecheck', 'case.recordMatch')"))
        conn.execute(text("DELETE FROM work_item"))
        conn.execute(text("DELETE FROM pack_version"))
        conn.execute(text("DELETE FROM customer_overlay"))
        for pattern in ("%:SN-CPE-%", "%:LOT-R7-%"):
            conn.execute(text("DELETE FROM provenance WHERE key LIKE :p"), {"p": pattern})
            conn.execute(text("DELETE FROM canonical WHERE key LIKE :p"), {"p": pattern})
        conn.execute(text("DELETE FROM standing_policy_version"))
        conn.execute(text("DELETE FROM standing_policy"))


def start() -> None:
    """A clean store, the shipped pack imported and published as the org's, the source registered."""
    starting.reset()
    clean()
    doc: dict[str, Any] = copy.deepcopy(json.loads(PACK.read_text(encoding="utf-8")))
    doc["version"] = "1.9.1"
    pid = ok(call("pack.import", {"doc": doc}, "admin"))["id"]
    ok(call("pack.submit", {"id": pid}, "admin"))
    ok(call("pack.approve", {"id": pid}, "approver"))
    with SessionLocal() as s:
        extra.register(s, "cpe_bss", ORG)
        s.commit()


def finish() -> None:
    clean()
    starting.reset()


def sync_lot(lot_id: str, *, resets: list[int] | None = None) -> list[str]:
    """The lot and the reset records of its serials written to the canonical store (a sync of cpe_bss). `resets` are the serial
    numbers that have a record (default: the lot's, but the ones it lacks). Returns the lot's serials."""
    units, grade, first, missing = LOTS[lot_id]
    numbers = list(range(first, first + units))
    serials = [serial(n) for n in numbers]
    have = [n for n in numbers if n not in missing] if resets is None else resets
    adapter: Any = ADAPTERS["cpe_bss"]
    docs = {
        "/lot-grades": [{"lotId": lot_id, "model": "R7", "grade": grade, "week": "2026-W47", "serials": serials}],
        "/factory-resets": [{"serial": serial(n), "method": "factory_reset", "firmwareRefreshed": True, "at": AT} for n in have],
    }
    with SessionLocal() as s:
        for name in ("lot_grades", "factory_resets"):
            read = next(r for r in adapter.resources() if r.name == name).read
            facts = [f for rec in read(StandInClient(s, docs), None) for f in adapter.map(rec)]  # type: ignore[arg-type]
            canonical.apply(s, "cpe_bss", facts)
        s.commit()
    return serials


def add_reset(n: int) -> None:
    """The record of one more serial arrives (a later sync)."""
    adapter: Any = ADAPTERS["cpe_bss"]
    docs = {"/factory-resets": [{"serial": serial(n), "method": "factory_reset", "firmwareRefreshed": True, "at": AT}]}
    with SessionLocal() as s:
        read = next(r for r in adapter.resources() if r.name == "factory_resets").read
        for rec in read(StandInClient(s, docs), None):  # type: ignore[arg-type]
            canonical.apply(s, "cpe_bss", adapter.map(rec))
        s.commit()


def open_lot(lot_id: str) -> dict[str, Any]:
    body = {"org_unit_id": ORG, "template_key": "telecom_cpe", "asset_key": lot_key(lot_id), "reason": "rma", "facts": {}}
    with SessionLocal() as s:
        c = intake.open_case(s, body, "system")
        s.commit()
    return dict(c)


def get(cid: str) -> dict[str, Any]:
    with SessionLocal() as s:
        c = cases.get(s, cid)
    assert c is not None
    return c


def route(c: dict[str, Any], rid: str) -> dict[str, Any]:
    return next(r for r in c["routes"] if r["id"] == rid)
