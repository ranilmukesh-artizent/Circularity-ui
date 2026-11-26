"""Plan 9, P9-6.6 (story DV-03): the blacklist and lock gate for a received device (G-DEV-LOCK, guardrail GR-D7).

A registry hit (blacklist, activation lock, a balance owed) fails every channel with the GR-D7 text and opens one
`blacklist_hit` item for the Approver role (owner label "Compliance") with the registry evidence. Only a person releases it,
and only with a registry check newer than the hit. No check, or one older than `recheck_days` (7), holds the case for a new
one. A shortcut that skips the check is refused by the customer overlay (I-4). Nothing here writes language: no model call.
"""

from datetime import timedelta

import pytest
from sqlalchemy import text

from di.connectors.adapters import device_lab as lab
from di.core import clock
from di.core.db import SessionLocal, engine
from di.services.agents.forbidden import forbidden
from di.services.cases import store
from di.services.device import intake as device_intake
from di.services.modeler.overlay import OverlayError, Shortcut, apply_overlay
from di.services.modeler.pack import load_pack
from tests import starting
from tests.device_registry import seed_registry, seed_wipe
from tests.helpers import call, client, h

ORG = "Customer A"
IMEI = "359990000000428"


def _clean() -> None:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM provenance WHERE source_id IN ('dvlab', 'dvreg') AND key LIKE 'IMEI:%'"))
        conn.execute(text("DELETE FROM canonical WHERE model IN ('condition', 'asset') AND key LIKE 'IMEI:%'"))
        conn.execute(text("DELETE FROM device_tradein"))
        conn.execute(text("DELETE FROM device_price_point"))


@pytest.fixture(autouse=True)
def fresh():
    starting.reset()
    _clean()
    yield
    starting.reset()
    _clean()


def _open() -> dict:
    when = (clock.now() - timedelta(days=5)).isoformat()
    doc = {
        "tradeInId": "TI-00428", "imei": IMEI,
        "sku": {"brand": "Apple", "model": "iPhone 14", "storageGb": 128, "colour": "Blue", "carrierLock": "unlocked"},
        "quote": {"declaredGrade": "B", "amount": 410, "currency": "USD", "quotedAt": when},
        "partner": "P01", "batchId": "BATCH-0011", "bulk": False, "receivedAt": when, "payoutAmount": 410,
    }  # fmt: skip
    with SessionLocal() as s:
        lab.land_tradein(s, doc, ORG)
        (cid,) = device_intake.open_pending(s, ORG)
        s.commit()
        c = store.get(s, cid)
    assert c is not None
    return c


def _get(cid: str) -> dict:
    with SessionLocal() as s:
        c = store.get(s, cid)
    assert c is not None
    return c


def _items(cid: str, type: str = "blacklist_hit") -> list[dict]:
    with SessionLocal() as s:
        rows = s.execute(
            text(
                "SELECT id, status, owner_role, title, cause, action FROM work_item WHERE case_id = :c AND type = :t ORDER BY id"
            ),
            {"c": cid, "t": type},
        ).mappings().all()  # fmt: skip
    return [dict(r) for r in rows]


def _blocked(c: dict) -> list[dict]:
    """The routes a hit blocks: every one but the gate's locked routes, parts and recycle (P9-6.15); repair then sell, with no
    quote, carries the valuer's own reason."""
    return [r for r in c["routes"] if r["id"] not in ("parts", "recycle", "repair_sell")]


def test_dv_03_blacklist_blocks_sale_channels():
    at = seed_registry(IMEI, blacklist="reported_stolen")
    c = _open()
    day = at[:10]
    assert c["routes"] and all(
        r["excluded"] and f"Blacklist or lock check hit (GR-D7): reported stolen, checked {day}" in r["failReason"]
        for r in _blocked(c)
    )
    # only the locked routes stay open ("as law allows", P9-6.15); the case is recommended one of them
    assert {r["id"] for r in c["routes"] if not r["excluded"]} == {"parts", "recycle"}
    assert c["recommendation"]["id"] in ("parts", "recycle")
    lock = next(g for g in c["gates"] if g["id"] == "G-DEV-LOCK")
    assert (lock["type"], lock["passed"], lock["owner"]) == ("Compliance", False, "Compliance")


