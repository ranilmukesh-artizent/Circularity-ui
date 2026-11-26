"""Test helper (plan 9, P9-12.10): the serialised retail returns pack imported and published as the org's, and the facts of a
returned phone and a returned jacket as the retail returns portal (`b2c_ret`) lists them. Synthetic data."""

import copy
import json
from pathlib import Path
from typing import Any

from sqlalchemy import text

from di.core.db import SessionLocal, engine
from di.services.cases import intake
from di.services.cases import store as cases
from tests.helpers import call

ORG = "Customer A"
PACK = Path(__file__).resolve().parents[1] / "di" / "services" / "modeler" / "packs" / "b2c_serial.json"
IMEI = "359990000000428"
PHONE: dict[str, Any] = {
    "itemId": "RET-0001", "serial": "SN-B2C-0001", "imei": IMEI, "itemClass": "phone", "sku": "PH-14-128", "unsold": False,
    "exceptionEvidence": None, "brand": "Apple", "model": "iPhone 14", "grade": "B", "band": "25-48m", "ref": 300, "qty": 1,
    "doh": 5,
}  # fmt: skip
JACKET: dict[str, Any] = {
    "itemId": "RET-0002", "serial": "SN-B2C-0002", "imei": None, "itemClass": "apparel", "sku": "JK-221-M", "unsold": True,
    "exceptionEvidence": None, "ref": 80, "qty": 1,
}  # fmt: skip


def clean() -> None:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM job WHERE kind IN ('case.gateRecheck', 'case.recordMatch')"))
        conn.execute(text("DELETE FROM work_item"))
        conn.execute(text("DELETE FROM pack_version"))
        conn.execute(text("DELETE FROM customer_overlay"))
        conn.execute(text("DELETE FROM provenance WHERE source_id IN ('dvreg', 'dvlab') AND key LIKE 'IMEI:%'"))
        conn.execute(text("DELETE FROM canonical WHERE model = 'condition' AND key LIKE 'IMEI:%'"))


def publish_pack() -> None:
    """The shipped pack, imported and published as the org's (an imported pack is what a case opens with)."""
    doc: dict[str, Any] = copy.deepcopy(json.loads(PACK.read_text(encoding="utf-8")))
    doc["version"] = "1.9.1"
    r = call("pack.import", {"doc": doc}, "admin")
    assert r.get("ok"), r
    pid = r["output"]["id"]
    assert call("pack.submit", {"id": pid}, "admin").get("ok")
    assert call("pack.approve", {"id": pid}, "approver").get("ok")


def open_item(facts: dict[str, Any], reason: str = "rma") -> dict[str, Any]:
    body = {"org_unit_id": ORG, "template_key": "b2c_serial", "asset_key": facts.get("serial") or facts["itemId"],
            "reason": reason, "facts": facts}  # fmt: skip
    with SessionLocal() as s:
        c = intake.open_case(s, body, "system")
        s.commit()
    return dict(c)


def case(cid: str) -> dict[str, Any]:
    with SessionLocal() as s:
        c = cases.get(s, cid)
    assert c is not None
    return dict(c)
