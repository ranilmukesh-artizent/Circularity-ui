"""One write per step kind, to the system that owns the work (B13b). Each writer is idempotent: sending the same
instruction again (a retry, or instruction.resend) never creates a second document, because every system is called
with a key it deduplicates on.

    order      IBM Sterling OMS     POST order/allocate {OrderNo, PrimeLineNo, SerialNo, Reference = key}
                                    idempotent on the header Idempotency-Key = key
    repair,    Oracle Depot Repair  csdrepairs/create_repair_order (REPAIR_TYPE Refurbishment / Teardown)
    teardown                        P_REPAIR_NUMBER = our WO number; a repeat is CSD_API_RO_NUM_EXISTS
    transport  Oracle Transp. Mgmt  POST orderReleases, the case's warehouse -> the ship-to (planned into a load)
                                    orderReleaseXid = OR-<key>; a repeat is "already exists"
    move       Manhattan Active WM  reservation/save, then order/save TRANSFER (to a facility) or OUTBOUND
                                    ReservationId / OrderId = our numbers; a repeat is 409 duplicate…
    pod        IBM Sterling OMS     POST order/{key}/fulfil RELEASE, SHIP, DELIVER with OTM's proof of delivery
                                    the line's status decides: only the missing actions are sent
    finance    SAP S/4HANA          SOAP Journal Entry - Post, one item per actual cost line
                                    DocumentReferenceID = approval reference; a repeat confirms the first (F5 117)

Where things come from: the order line is the case's matched demand (caseDemand: SO-48102 line 10 for RT-1048) and the
unit is the case's asset (the serial Sterling, Depot Repair and Manhattan know, MTR-2041). The transport goes from the
case's warehouse (FAC_LOC) to the demand's ship-to (the move's last stop when there is no demand); Manhattan's facility
ids are the location codes' (WH-PNQ-01 -> WH01, LOC-CHN-03 -> ST03). The journal entry's lines are the chosen route's
actual cost lines (di.execution.trace.line_actuals) in USD (the mock converts to INR at 83.5): a cost (a negative
term) is a debit, a value (avoided purchase, residual) a credit, balanced against the decision clearing account; each
item's AssignmentReference names its cost line, so the outcome read (di/connectors/adapters/s4.py) maps it back.

A writer raises `NotApplicable` when the case has nothing for that system to act on (no matched order line, no
ship-to): the step is then acknowledged by the simulated adapter, as the kinds without a mock write are. `Waiting`
means the step cannot be sent yet (delivery waits for the carrier's proof of delivery). `Refused` is a business
refusal that a retry will not change; a SourceError of kind "unavailable" or "auth" is retried.
"""

import uuid
from dataclasses import dataclass, field
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape

from sqlalchemy.orm import Session

from di import clock
from di.cases import store
from di.config import get_settings
from di.connectors.http import SourceClient, SourceError
from di.connectors.registry import ADAPTERS
from di.execution import ex_doc_num, ex_doc_ref, ex_kg, ex_move_raw, line_actuals
from di.instructions.queue import journal_ref
from di.reads.common import FAC_LOC, case_demand, demand_order

OTM_DOMAIN = "NORTHFIELD"
MANHATTAN_ORG = "NORTHFIELD"
STERLING = "/sterling/smcfs/restapi"
OTM = "/logisticsRestApi/resources/v2"
S4_JOURNAL = "/sap/bc/srt/scs_ext/sap/journalentrycreaterequestconfi"
S4_COMPANY = "1000"
S4_PLANTS = {"Warehouse 1": "2010", "Warehouse 2": "2020", "Repair centre": "2030"}
# G/L accounts per cost line (this deployment's chart): costs to expense accounts, values to income accounts
GL = {"purchase": "0048100000", "prep": "0051000000", "service": "0051200000", "residual": "0048200000", "lease": "0048300000"}
GL_OTHER, GL_CLEARING = "0051900000", "0021100000"
CLEARING = "CLEARING"  # AssignmentReference of the balancing item


class NotApplicable(Exception):
    """Nothing in this system to act on for the case: the step is acknowledged by the simulated adapter."""


class Waiting(Exception):
    """The step cannot be sent yet; `str(e)` says what it waits for."""


