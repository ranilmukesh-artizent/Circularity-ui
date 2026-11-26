"""The telecom network pack's follow-through writes (plan 9, P9-10.16, stories TN-19, TN-23, TN-24; registry entries I-6, I-11).

An approved route's steps (the pack route's `instructions`, or the valuer's `dest.steps`) go to the executing system, in order:

    site_transfer      network inventory (tn_inv)     POST /transfer-orders {serial, toSite}: redeploy to the demand's site
    spares_transfer    network inventory (tn_inv)     POST /transfer-orders {serial, toPool}: the unit joins its region's pool
    refurb_order       test bench (tn_bench)          POST /refurb-orders {serial, kind: refurbish}
    bench_teardown     test bench (tn_bench)          POST /teardowns {serial}: the harvest route's `teardown` (`write_kind`)
    broker_listing     broker marketplace (tn_broker) POST /listings {serials, unitPrice, bidId}: the highest bid on file
    recycler_pickup    recycler portal (tn_recycler)  POST /pickups {serials, vendorId, weeeCategory, weightKg}

Each reply is the executing system's confirmation: `detail.confirmed` lets the send acknowledge the step, and the instruction
keeps the document (`orderId`, `listingId`, `pickupId`, the recycler's certificate reference), so the inventory's transfer
confirmation is stored with the case's instructions. Every write is idempotent in the system, so a resend answers the first
document. A recycler whose certificate lapsed is refused by the portal and by the gate G-DS-1; a pickup without WEEE category
and weight is refused here and (EU sites) by G-WEEE-2.

Never does: pick a route, approve, clear a gate, or invent a weight or a category (they come from the case's `downstream`
record). Legal note: the WEEE and recycler-certification rules rest on research summaries; Kinective's Legal team reviews them
before they are relied on.
"""

from typing import Any

from sqlalchemy.orm import Session

from di.connectors.http import SourceError
from di.services.cases import store
from di.services.instructions import writers
from di.services.instructions.writers import NotApplicable, Refused, Sent, _refused


def _serial(c: store.Case) -> str:
    serial = str(c.get("serial") or c.get("assetId") or "").rpartition(":")[2]
    if not serial:
        raise NotApplicable("no unit serial to write for")
    return serial


def _dest(c: store.Case) -> dict[str, Any]:
    return dict((c.get("chosen") or c.get("recommendation") or {}).get("dest") or {})


def _post(s: Session, source: str, path: str, body: dict[str, Any], id_field: str, extra: dict[str, Any] | None = None) -> Sent:
    cl = writers.client(s, source)
    try:
        doc = cl.request("POST", path, json=body).json()
    except SourceError as e:
        raise _refused(e) from e
    finally:
        cl.close()
    ref = str(doc.get(id_field) or "")
    return Sent(
        [{"call": f"POST {path.lstrip('/')}", "body": body}], ref or None,
        {"confirmed": bool(ref), id_field: ref, **(extra or {})},
    )  # fmt: skip


def site_transfer(s: Session, ins: dict, c: store.Case, prev: dict) -> Sent:  # noqa: ARG001 - every writer takes (session, instruction, case, previous)
    site = _dest(c).get("site")
    if not site:
        raise Refused("The route names no site to transfer the unit to")
    serial = _serial(c)
    return _post(
        s, "tn_inv", "/transfer-orders", {"serial": serial, "toSite": site}, "orderId", {"serial": serial, "toSite": site}
    )


def spares_transfer(s: Session, ins: dict, c: store.Case, prev: dict) -> Sent:  # noqa: ARG001 - every writer takes (session, instruction, case, previous)
    pool = _dest(c).get("region")
    if not pool:
        raise Refused("The route names no spares pool to transfer the unit to")
    serial = _serial(c)
    return _post(
        s, "tn_inv", "/transfer-orders", {"serial": serial, "toPool": pool}, "orderId", {"serial": serial, "toPool": pool}
    )


def refurb_order(s: Session, ins: dict, c: store.Case, prev: dict) -> Sent:  # noqa: ARG001 - every writer takes (session, instruction, case, previous)
    serial = _serial(c)
    return _post(s, "tn_bench", "/refurb-orders", {"serial": serial, "kind": "refurbish"}, "orderId", {"serial": serial})


def bench_teardown(s: Session, ins: dict, c: store.Case, prev: dict) -> Sent:  # noqa: ARG001 - every writer takes (session, instruction, case, previous)
    serial = _serial(c)
    return _post(s, "tn_bench", "/teardowns", {"serial": serial}, "teardownId", {"serial": serial})


def broker_listing(s: Session, ins: dict, c: store.Case, prev: dict) -> Sent:  # noqa: ARG001 - every writer takes (session, instruction, case, previous)
    """The highest bid on file for the unit's model, read from the marketplace; no bid, no listing."""
    serial, model = _serial(c), str((c.get("network") or {}).get("model") or "")
    cl = writers.client(s, "tn_broker")
    try:
        bids = cl.get_json("/bids", params={"model": model} if model else None)
    except SourceError as e:
        raise _refused(e) from e
    finally:
        cl.close()
    rows = [b for b in (bids if isinstance(bids, list) else []) if isinstance(b, dict) and b.get("unitPrice")]
    best = max(rows, key=lambda b: (b["unitPrice"], str(b.get("bidId"))), default=None)
    if best is None:
        raise Refused("The broker marketplace holds no bid for the unit's model")
    body = {"serials": [serial], "unitPrice": best["unitPrice"], "bidId": best["bidId"]}
    return _post(s, "tn_broker", "/listings", body, "listingId", {"serial": serial, "bidId": best["bidId"]})


def recycler_pickup(s: Session, ins: dict, c: store.Case, prev: dict) -> Sent:  # noqa: ARG001 - every writer takes (session, instruction, case, previous)
    """The pickup by the recycler the case names (`downstream.vendor_id`), with the WEEE category and weight."""
    serial, d = _serial(c), c.get("downstream") or {}
    vendor = d.get("vendor_id") or _dest(c).get("vendor")
    if not vendor:
        raise Refused("The route names no recycler")
    category, weight = d.get("weee_category"), d.get("weight_kg")
    if not category or not isinstance(weight, int | float) or isinstance(weight, bool) or weight <= 0:
        raise Refused("WEEE category and weight are required for the pickup")
    body = {"serials": [serial], "vendorId": vendor, "weeeCategory": category, "weightKg": weight}
    ref = (d.get("certificate") or {}).get("ref")
    return _post(s, "tn_recycler", "/pickups", body, "pickupId", {"serial": serial, "vendorId": vendor, "certificateRef": ref})
