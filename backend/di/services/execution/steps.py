"""The execution steps (the demo's EX_STEP and STEP_TPL, index.html "Execution detail and cost trace").

Each step of an approved decision is an instruction to one enterprise system. Per step kind: its label, the system it
goes to, the document that system returns (prefix and name), the owner, the time limit in working hours (None: it
completes on delivery), the event its acknowledgement emits, and the offset of its planned document number.
"""

import re
from typing import Any

from di.repositories.common import Case, demand_order


def _s(label, sys, doc, owner, lim, ev, off, note, why) -> dict[str, Any]:
    return {"label": label, "sys": sys, "doc": doc, "owner": owner, "lim": lim, "ev": ev, "off": off, "note": note, "why": why}


EX_STEP: dict[str, dict[str, Any]] = {
    "order": _s("Allocate to the order line", "OMS · order allocation", ("SO", "Sales order"),
                "Customer operations · order desk", 4,
                "order.allocated", 0, "unit allocated to the order line; planned purchase cancelled in SAP Ariba",
                "The order desk owns order lines in OMS"),
    "repair": _s("Refurbishment work order", "MRO · Depot repair", ("WO", "Work order"), "Repair centre lead (Engineer)", 4,
                 "workorder.created", 13, "repaired, tested and certified; QMS record updated",
                 "The Repair centre lead plans the repair order and its operations in Oracle Depot Repair"),
    "transport": _s("Book transport", "TMS · load booking", ("LD", "Load"), "Transport planner", 4, "load.booked", 52,
                    "load tendered to and accepted by the carrier",
                    "The Transport planner books loads on contracted lanes in Oracle Transportation Management"),
    "move": _s("Warehouse moves and outbound delivery", "WMS · transfer", ("TR", "Transfer"), "Warehouse Manager", 2,
               "movement.confirmed", 26, "picked, staged and shipped against the load",
               "The Warehouse Manager of the shipping warehouse confirms picks, staging and dispatch"),
    "pod": _s("Delivery confirmed", "OMS · order fulfilled", ("FUL", "Fulfilment"), "Customer operations", None,
              "delivery.confirmed", 39, "proof of delivery signed at the site; order line fulfilled",
              "Customer operations closes the order line on proof of delivery"),
    "finance": _s("Actual costs posted", "ERP · finance", ("FI", "Finance document"), "Finance", 16, "outcome.reported", 65,
                  "actual parts, labour, machine and freight costs posted against the decision",
                  "SAP S/4HANA stays the book of record for actual cost (K1); Finance confirms the outcome"),
    "reserve": _s("Reserve unit", "WMS · reservation", ("RSV", "Reservation"), "Warehouse Manager", 2, "stock.reserved", 6,
                  "unit reserved for the sale", "The holding warehouse reserves the unit so it is not picked for anything else"),
    "sale": _s("Sale order", "OMS · sale order", ("SO", "Sales order"), "Sales operations", 8, "sale.recorded", 0,
               "buyer confirmed; sale order created", "Sales operations records the buyer and price in OMS"),
    "ship": _s("Book shipment to the buyer", "TMS · load booking", ("LD", "Load"), "Transport planner", 4, "load.booked", 52,
               "load booked to the buyer", "Freight goes on the contracted lane rate card"),
    "fulfil": _s("Shipped and invoiced", "OMS · order fulfilled", ("FUL", "Fulfilment"), "Customer operations", None,
                 "delivery.confirmed", 39, "delivered and invoiced", "OMS closes the sale order on delivery"),
    "receipt": _s("Outcome reported", "ERP · receipts", ("INV", "Invoice"), "Finance", 16, "outcome.reported", 65,
                  "receipts posted", "Receipts post in SAP S/4HANA"),
    "putaway": _s("Putaway after refurbishment", "WMS · putaway", ("PA", "Putaway"), "Warehouse Manager", 2,
                  "movement.confirmed", 26, "refurbished unit put away",
                  "The receiving warehouse puts the unit away until the lease starts"),
    "lease": _s("Lease contract", "Lease · contract", ("LS", "Lease contract"), "Lease administration", 16, "contract.signed", 39,
                "lease contract signed", "Lease administration issues the contract in Oracle Lease"),
    "teardown": _s("Teardown work order", "MRO · Depot repair", ("WO", "Work order"), "Repair centre lead (Engineer)", 4,
                   "workorder.created", 13, "teardown done; recovered parts tested and certified",
                   "Teardown and part testing run as a repair order in Oracle Depot Repair"),
    "partsput": _s("Parts putaway", "WMS · putaway", ("PA", "Putaway"), "Warehouse Manager", 2, "movement.confirmed", 26,
                   "recovered parts put away", "Recovered parts go into service stock"),
    "partsxfer": _s("Parts allocation", "ERP · stock transfer", ("TR", "Transfer"), "Materials planner", 8,
                    "stock.transferred", 39,
                    "parts allocated to open service orders", "The Materials planner allocates stock to service orders"),
    "resparts": _s("Reserve parts", "WMS · reservation", ("RSV", "Reservation"), "Warehouse Manager", 2, "stock.reserved", 26,
                   "parts reserved", "Parts are held for the buyer"),
    "saletask": _s("Sale task", "CRM · sale task", ("SO", "Sales order"), "Sales operations", 8, "sale.recorded", 39,
                   "buyer confirmed; sale recorded", "Parts sales are worked as CRM tasks"),
    "release": _s("Release to partner", "WMS · release", ("REL", "Release"), "Warehouse Manager", 2, "release.confirmed", 0,
                  "released to the partner", "The warehouse releases the unit to the approved partner"),
    "collect": _s("Collection", "Recycler / Exit partner", ("COL", "Collection"), "Exit partner", 24, "collection.confirmed", 13,
                  "collected by the partner", "The partner collects on its own vehicle"),
    "process": _s("Processing", "Recycler / Exit partner", ("COL", "Collection"), "Exit partner", 40, "processing.confirmed", 26,
                  "processed by the partner", "The partner processes under its certificate"),
    "cert": _s("Certificate returned", "Recycler · certificate", ("CERT", "Certificate"), "Exit partner", 40,
               "certificate.received", 39, "certificate returned", "The certificate closes the custody chain"),
    "custody": _s("Custody certificate returned", "Exit partner", ("CERT", "Certificate"), "Exit partner", 40,
                  "certificate.received", 39, "custody certificate returned", "The certificate closes the custody chain"),
    "holdput": _s("Return to stock", "WMS · inventory putaway", ("PA", "Putaway"), "Warehouse Manager", 2,
                  "movement.confirmed", 0,
                  "returned to stock", "The unit waits in stock until the review"),
    "holdrev": _s("Hold until review", "Planning", ("REF", "Reference"), "Planner", 16, "hold.recorded", 13, "hold recorded",
                  "The Planner owns the review date"),
    "reeval": _s("Re-evaluate", "Circularity", ("REF", "Reference"), "Planner", 16, "case.reevaluated", 26, "re-evaluated",
                 "Circularity re-runs the routes on fresh evidence"),
    "holdout": _s("Outcome reported", "ERP · finance", ("INV", "Invoice"), "Finance", 16, "outcome.reported", 65,
                  "outcome posted",
                  "Receipts post in SAP S/4HANA"),
    # plan 9 P9-4.9: a service ticket's old tool comes back (the Returns case opens on its acknowledgement), then the credit goes
    "takeback": _s("Take back the old tool", "WMS · inbound receipt", ("RCV", "Receipt"), "Fleet desk", 48, "tool.received", 33,
                   "old tool received; a Returns case opened for it", "The Fleet desk receives the tool the customer returns"),
    "credit": _s("Release the credit", "ERP · credit memo", ("CM", "Credit memo"), "Finance", 16, "credit.released", 71,
                 "credit memo released to the customer", "Finance releases the credit once the old tool is received"),
    # plan 9 P9-5.5: an approved contract refresh is sent, its lines drafted and its units held (the systems answer
    # with the proposal, the draft lines and the reservation; PR-, DL- and RU- are their planned numbers, which the mocks keep)
    "propsend": _s("Send the proposal", "Fleet contract system · proposal", ("PR", "Proposal"), "Fleet desk", 8,
                   "proposal.sent", 8,
                   "proposal sent to the customer", "The Fleet desk owns what the customer is offered"),
    "propdraft": _s("Draft the contract lines", "Fleet contract system · draft lines", ("DL", "Contract lines"), "Fleet desk", 8,
                    "contract.drafted", 21, "contract lines drafted for the renewal",
                    "The lines are drafted in the fleet contract system, ready for the customer's answer"),
    "propreserve": _s("Reserve the units", "Parts and service system · reserve units", ("RU", "Reservation"), "Fleet desk", 8,
                      "stock.reserved", 34, "refurbished units reserved for the swaps",
                      "The units promised in the proposal are held so no other contract takes them"),
    # plan 9 P9-6.8: the payout of a received device; sent on its own (di.services.device.payout), never a step of a plan
    "payout": _s("Payout adjusted", "Trade-in platform · payout", ("TI", "Trade-in"), "Customer care", None, "payout.adjusted", 0,
                 "payout adjusted on the trade-in", "Customer care owns the payout the customer is paid"),
    # plan 9 P9-6.12: a received device on a listing channel is listed on the device market (di.services.device.settle)
    "list": _s("List on the channel", "Marketplace · listing", ("LST", "Listing"), "Channel ops", 8, "listing.posted", 21,
               "listing live on the channel", "Channel ops owns what is offered for sale and at what price"),
}  # fmt: skip