class Refused(Exception):
    """The system refused the write for a business reason; resending the same request would not change that."""


@dataclass
class Sent:
    request: list[dict]  # each call made: {"call", "body"}
    doc_ref: str | None = None  # the system's own reference, when the reply gives it
    detail: dict = field(default_factory=dict)  # what later steps or the event matching need


def client(s: Session, source_id: str) -> SourceClient:
    """The connector's own client (auth, fetch log) for a write."""
    a = ADAPTERS[source_id]
    return SourceClient(source_id, get_settings().source_sim_url.rstrip("/") + a.base_path, a.auth(), s)


def _step(c: store.Case, ins: dict) -> dict:
    return c["exec"]["steps"][ins["step"]]


def _ship_to(c: store.Case) -> str | None:
    """Where the unit goes: the demand's ship-to, else the move's last stop."""
    d = case_demand(c) or {}
    if d.get("shipTo"):
        return d["shipTo"]
    raw = ex_move_raw(c, c.get("chosen") or c["recommendation"])
    return raw["stops"][-1] if raw and raw.get("stops") else None


def manhattan_facility(code: str) -> str:
    """WH-PNQ-01 -> WH01, RC-HSR-01 -> RC01, LOC-CHN-03 -> ST03 (Manhattan's facility ids; OTM keeps the same map in
    each location's attribute2)."""
    prefix = {"WH": "WH", "RC": "RC", "LOC": "ST"}.get(code.split("-")[0], code.split("-")[0])
    return prefix + code[-2:]


# ---------------------------------------------------------------- IBM Sterling OMS
def order(s: Session, ins: dict, c: store.Case, prev: dict) -> Sent:  # noqa: ARG001 - every writer takes (session, instruction, case, previous)
    so, d = demand_order(c), case_demand(c) or {}
    if not so or not d.get("line"):
        raise NotApplicable("no matched sales order line")
    body = {
        "OrderNo": so,
        "PrimeLineNo": str(d["line"]),
        "SubLineNo": "1",
        "SerialNo": c["assetId"],
        "Reference": ins["idem_key"],
    }
    cl = client(s, "oms")
    try:
        r = cl.request("POST", f"{STERLING}/order/allocate", json=body, headers={"Idempotency-Key": ins["idem_key"]})
    except SourceError as e:
        raise _refused(e) from e
    finally:
        cl.close()
    return Sent(
        [{"call": "POST order/allocate", "body": body}], so, {"OrderHeaderKey": r.json()["OrderHeaderKey"], "line": d["line"]}
    )


def pod(s: Session, ins: dict, c: store.Case, prev: dict) -> Sent:  # noqa: ARG001 - every writer takes (session, instruction, case, previous)
    """Delivery confirmed: the order line is released, shipped and delivered in Sterling with the carrier's proof of
    delivery, once Oracle Transportation Management has reported the delivery."""
    alloc, transport = prev.get("order"), prev.get("transport")
    if not alloc or not alloc.get("detail", {}).get("OrderHeaderKey"):
        raise NotApplicable("no allocated order line to fulfil")
    proof = (transport or {}).get("detail", {}).get("delivery")
    if transport and not proof:
        raise Waiting("the carrier's proof of delivery (otm.shipment.delivered)")
    key, line = alloc["detail"]["OrderHeaderKey"], str(alloc["detail"]["line"])
    proof = proof or {}
    cl = client(s, "oms")
    calls = []
    try:
        o = cl.get_json(f"{STERLING}/order/{key}")
        ln = next(x for x in o["OrderLines"]["OrderLine"] if str(x["PrimeLineNo"]) == line)
        status = str(ln.get("MaxLineStatus") or "")
        todo = {"1500": ["RELEASE", "SHIP", "DELIVER"], "3200": ["SHIP", "DELIVER"], "3700": ["DELIVER"]}.get(status, [])
        for action in todo:
            body: dict = {"PrimeLineNo": line, "SubLineNo": "1", "Action": action, "Reference": ins["idem_key"]}
            if action == "SHIP":
                body |= {"SCAC": proof.get("carrier") or "NLTL", "TrackingNo": proof.get("shipment") or ""}
            if action == "DELIVER":
                body["ProofOfDelivery"] = {
                    "ReceivedBy": proof.get("received_by") or "Receiving",
                    "PODReference": proof.get("pod") or "",
                    "Remarks": f"Delivered on {proof.get('shipment') or 'the booked load'}",
                }
            cl.request("POST", f"{STERLING}/order/{key}/fulfil", json=body)
            calls.append({"call": f"POST order/{key}/fulfil", "body": body})
    except SourceError as e:
        raise _refused(e) from e
    finally:
        cl.close()
    return Sent(calls, proof.get("pod") or None, {"OrderHeaderKey": key})


