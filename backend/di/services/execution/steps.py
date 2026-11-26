"""The execution steps (the demo's EX_STEP and STEP_TPL, index.html "Execution detail and cost trace").

Each step of an approved decision is an instruction to one enterprise system. Per step kind: its label, the system it
goes to, the document that system returns (prefix and name), the owner, the time limit in working hours (None: it
completes on delivery), the event its acknowledgement emits, and the offset of its planned document number.
"""

import re
from typing import Any

from di.repositories.common import Case, demand_order
from di.services.modeler.pack import close_kinds  # noqa: F401 - re-exported: the pure rule lives with the pack model (P9-13.1)


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
    # plan 9 P9-13.4 (X-16): the credit memo to the customer; a service ticket's upgrade plan also ends on it
    "credit": _s("Customer credit memo", "ERP · billing", ("CM", "Credit memo"), "Finance", 16, "credit.posted", 74,
                 "credit memo posted to the customer", "The ERP posts customer credits; Finance owns the match"),
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
    # plan 9 P9-9.17: the used-car channels' follow-through (the pack's route instructions, UC-18 and UC-25); written to the
    # dealer system (`uc_dms`) and the auction platform (`uc_auction`), or a person's checklist with no system write
    "infotainment_reset": _s("Reset infotainment and remove paired devices", "Lot · checklist", ("CHK", "Checklist"),
                             "Inspection lead", None, "release.confirmed", 0,
                             "infotainment reset and paired devices removed",
                             "The inspection lead resets the car's infotainment before it is released (UC-25)"),
    "recon_order": _s("Reconditioning order", "Dealer system · recon order", ("RO", "Recon order"), "Lot manager", 8,
                      "workorder.created", 13, "recon order accepted by the dealer system",
                      "The lot manager owns the car's reconditioning at the dealer system"),
    "lot_transfer": _s("Transfer to the lot", "Dealer system · lot transfer", ("TR", "Transfer"), "Lot manager", 8,
                       "movement.confirmed", 26, "car transferred to the chosen lot",
                       "The lot manager moves the car to the lot that sells it best"),
    "listing": _s("Retail listing", "Dealer system · listing", ("LST", "Listing"), "Lot manager", 8, "sale.recorded", 39,
                  "listing published with its disclosures", "The lot manager lists the car; the listing carries the disclosures"),
    "consignment": _s("Auction consignment", "Auction platform · consignment", ("CN", "Consignment"), "Remarketing manager", 8,
                      "sale.recorded", 0, "consigned to the next sale with the title reference",
                      "The remarketing manager consigns the car to the wholesale auction"),
    "dealer_trade": _s("Dealer trade", "Dealer system · dealer trade", ("DT", "Dealer trade"), "Remarketing manager", 8,
                       "sale.recorded", 0, "trade booked with the partner dealer",
                       "The remarketing manager books the trade with the highest-bidding partner"),
    "salvage_sale": _s("Salvage sale", "Auction platform · salvage sale", ("SS", "Salvage sale"), "Remarketing manager", 8,
                       "sale.recorded", 0, "sold to a salvage buyer that reports to the national title database",
                       "The remarketing manager sells to a buyer that reports to the national title database"),
    # plan 9 P9-11.17: the follow-through of a medical rental route (the pack's route instructions, MR-19 and MR-23); written to
    # the rental system (`mr_rental`), the biomedical service system (`mr_biomed`) and the disposal partner (`mr_disposal`)
    "dispatch": _s("Dispatch the device", "Rental system · dispatch", ("DSP", "Dispatch"), "Operations manager", 8,
                   "dispatch.confirmed", 0, "device dispatched with its service, certification and decontamination records",
                   "The operations manager sends the device to the hospital with the evidence the hospital asks for"),
    "service_order": _s("Service order", "Biomedical service · service order", ("SVC", "Service order"), "Biomedical engineer", 8,
                        "workorder.created", 13, "service order accepted by the biomedical service system",
                        "The biomedical engineer owns the service the device needs before it is rented again"),
    "biomed_refurb": _s("Refurbishment order", "Biomedical service · refurbishment order", ("SVC", "Service order"),
                       "Clinical engineering", 8, "workorder.created", 26, "refurbishment order accepted by the service system",
                       "Clinical engineering owns the refurbishment of the device"),
    "data_sanitisation": _s("Patient data sanitisation", "Disposal partner · sanitisation", ("SAN", "Sanitisation"),
                            "Fleet manager", 24, "sanitisation.requested", 39,
                            "sanitisation requested; its record releases the collection",
                            "The fleet manager has patient data removed before the device leaves (HIPAA 45 CFR 164.310(d))"),
    "disposal_collection": _s("Collection for disposal", "Disposal partner · collection", ("COL", "Collection"), "Fleet manager",
                              24, "collection.confirmed", 13, "collected by the disposal partner",
                              "The disposal partner collects the device once its sanitisation record is on file"),
    # plan 9 P9-6.12: a received device on a listing channel is listed on the device market (di.services.device.settle)
    "list": _s("List on the channel", "Marketplace · listing", ("LST", "Listing"), "Channel ops", 8, "listing.posted", 21,
               "listing live on the channel", "Channel ops owns what is offered for sale and at what price"),
    # plan 9 P9-10.16: the telecom pack's follow-through (inventory, test bench, broker marketplace, recycler portal)
    "firmware_upgrade": _s("Firmware upgrade", "Test bench · firmware", ("RF", "Refurb order"), "Test bench lead", 8,
                           "workorder.created", 13, "firmware upgrade ordered at the bench",
                           "The test bench lead upgrades the unit to the demand's firmware"),
    "site_transfer": _s("Transfer to the site", "Network inventory · transfer order", ("TO", "Transfer order"),
                        "Network asset manager", 8, "movement.confirmed", 26, "transfer order created in the network inventory",
                        "The network asset manager moves the unit to the site that needs it"),
    "spares_transfer": _s("Transfer to the spares pool", "Network inventory · transfer order", ("TO", "Transfer order"),
                          "Spares planner", 8, "movement.confirmed", 26, "unit transferred to its region's spares pool",
                          "The spares planner holds the unit in its region's pool"),
    "refurb_order": _s("Refurbishment order", "Test bench · refurb order", ("RF", "Refurb order"), "Spares planner", 8,
                       "workorder.created", 13, "refurb order accepted by the test bench",
                       "The spares planner has the unit refurbished at the bench"),
    "broker_listing": _s("Broker listing", "Broker marketplace · listing", ("LS", "Listing"), "Network asset manager", 8,
                         "sale.recorded", 39, "unit listed against the highest bid",
                         "The network asset manager lists the unit on the highest bid"),
    "recycler_pickup": _s("Recycler pickup", "Recycler portal · pickup", ("PU", "Pickup"), "Sustainability lead", 24,
                          "collection.confirmed", 13, "pickup scheduled with the certified recycler",
                          "The sustainability lead sends the unit to a recycler whose certificate is valid"),
    # plan 9 P9-13.1 (X-13): the close of a pack that owns the asset; the ERP stays the book of record for fixed assets
    "retire": _s("Fixed-asset retirement", "ERP · fixed assets", ("FA", "Asset document"), "Finance", 16, "asset.retired", 70,
                 "asset retired with its proceeds; gain or loss posted",
                 "The ERP stays the book of record for fixed assets; Finance owns the retirement"),
    "transfer": _s("Asset transfer", "ERP · fixed assets", ("FA", "Asset document"), "Finance", 16, "asset.transferred", 72,
                   "asset transferred to its new site; posted in the ERP",
                   "The ERP stays the book of record for fixed assets; Finance owns the transfer"),
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
    # plan 9 P9-6.15, a received device's routes beyond the sale channels: repaired, then listed and sold; torn down into parts;
    # recycled through a certified recycler (the certificate closes the custody chain). No new step kind.
    "repair_sell": ["repair", "reserve", "list", "ship", "fulfil", "receipt"],
    "parts": ["teardown", "partsput", "partsxfer", "finance"],
    "recycle": ["release", "collect", "process", "cert"],
    # plan 9 P9-6.16: a received device kept as replacement stock for an open demand (the unit is reserved at approval)
    "replacement": ["reserve", "move", "finance"],
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
    "telecom_network": {"teardown": "Test bench · teardown"},  # P9-10.16
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
    if r.get("steps"):  # a route that names its own steps (the used-car channels, P9-9.17)
        return [str(k) for k in r["steps"]]
    if r.get("kinds"):  # a service ticket's split: the union of its lines' kinds, each once (P9-4.9)
        return list(r["kinds"])
    k = list(STEP_TPL.get(r.get("id") or "resale") or STEP_TPL["resale"])
    if r.get("id") == "resale" and r.get("variant") == "refurb":
        k.insert(1, "repair")
    k += [x for x in r.get("close_steps") or [] if x not in k]  # P9-13.4: a pack's close steps after the route's own (decide.py)
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