# The step plan per route; a refurbish-then-sell resale gets a repair step after the reservation. A step's identity is
# its kind, never its position.
STEP_TPL: dict[str, list[str]] = {
    "redeploy": ["order", "repair", "transport", "move", "pod", "finance"],
    "resale": ["reserve", "sale", "ship", "fulfil", "receipt"],
    "relase": ["repair", "transport", "putaway", "lease", "finance"],
    "intparts": ["teardown", "partsput", "partsxfer", "finance"],
    "extparts": ["teardown", "resparts", "saletask", "receipt"],
    "material": ["release", "collect", "process", "cert"],
    "exit": ["release", "collect", "process", "custody"],
    "hold": ["holdput", "holdrev", "reeval", "holdout"],
    # template paths (plan 8; audit: they fell back to the resale plan). Tool fleet: re-issue to a fleet contract is a
    # re-lease; refurbish → place repairs then puts away for the named order; pre-owned sale is a sale; harvest is a
    # teardown into service stock; recycle (`exit`) and tool pool (`redeploy`) share the industrial ids.
    "release": ["repair", "transport", "putaway", "lease", "finance"],
    "refurb": ["repair", "transport", "putaway", "finance"],
    "resell": ["reserve", "sale", "ship", "fulfil", "receipt"],
    "harvest": ["teardown", "partsput", "partsxfer", "finance"],
    # device recommerce channels: each is a sale of the lot
    "buynow": ["reserve", "sale", "ship", "fulfil", "receipt"],
    "offers": ["reserve", "sale", "ship", "fulfil", "receipt"],
    "auction": ["reserve", "sale", "ship", "fulfil", "receipt"],
    "market": ["reserve", "sale", "ship", "fulfil", "receipt"],
    "wholesale": ["reserve", "sale", "ship", "fulfil", "receipt"],  # plan 9 P9-6.11: a lot sold to the best approved bid
    # a service ticket's options (P9-4.9; the valuer's OPTION_KINDS says the same, tests/test_service_desk_execute.py): a batch's
    # `split` has no plan of its own, the route carries the union of its lines' kinds (`kinds`, below)
    "fix": ["repair", "transport", "finance"],
    "swap": ["reserve", "transport", "takeback", "finance"],
    "upgrade": ["sale", "transport", "takeback", "credit", "finance"],
    "all_fix": ["repair", "transport", "finance"],
    "all_upgrade": ["sale", "transport", "takeback", "credit", "finance"],
    # a contract refresh's routes (P9-5.4, P9-5.5): the proposal goes out, its lines are drafted, the swaps' units are held;
    # renewing as it is has no swap to hold
    "proposal": ["propsend", "propdraft", "propreserve"],
    "renew_as_is": ["propsend", "propdraft"],
    "upgrade_all": ["propsend", "propdraft", "propreserve"],
}
# plan 9 P9-3.17: the executing system of a step per template (the other steps keep EX_STEP's). A tool-fleet re-issue goes to the
# fleet contract system and a harvest to the parts system; an industrial case never reads this
TEMPLATE_SYS: dict[str, dict[str, str]] = {
    "tool_fleet": {"lease": "Fleet contract system · re-issue", "partsxfer": "Parts and service system · issue parts"},
}
# The demo's ACK_NOTE: notes for steps without a kind (none are created any more; kept for stored plans)
ACK_NOTE = {
    "Refurbishment work order": "repaired, tested and certified; QMS record updated",
    "Teardown work order": "teardown done; recovered parts tested and certified",
    "Sale task": "buyer confirmed; sale recorded",
    "Putaway after refurbishment": "refurbished unit put away",
    "Lease contract": "lease contract signed",
    "Parts putaway": "recovered parts put away",
    "Reserve parts": "parts reserved",
    "Collection": "collected by the partner",
    "Processing": "processed by the partner",
    "Hold until review": "hold recorded",
}