# ---------------------------------------------------------------- Oracle Depot Repair
def repair(s: Session, ins: dict, c: store.Case, prev: dict) -> Sent:  # noqa: ARG001 - every writer takes (session, instruction, case, previous)
    number = ex_doc_ref(c, _step(c, ins))  # WO-47349: our planned work order number becomes the repair number
    rec = {
        "SERIAL_NUMBER": c["assetId"],
        "REPAIR_TYPE": "Teardown" if ins["kind"] == "teardown" else "Refurbishment",
        "QUANTITY": 1,
        "ORIGINAL_SOURCE_REFERENCE": c["exec"]["ref"],
        "PROBLEM_DESCRIPTION": f"{_step(c, ins)['label']} for {c['id']} under {c['exec']['ref']}",
    }
    body = {
        "CREATE_REPAIR_ORDER_Input": {
            "RESTHeader": {
                "Responsibility": "DEPOT_REPAIR_SUPER_USER", "RespApplication": "CSD", "SecurityGroup": "STANDARD",
                "NLSLanguage": "AMERICAN",
            },
            "InputParameters": {"P_API_VERSION_NUMBER": "1.0", "P_REPAIR_NUMBER": number, "P_REPLN_REC": rec},
        }
    }  # fmt: skip
    cl = client(s, "repair")
    try:
        out = cl.request("POST", "/csdrepairs/create_repair_order/", json=body).json()["OutputParameters"]
    except SourceError as e:
        raise _refused(e) from e
    finally:
        cl.close()
    calls = [{"call": "POST csdrepairs/create_repair_order", "body": body}]
    if out.get("X_RETURN_STATUS") == "S":
        return Sent(calls, out["X_REPAIR_NUMBER"], {"repair_line_id": out.get("X_REPAIR_LINE_ID")})
    msg = str(out.get("X_MSG_DATA") or "")
    if "CSD_API_RO_NUM_EXISTS" in msg:  # sent before: the repair order with our number exists
        return Sent(calls, number, {"duplicate": True})
    if "CSD_RO_SERIAL_IN_REPAIR" in msg:  # the unit is on another repair order now; it frees up later
        raise SourceError("unavailable", f"repair: {msg}")
    raise Refused(f"Oracle Depot Repair refused the repair order: {msg}")


# ---------------------------------------------------------------- Oracle Transportation Management
def transport(s: Session, ins: dict, c: store.Case, prev: dict) -> Sent:  # noqa: ARG001 - every writer takes (session, instruction, case, previous)
    src, dst = FAC_LOC.get(c["location"]), _ship_to(c)
    if not src or not dst or src == dst:
        raise NotApplicable("no lane from the case's warehouse")
    xid = f"OR-{ins['idem_key']}"
    move_type = {"redeploy": "REDEPLOYMENT", "relase": "RELEASE_TO_LEASE"}.get((c.get("chosen") or {}).get("id"), "OUTBOUND")
    refnums = {"CASE_REF": c["id"], "ITEM_ID": c["assetId"], "MOVE_TYPE": move_type, "APPROVAL": c["exec"]["ref"]}
    body = {
        "orderReleaseXid": xid,
        "orderReleaseName": f"{c['id']} {src} to {dst}",
        "sourceLocationGid": f"{OTM_DOMAIN}.{src}",
        "destLocationGid": f"{OTM_DOMAIN}.{dst}",
        "totalWeight": {"value": ex_kg(c), "unit": "KG"},
        "totalShipUnitCount": 1,
        "refnums": {
            "items": [
                {"orderReleaseRefnumQualGid": f"{OTM_DOMAIN}.{k}", "orderReleaseRefnumValue": v} for k, v in refnums.items()
            ]
        },
    }
    cl = client(s, "tms")
    try:
        try:
            r = cl.request("POST", f"{OTM}/orderReleases", json=body)
            planned = any("PLANNED" in x.get("statusValueGid", "") for x in r.json().get("statuses", {}).get("items", []))
        except SourceError as e:
            if e.kind != "client" or "already exists" not in str(e):
                raise
            planned = True  # sent before; the shipment it planned is found below
        found = cl.get_json(f"{OTM}/shipments", params={"q": f'orderReleases.orderReleaseGid eq "{OTM_DOMAIN}.{xid}"'})
    except SourceError as e:
        raise _refused(e) from e
    finally:
        cl.close()
    if not planned or not found.get("items"):
        raise Refused(f"Oracle Transportation Management did not plan {xid}: no active rate record for {src} > {dst}")
    sh = found["items"][0]
    detail = {"orderReleaseXid": xid, "shipmentGid": sh["shipmentGid"], "shipmentXid": sh["shipmentXid"], "from": src, "to": dst}
    # the load is the system's document; the step is acknowledged by the carrier's tender acceptance event
    return Sent([{"call": "POST orderReleases", "body": body}], sh["shipmentXid"], detail)


