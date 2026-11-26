"""Plan 9, P9-6.7 (story DV-04): the data-wipe certificate gate for a received device (G-DEV-WIPE, guardrail GR-D1).

No certificate, or one without `method`, `tool_version`, `verification` or `operator`, fails every channel but recycle with
"No data-wipe certificate (GR-D1): listing blocked" and holds the case; the cases of one batch that wait are held as one batch
and each releases on its own when its certificate lands (`case.gateRecheck`), journaled "Released: wipe certificate <id>
arrived". A failed verification adds the step "Wipe verification failed: re-run the wipe or destroy the storage" and the
channels stay blocked. Nothing here writes language: no model call. The mock's own posting is `test_device_wipe_sim.py`.
"""

from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy import text

from di import worker
from di.connectors.adapters import device_lab as lab
from di.core import clock
from di.core.db import SessionLocal, engine
from di.services.agents.forbidden import forbidden
from di.services.canonical import store as canonical
from di.services.canonical.store import Fact
from di.services.cases import store
from di.services.device import intake as device_intake
from tests import starting
from tests.device_registry import seed_registry, seed_wipe
from tests.helpers import client, h

ORG = "Customer A"
BATCH = "BATCH-0007"
GR_D1 = "No data-wipe certificate (GR-D1): listing blocked"


def _clean() -> None:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM provenance WHERE source_id IN ('dvlab', 'dvreg') AND key LIKE 'IMEI:%'"))
        conn.execute(text("DELETE FROM canonical WHERE model IN ('condition', 'asset') AND key LIKE 'IMEI:%'"))
        conn.execute(text("DELETE FROM device_tradein"))
        conn.execute(text("DELETE FROM device_price_point"))
        conn.execute(text("DELETE FROM job WHERE kind = 'case.gateRecheck'"))


@pytest.fixture(autouse=True)
def fresh():
    starting.reset()
    _clean()
    yield
    starting.reset()
    _clean()


def _imei(n: int) -> str:
    return f"3599900000{n:05d}"


def _open(*numbers: int, batch: str = BATCH, clear: bool = True) -> list[dict]:
    """Land one trade-in per number and open their cases; a clear registry check is seeded unless `clear` is false."""
    when = (clock.now() - timedelta(days=5)).isoformat()
    for n in numbers:
        if clear:
            seed_registry(_imei(n), wipe=False)
        doc = {
            "tradeInId": f"TI-{n:05d}", "imei": _imei(n),
            "sku": {"brand": "Apple", "model": "iPhone 14", "storageGb": 128, "colour": "Blue", "carrierLock": "unlocked"},
            "quote": {"declaredGrade": "B", "amount": 410, "currency": "USD", "quotedAt": when},
            "partner": "P01", "batchId": batch, "bulk": False, "receivedAt": when, "payoutAmount": 410,
        }  # fmt: skip
        with SessionLocal() as s:
            lab.land_tradein(s, doc, ORG)
            s.commit()
    with SessionLocal() as s:
        ids = device_intake.open_pending(s, ORG)
        s.commit()
        out = [store.get(s, i) for i in ids]
    assert all(c is not None for c in out)
    return sorted(out, key=lambda c: c["valuer"]["imei"])  # type: ignore[arg-type,index]


def _get(cid: str) -> dict:
    with SessionLocal() as s:
        c = store.get(s, cid)
    assert c is not None
    return c


def _post(n: int, **over: Any) -> dict:
    """The certificate the lab posts, as the dvlab adapter lands it (`condition.wipe_certificate`)."""
    cert = {"certificate_id": f"WC-{n:05d}", "method": "Purge", "tool_version": "4.2.1", "verification": "pass",
            "operator": "OP-77", "at": clock.now().isoformat()} | over  # fmt: skip
    with SessionLocal() as s:
        canonical.apply(s, "dvlab", [Fact("condition", f"IMEI:{_imei(n)}", "wipe_certificate", cert)])
        s.commit()
    return cert


def _rechecks() -> int:
    with SessionLocal() as s:
        rows = s.execute(text("SELECT payload FROM job WHERE kind = 'case.gateRecheck' AND status = 'queued'")).scalars().all()
    for p in rows:
        worker.HANDLERS["case.gateRecheck"](p)
    return len(rows)


def _sale(c: dict) -> list[dict]:
    """The routes the wipe gate blocks: not recycle (the gate keeps it, P9-6.15) and not repair then sell without a quote (the
    valuer's own reason comes first)."""
    return [r for r in c["routes"] if r["id"] not in ("recycle", "repair_sell")]