@pytest.mark.parametrize(
    ("over", "said"), [({"lock": "on"}, "activation lock on"), ({"finance": "balance_owed"}, "balance owed")]
)
def test_dv_03_lock_and_balance_owed_are_hits(over, said):
    seed_registry(IMEI, **over)
    c = _open()
    assert all(r["excluded"] and said in r["failReason"] for r in _blocked(c))


def test_dv_03_waits_for_compliance_with_evidence():
    seed_registry(IMEI, blacklist="reported_stolen")
    c = _open()
    (item,) = _items(c["id"])
    assert item["status"] == "open" and item["owner_role"] == "Approver"
    assert "Compliance" in item["action"] and "reports reported stolen" in item["cause"] and "checked" in item["cause"]
    assert "blacklist reported_stolen" in item["cause"]
    # an agent may never resolve it (R21); a person of another role may not either
    assert forbidden("work.resolve")
    refused = call("work.resolve", {"item_id": item["id"], "outcome": "Released"}, "planner.a")
    assert refused.get("ok") is False or refused.get("error"), refused
    assert _items(c["id"])[0]["status"] == "open"
    r = client.get(f"/api/screens/case/{c['id']}", headers=h("admin"))
    reg = r.json()["case"]["device"]["registry"]
    assert (reg["state"], reg["owner"], reg["item"], reg["allowedRoutes"]) == ("hit", "Compliance", "open", ["parts", "recycle"])


def test_dv_03_release_needs_a_newer_registry_check():
    seed_registry(IMEI, blacklist="reported_stolen", days_ago=2)
    c = _open()
    (item,) = _items(c["id"])
    no = call("work.resolve", {"item_id": item["id"], "outcome": "Released"}, "approver")
    assert "newer" in str(no), no  # the same hit is not a newer check
    assert _items(c["id"])[0]["status"] == "open"
    seed_registry(IMEI, days_ago=0.5)  # a later check: clear
    ok = call("work.resolve", {"item_id": item["id"], "outcome": "Released on the new check"}, "approver")
    assert ok.get("ok") is not False, ok
    got = _get(c["id"])
    assert any(not r["excluded"] for r in got["routes"]) and got["stage"] == "awaiting_approval"
    assert _items(c["id"])[0]["status"] == "done" and len(_items(c["id"])) == 1


def test_dv_03_skip_diversion_refused():
    op = Shortcut(
        id="op-1", op="shortcut", stage="receive", when=[{"fact": "quote.amount", "op": "lte", "value": 49}], to="condition"
    )
    with pytest.raises(OverlayError) as e:
        apply_overlay(load_pack("device"), [op])
    assert e.value.code == "skips_compliance" and e.value.guardrail == "GR-D7"
    assert "Blacklist" in str(e.value) or "blacklist" in str(e.value)
    sample = next(d for d in load_pack("device").customer_layer.sample_diversions if "blacklist" in d.text.lower())
    assert sample.blocked is True and "GR-D7" in sample.reason


def test_dv_03_stale_check_waits():
    seed_registry(IMEI, days_ago=9)
    c = _open()
    assert c["recommendation"] is None and c["gateHold"]["gates"] == ["G-DEV-LOCK"]
    assert all(r["excluded"] and "Evidence stale" in r["failReason"] for r in c["routes"] if r["id"] != "repair_sell")
    assert _items(c["id"]) == []  # a stale check is not a hit
    assert len(_items(c["id"], "evidence_missing")) == 1


def test_dv_03_no_check_waits_and_a_fresh_one_releases():
    seed_wipe(IMEI)  # the wipe gate (P9-6.7) has its certificate; only the registry check is missing
    c = _open()
    assert c["gateHold"] is not None
    assert all("No registry check on file" in r["failReason"] for r in c["routes"] if r["id"] != "repair_sell")
    seed_registry(IMEI, days_ago=1)
    from di.services.cases import gate_hold

    with SessionLocal() as s:
        released = gate_hold.recheck(s, f"IMEI:{IMEI}")
        s.commit()
    assert released == [c["id"]] and _get(c["id"])["recommendation"] is not None


def test_dv_03_clear_fresh_check_passes():
    seed_registry(IMEI, days_ago=6)
    c = _open()
    assert c["recommendation"] is not None and _items(c["id"]) == []
    assert next(g for g in c["gates"] if g["id"] == "G-DEV-LOCK")["passed"] is True