# ---------------------------------------------------------------- Manhattan Active WM
def move(s: Session, ins: dict, c: store.Case, prev: dict) -> Sent:
    src, dst = FAC_LOC.get(c["location"]), _ship_to(c)
    if not src or not dst or src == dst:
        raise NotApplicable("no move out of the case's warehouse")
    facility, dest = manhattan_facility(src), manhattan_facility(dst)
    order_id = ex_doc_ref(c, _step(c, ins))  # TR-47362: our planned transfer number
    rsv = f"RSV-{ex_doc_num(c, 'move')}"
    headers = {"SelectedOrganization": MANHATTAN_ORG, "SelectedLocation": facility}
    reserve = {"ItemId": c["assetId"], "Quantity": 1, "ReservationId": rsv, "OrderId": order_id, "ReferenceId": ins["idem_key"]}
    otype = "TRANSFER" if dest[:2] in ("WH", "RC") else "OUTBOUND"
    carrier = ((prev.get("transport") or {}).get("detail") or {}).get("carrier") or "NLTL"
    save = {
        "OrderId": order_id,
        "OrderType": otype,
        "DestinationFacilityId": dest,
        "ExternalReference": ins["idem_key"],
        "CarrierId": carrier,
        "OrderLine": [{"OrderLineId": "1", "ItemId": c["assetId"], "OrderedQuantity": 1, "ReservationId": rsv}],
    }
    cl = client(s, "wms")
    try:
        _ok_if_duplicate(
            lambda: cl.request("POST", "/dcinventory/api/dcinventory/reservation/save", json=reserve, headers=headers)
        )
        _ok_if_duplicate(lambda: cl.request("POST", "/dcorder/api/dcorder/order/save", json=save, headers=headers))
    except SourceError as e:
        raise _refused(e) from e
    finally:
        cl.close()
    calls = [{"call": "POST reservation/save", "body": reserve}, {"call": "POST order/save", "body": save}]
    return Sent(calls, order_id, {"facility": facility, "destination": dest, "type": otype, "reservation": rsv})


def _ok_if_duplicate(call) -> None:
    """Manhattan answers 409 duplicate… for an id it already has: the earlier send went through."""
    try:
        call()
    except SourceError as e:
        if not (e.status == 409 and "duplicate" in str(e)):
            raise