def test_dv_04_no_listing_without_certificate():
    (c,) = _open(1)
    assert c["routes"] and all(r["excluded"] and (GR_D1 in r["failReason"] or "(GR-D9)" in r["failReason"]) for r in _sale(c))
    assert {r["id"] for r in c["routes"]} >= {"buynow", "offers", "auction"}
    assert c["recommendation"] is None and c["stage"] == "none"
    g = next(x for x in c["gates"] if x["id"] == "G-DEV-WIPE")
    assert (g["type"], g["passed"], g["hold"], g["owner"]) == ("Compliance", False, True, "Compliance")


@pytest.mark.parametrize("gone", ["method", "tool_version", "verification", "operator"])
def test_dv_04_incomplete_certificate_is_no_certificate(gone):
    _post(1, **{gone: None})  # a certificate missing one field
    (c,) = _open(1)
    assert c["gateHold"]["gates"] == ["G-DEV-WIPE"] and all(
        (GR_D1 in r["failReason"] or "(GR-D9)" in r["failReason"]) for r in _sale(c)
    )


def test_dv_04_certificate_clears_the_gate_and_the_page_shows_it():
    seed_wipe(_imei(1))
    (c,) = _open(1)
    assert c["recommendation"] is not None and c.get("gateHold") is None
    assert next(x for x in c["gates"] if x["id"] == "G-DEV-WIPE")["passed"] is True
    d = client.get(f"/api/screens/case/{c['id']}", headers=h("admin")).json()["case"]["device"]["wipe"]
    assert (d["state"], d["certificate"]["method"], d["certificate"]["toolVersion"]) == ("ok", "Purge", "4.2.1")
    assert (d["certificate"]["verification"], d["certificate"]["operator"]) == ("pass", "OP-77")


def test_dv_04_batch_held_and_auto_released():
    cases = _open(1, 2, 3, 4)
    assert all(c["gateHold"]["gates"] == ["G-DEV-WIPE"] and c["gateHold"]["batch"] == BATCH for c in cases)
    page = client.get(f"/api/screens/case/{cases[0]['id']}", headers=h("admin")).json()["case"]["device"]["wipe"]
    assert (page["state"], page["batch"]) == ("none", {"ref": BATCH, "total": 4, "waiting": 4})
    cert = _post(2)
    assert _rechecks() == 1
    one, two, three, four = (_get(c["id"]) for c in cases)
    assert two["gateHold"] is None and two["recommendation"] is not None and two["stage"] == "awaiting_approval"
    assert all(x["gateHold"] is not None and x["stage"] == "none" for x in (one, three, four))  # the others stay held
    with SessionLocal() as s:
        row = s.execute(
            text("SELECT reason, actor FROM case_stage_log WHERE case_id = :c ORDER BY id DESC LIMIT 1"), {"c": two["id"]}
        ).one()
    assert tuple(row) == (f"Released: wipe certificate {cert['certificate_id']} arrived", "system")
    page = client.get(f"/api/screens/case/{one['id']}", headers=h("admin")).json()["case"]["device"]["wipe"]
    assert page["batch"] == {"ref": BATCH, "total": 4, "waiting": 3}


def test_dv_04_failed_verification_adds_step():
    _post(1, verification="fail")
    (c,) = _open(1)
    assert all(r["excluded"] and ("verification" in r["failReason"] or "(GR-D9)" in r["failReason"]) for r in _sale(c))
    assert c["requiredSteps"] == [
        {"gate": "G-DEV-WIPE", "step": "Wipe verification failed: re-run the wipe or destroy the storage", "owner": "Compliance"}
    ]
    assert (c["recommendation"] or {}).get("id") in (None, "recycle")  # a failed wipe may only be recycled (P9-6.15)
    d = client.get(f"/api/screens/case/{c['id']}", headers=h("admin")).json()["case"]["device"]["wipe"]
    assert d["state"] == "failed"


def test_dv_04_failed_then_passing_certificate_releases():
    _post(1, verification="fail")
    (c,) = _open(1)
    _post(1, certificate_id="WC-RERUN")
    assert _rechecks() == 1
    got = _get(c["id"])
    assert got["recommendation"] is not None and "requiredSteps" not in got


def test_dv_04_agents_cannot_release_a_wipe_hold():
    # the gate adds no action: a hold ends only when a certificate lands, and work.resolve stays a person's
    assert forbidden("work.resolve")