def ex_kinds(r: dict) -> list[str]:
    """The demo's exKinds: the step kinds for a route."""
    if r.get("kinds"):  # a service ticket's split: the union of its lines' kinds, each once (P9-4.9)
        return list(r["kinds"])
    k = list(STEP_TPL.get(r.get("id") or "resale") or STEP_TPL["resale"])
    if r.get("id") == "resale" and r.get("variant") == "refurb":
        k.insert(1, "repair")
    if r.get("variant") == "listing":  # plan 9 P9-6.12: a received device on a channel is listed, not entered as a sale order
        k = ["list" if x == "sale" else x for x in k]
    return k


def steps_for(r: dict, done: int = 0, template: str | None = None) -> list[dict]:
    """The demo's stepsFor(r, done): steps before `done` are done, `done` is active (-1: every step still to do). A template
    with its own executing systems (`TEMPLATE_SYS`) names them on its steps."""
    sys_of = TEMPLATE_SYS.get(template or "") or {}
    lines, to = r.get("stepLines") or {}, r.get("shipTo")  # a service ticket: the lines each step covers, the site (P9-4.9)
    return [
        {
            "k": k,
            "label": EX_STEP[k]["label"],
            "sys": sys_of.get(k) or EX_STEP[k]["sys"],
            "state": "done" if i < done else "active" if i == done else "todo",
            "ack": None,
            **({"lines": list(lines[k])} if k in lines else {}),
            **({"to": to} if to and k == "transport" else {}),
        }
        for i, k in enumerate(ex_kinds(r))
    ]