# ---------------------------------------------------------------- SAP S/4HANA
def finance(s: Session, ins: dict, c: store.Case, prev: dict) -> Sent:  # noqa: ARG001 - every writer takes (session, instruction, case, previous)
    r = c.get("chosen") or c["recommendation"]
    lines = [ln for ln in line_actuals(c, r) if ln["act"]]
    if not lines:
        raise NotApplicable("no actual cost lines")
    ref = journal_ref(c["exec"]["ref"])
    plant = S4_PLANTS.get(c["location"])
    items = []
    for n, ln in enumerate(lines, start=1):
        # a cost (negative term) is a debit; a value (avoided purchase, residual) a credit
        items.append(_item(n, GL.get(ln["kind"], GL_OTHER), -ln["act"], ln["label"], ln["kind"], c["assetId"], plant))
    total = sum(ln["act"] for ln in lines)
    items.append(_item(len(lines) + 1, GL_CLEARING, total, f"Decision clearing {c['id']}", CLEARING, None, None))
    today = clock.now().date().isoformat()
    msg = uuid.uuid5(uuid.NAMESPACE_URL, ins["idem_key"]).hex.upper()  # the same message id on every resend
    xml = (
        '<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" '
        'xmlns:sfin="http://sap.com/xi/SAPSCORE/SFIN"><soapenv:Header/><soapenv:Body>'
        f"<sfin:JournalEntryBulkCreateRequest><MessageHeader><ID>{msg}</ID></MessageHeader>"
        f"<JournalEntryCreateRequest><MessageHeader><ID>{msg}</ID></MessageHeader><JournalEntry>"
        "<OriginalReferenceDocumentType>BKPFF</OriginalReferenceDocumentType>"
        "<BusinessTransactionType>RFBU</BusinessTransactionType><AccountingDocumentType>SA</AccountingDocumentType>"
        f"<DocumentReferenceID>{escape(ref)}</DocumentReferenceID>"
        f"<DocumentHeaderText>{escape(('Actuals ' + c['id'])[:25])}</DocumentHeaderText>"
        f"<CompanyCode>{S4_COMPANY}</CompanyCode><DocumentDate>{today}</DocumentDate><PostingDate>{today}</PostingDate>"
        + "".join(items)
        + "</JournalEntry></JournalEntryCreateRequest></sfin:JournalEntryBulkCreateRequest></soapenv:Body></soapenv:Envelope>"
    )
    cl = client(s, "erp")
    try:
        resp = cl.request("POST", S4_JOURNAL, content=xml.encode(), headers={"Content-Type": "text/xml; charset=utf-8"})
    except SourceError as e:
        raise _refused(e) from e
    finally:
        cl.close()
    root = ET.fromstring(resp.content)  # noqa: S314 - the reply of the configured S/4 system (the simulator)
    doc = _find(root, "AccountingDocument")
    severity = _find(root, "MaximumLogItemSeverityCode")
    if severity == "3" or not doc or doc == "0000000000":
        notes = "; ".join(e.text or "" for e in root.iter() if e.tag.rsplit("}", 1)[-1] == "Note")
        raise Refused(f"SAP S/4HANA did not post the journal entry: {notes}")
    call = {"call": "POST JournalEntryCreateRequestConfirmation_In", "body": {"DocumentReferenceID": ref, "lines": lines}}
    detail = {"AccountingDocument": doc, "CompanyCode": _find(root, "CompanyCode"), "FiscalYear": _find(root, "FiscalYear")}
    return Sent([call], doc, detail | {"duplicate": severity == "2"})


def _item(n: int, gl: str, usd: float, text_: str, assignment: str, material: str | None, plant: str | None) -> str:
    extra = (f"<Material>{escape(material)}</Material>" if material else "") + (f"<Plant>{plant}</Plant>" if plant else "")
    return (
        f"<Item><ReferenceDocumentItem>{n}</ReferenceDocumentItem><GLAccount>{gl}</GLAccount>"
        f'<AmountInTransactionCurrency currencyCode="USD">{usd:.2f}</AmountInTransactionCurrency>'
        f"<DocumentItemText>{escape(text_[:50])}</DocumentItemText>"
        f"<AssignmentReference>{escape(assignment[:18])}</AssignmentReference>{extra}</Item>"
    )


def _find(root: ET.Element, name: str) -> str:
    return next(((e.text or "").strip() for e in root.iter() if e.tag.rsplit("}", 1)[-1] == name), "")


def _refused(e: SourceError) -> Exception:
    """A 4xx other than auth is a business refusal; anything else is retried."""
    return Refused(str(e)) if e.kind == "client" else e


WRITERS = {
    "order": order,
    "repair": repair,
    "teardown": repair,
    "transport": transport,
    "move": move,
    "pod": pod,
    "finance": finance,
}
