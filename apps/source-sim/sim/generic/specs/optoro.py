"""Optoro (the demo's SOURCES.rl): return receipts, disposition decisions, inbound shipments, carrier status.
Read: GET /returns, /dispositions, /shipments. Write: POST /return-authorizations.

One return per case. Authorisation, pickup, carrier, arrival and freight are the demo's afLease values (the same
numbers ShipLane's inbound load holds); the RMA is asRMA. Optoro's API speaks upper-case field names and reports
times in the returns centre's local time (US Eastern, -04:00), which is what the demo's MAPPINGS.rl normalises.
"""

from datetime import datetime, timedelta, timezone

from sim.generic.spec import Auth, Paging, Resource, Spec
from sim.generic.specs.manhattan import facility_id
from sim.generic.specs.shiplane import (
    FAC_LOC,
    LOCS,
    SCAC,
    as_hex,
    case_no,
    demand_order,
    load_id,
    return_logistics,
)
from sim.seed import Seed
from sim.seed.model import CaseFacts

EDT = timezone(timedelta(hours=-4))


def local(d: datetime) -> str:
    return d.astimezone(EDT).isoformat(timespec="seconds")


def received_at(f: CaseFacts) -> datetime:
    """The receipt scan: the received date, 12:00-19:59 UTC, so the local (-04:00) date is the same day."""
    return f.received + timedelta(minutes=720 + as_hex(f.id, "|rl|rcv") % 480)


# grade -> Optoro disposition. No grade yet: the unit waits for inspection.
DISPOSITION = {"A": "RESTOCK", "B": "RESTOCK", "C": "REFURB", "D": "RECYCLE", None: "PENDING_INSPECTION"}
DISPOSITION_REASON = {
    "RESTOCK": "Grade {g}: sellable as is",
    "REFURB": "Grade {g}: refurbishment lifts the grade",
    "RECYCLE": "Grade {g}: below resale threshold",
    "PENDING_INSPECTION": "Awaiting inspection; disposition held",
}


def return_id(f: CaseFacts) -> str:
    return f"OPT-R-{case_no(f.id)}"


def seed(s: Seed) -> dict[str, list[dict]]:
    returns, dispositions, shipments, ras = [], [], [], []
    for case in s.cases.values():
        f = case.facts
        L = return_logistics(f)
        lane = L["lane"]
        fid = facility_id(f.location)
        rcv = received_at(f)
        ret = return_id(f)
        returns.append(
            {
                "RETURN_ID": ret,
                "RMA_ID": L["rma"],
                "RA_ID": f"RA-{case_no(f.id)}",
                "CLIENT_REF": f.id,
                "SKU": f.asset_id,
                "ITEM_DESC": f"{f.product} · {f.mfr}",
                "QTY": f.qty,
                "OWNER": f.owner,
                "RETURN_REASON": L["intent"].upper().replace(" ", "_"),
                "STATUS": "RECEIVED",
                "RECEIVED_AT": local(rcv),
                "RECEIVING_FACILITY": fid,
                "RECEIVING_LOCATION_CODE": FAC_LOC[f.location],
                "ORIGIN_LOCATION_CODE": lane["from"],
                "ORIGIN_SITE": LOCS[lane["from"]]["site"],
                "SHIPMENT_ID": f"SHP-{case_no(f.id)}",
                "CONDITION_CODE": f.grade or "UNGRADED",
            }
        )
        disp = DISPOSITION[f.grade]
        dispositions.append(
            {
                "DISPOSITION_ID": f"DSP-{case_no(f.id)}",
                "RETURN_ID": ret,
                "RMA_ID": L["rma"],
                "SKU": f.asset_id,
                "CLIENT_REF": f.id,
                "DISPOSITION": disp,
                "DISPOSITION_REASON": DISPOSITION_REASON[disp].format(g=f.grade),
                "GRADE": f.grade,
                "STATUS": "PROPOSED" if disp != "PENDING_INSPECTION" else "ON_HOLD",
                "DECIDED_BY": "RULES_ENGINE",
                "RULESET": "NF-RETURNS-2026.3",
                "DECIDED_AT": local(rcv + timedelta(hours=2)) if disp != "PENDING_INSPECTION" else None,
                "FINAL": False,  # Circularity decides the route; Optoro's disposition is a proposal
            }
        )
        shipments.append(
            {
                "SHIPMENT_ID": f"SHP-{case_no(f.id)}",
                "RETURN_ID": ret,
                "RMA_ID": L["rma"],
                "CLIENT_REF": f.id,
                "DIRECTION": "INBOUND",
                "CARRIER": L["carrier"],
                "CARRIER_SCAC": SCAC[L["carrier"]],
                "TMS_LOAD_ID": load_id(f),
                "TRACKING_NO": f"{SCAC[L['carrier']]}{as_hex(f.id, '|rl|trk') % 10**10:010d}",
                "ORIGIN_LOCATION_CODE": lane["from"],
                "DESTINATION_LOCATION_CODE": lane["to"],
                "DESTINATION_FACILITY": fid,
                "PICKUP_DATE": L["pickup"].date().isoformat(),
                "ETA": L["eta"].date().isoformat(),
                "DELIVERED_AT": local(rcv),
                "CARRIER_STATUS": "DELIVERED",
                "FREIGHT_USD": float(L["freight_usd"]),
                "FREIGHT_INR": float(lane["inr"]),
            }
        )
        ras.append(
            {
                "RA_ID": f"RA-{case_no(f.id)}",
                "RMA_ID": L["rma"],
                "CLIENT_REF": f.id,
                "SKU": f.asset_id,
                "QTY": f.qty,
                "OWNER": f.owner,
                "LEASE_CONTRACT_ID": L["lease"],
                "LEASE_END_DATE": L["end"].date().isoformat(),
                "RETURN_REASON": L["intent"].upper().replace(" ", "_"),
                "AUTHORIZED_AT": local(L["auth"] + timedelta(hours=14)),
                "RETURN_FEE_USD": float(L["fee"]),
                "REPLACEMENT_ORDER": demand_order(f),
                "STATUS": "CLOSED",
            }
        )
    return {"returns": returns, "dispositions": dispositions, "shipments": shipments, "return_authorizations": ras}


SPEC = Spec(
    source_id="rl",
    title="Optoro",
    schema="optoro",
    base_path="/optoro/v1",
    auth=Auth("api_key", header="X-Api-Key"),
    paging=Paging(
        "page", page_param="page", size_param="per_page", items_key="data", next_key="next_page", total_key="total_count"
    ),
    resources=(
        Resource(
            "returns",
            "/returns",
            "RETURN_ID",
            filters=("RMA_ID", "CLIENT_REF", "SKU", "STATUS", "RECEIVING_FACILITY", "OWNER"),
        ),
        Resource(
            "dispositions",
            "/dispositions",
            "DISPOSITION_ID",
            filters=("RETURN_ID", "RMA_ID", "CLIENT_REF", "SKU", "DISPOSITION", "STATUS"),
        ),
        Resource(
            "shipments",
            "/shipments",
            "SHIPMENT_ID",
            filters=("RETURN_ID", "RMA_ID", "CLIENT_REF", "CARRIER_SCAC", "CARRIER_STATUS", "TMS_LOAD_ID"),
        ),
        Resource(
            "return_authorizations",
            "/return-authorizations",
            "RA_ID",
            filters=("RMA_ID", "CLIENT_REF", "SKU", "STATUS"),
            create=True,
            id_format="RA-9{n:05d}",
            event="optoro.return_authorization",
        ),
    ),
    updated_since_param="updated_since",
    seed=seed,
)