def approval_ref(case_id: str) -> str:
    """The demo's approvalRef."""
    return f"APR-2026-10-{int(case_id[3:]) * 3 + 17:04d}"


def ex_ev(s: dict) -> str:
    """The demo's exEv: the event a step's acknowledgement emits."""
    d = EX_STEP.get(s["k"])
    return d["ev"] if d else "outcome.reported"


def ex_doc_num(c: Case, k: str) -> int:
    """The demo's exDocNum: the planned document number, shown before acknowledgement; the acknowledgement confirms it."""
    d = EX_STEP.get(k)
    return 40000 + int(c["id"][3:]) * 7 + (d["off"] if d else 0) + (c.get("cycle") or 0) * 101


def ex_doc_ref(c: Case, s: dict) -> str:
    """The demo's exDocRef: the document a step creates. An order allocation is made against the matched sales order."""
    if s["k"] == "order":
        return demand_order(c) or f"SO-{ex_doc_num(c, 'order')}"
    d = EX_STEP.get(s["k"])
    return f"{d['doc'][0] if d else 'REF'}-{ex_doc_num(c, s['k'])}"


def ho_kind(s: dict) -> tuple[str, str]:
    """The demo's hoKind: the document type a system returns for a step (by kind; the label and system rules are for
    steps stored without a kind)."""
    d = EX_STEP.get(s.get("k", ""))
    if d:
        return d["doc"]
    y, lbl = s["sys"], s["label"]
    if re.search("Outcome reported", lbl):
        return ("FUL", "Fulfilment") if re.search("fulfilled|EAM", y) else ("INV", "Invoice")
    rules = [
        ("Order Management|CRM · sale", ("SO", "Sales order")), ("^EAM", ("WO", "Work order")),
        ("Lease · contract", ("LS", "Lease contract")), ("transfer", ("TR", "Transfer")), ("reservation", ("RSV", "Reservation")),
        ("shipment", ("SHP", "Shipment")), ("putaway", ("PA", "Putaway")), ("release", ("REL", "Release")),
    ]  # fmt: skip
    for pat, kind in rules:
        if re.search(pat, y):
            return kind
    if re.search("certificate", lbl, re.I):
        return "CERT", "Certificate"
    if re.search("Recycler|Exit partner", y):
        return "COL", "Collection"
    return "REF", "Reference"


def ack_ref(c: Case, s: dict, num: int) -> str:
    """The demo's ackRef: the reference a system returns when it acknowledges a step (the planned document number)."""
    if s.get("k"):
        return ex_doc_ref(c, s)
    k = ho_kind(s)[0]
    o = demand_order(c) if k == "SO" and re.search("Order Management", s["sys"]) else None
    return o or f"{k}-{num}"


def ref_label(s: dict) -> str:
    """The demo's refLabel: "Sales order SO-48102"."""
    return f"{ho_kind(s)[1]} {s['ack']['ref']}"
