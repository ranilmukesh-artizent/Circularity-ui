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
    recon_order, lot_transfer, listing, dealer_trade     the dealer system (`uc_dms`, plan 9 P9-9.17: the used-car channels)
                                    POST recon-orders, transfers, listings (with the route's disclosures), dealer-trades
    consignment, salvage_sale       the auction platform (`uc_auction`): POST consignments (with the title reference and the
                                    disclosures), salvage-sales (only to a buyer that reports to the national title database)
                                    all idempotent on the header Idempotency-Key = key; the reply is the system's confirmation
    residual, lessee_charge         the close of a used-car lease return (P9-9.20), sent on their own, outside an approval's plan,
                                    after Finance accepts the agent's proposal: `residual` the gain or loss against the book
                                    value, one S/4HANA journal item and the clearing item (same posting as `finance`);
                                    `lessee_charge` POST charges {leaseId, kind, amount} to the lease system (`uc_lease`)

Where things come from: the order line is the case's matched demand (caseDemand: SO-48102 line 10 for RT-1048) and the
unit is the case's asset (the serial Sterling, Depot Repair and Manhattan know, MTR-2041). The transport goes from the
case's warehouse (FAC_LOC) to the demand's ship-to (the move's last stop when there is no demand); Manhattan's facility
ids are the location codes' (WH-PNQ-01 -> WH01, LOC-CHN-03 -> ST03). The journal entry's lines are the chosen route's
actual cost lines (di.services.execution.trace.line_actuals) in USD (the mock converts to INR at 83.5): a cost (a negative
term) is a debit, a value (avoided purchase, residual) a credit, balanced against the decision clearing account; each
item's AssignmentReference names its cost line, so the outcome read (di/connectors/adapters/s4.py) maps it back.

A writer raises `NotApplicable` when the case has nothing for that system to act on (no matched order line, no
ship-to): the step is then acknowledged by the simulated adapter, as the kinds without a mock write are. `Waiting`
means the step cannot be sent yet (delivery waits for the carrier's proof of delivery). `Refused` is a business
refusal that a retry will not change; a SourceError of kind "unavailable" or "auth" is retried.

The target's outbound workflow, once published here (di/services/instructions/outbound.py), may set the HTTP timeout of the
writes (`timeout`, its delivery method's Timeout) and, for Oracle Depot Repair, which repair order its write connector
makes (`operation_for`: Refurbishment or Teardown). Without one every write is as described above.
"""

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape

from sqlalchemy.orm import Session

from di.connectors.http import SourceClient, SourceError
from di.connectors.registry import ADAPTERS
from di.core import clock
from di.core.config import get_settings
from di.repositories.common import FAC_LOC, case_demand, demand_order
from di.services.cases import store
from di.services.execution import ex_doc_num, ex_doc_ref, ex_kg, ex_move_raw, line_actuals
from di.services.instructions.queue import SYSTEM_OF, TEMPLATE_SYSTEM_OF, journal_ref

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
GL_FEE = "0048400000"  # the income account of a non-return fee (P9-3.18)
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


_TIMEOUT: ContextVar[float | None] = ContextVar("write_timeout", default=None)


@contextmanager
def timeout(seconds: float | None) -> Iterator[None]:
    """The HTTP timeout of the writes made inside (the bound outbound workflow's delivery method, di/services/instructions/
    outbound.py); None: the client's own."""
    tok = _TIMEOUT.set(seconds)
    try:
        yield
    finally:
        _TIMEOUT.reset(tok)


def current_timeout() -> float | None:
    return _TIMEOUT.get()


def client(s: Session, source_id: str) -> SourceClient:
    """The connector's own client (auth, fetch log) for a write."""
    a = ADAPTERS[source_id]
    url = get_settings().source_sim_url.rstrip("/") + a.base_path
    t = _TIMEOUT.get()
    return SourceClient(source_id, url, a.auth(), s) if t is None else SourceClient(source_id, url, a.auth(), s, timeout=t)


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
    if isinstance(c.get("serviceDesk"), dict):  # a service ticket's fix (P9-4.9): one service reference for all its fix lines
        serials = [ln["serial"] for ln in c["serviceDesk"]["lines"] if ln["n"] in (_step(c, ins).get("lines") or [])]
        rec |= {
            "SERIAL_NUMBER": serials[0] if serials else c["assetId"],
            "REPAIR_TYPE": "Repair and Return",
            "ORIGINAL_SOURCE_REFERENCE": c["id"],
            "PROBLEM_DESCRIPTION": f"Repair and return of {', '.join(serials)} for {c['id']} under {c['exec']['ref']}",
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
    route: Any = (c.get("chosen") or {}).get("id")
    move_type = {"redeploy": "REDEPLOYMENT", "relase": "RELEASE_TO_LEASE"}.get(route, "OUTBOUND")
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
    doc, detail = post_journal(s, ins, ref, f"Actuals {c['id']}", items)
    call = {"call": "POST JournalEntryCreateRequestConfirmation_In", "body": {"DocumentReferenceID": ref, "lines": lines}}
    return Sent([call], doc, detail)


def post_journal(s: Session, ins: dict, ref: str, header: str, items: list[str]) -> tuple[str, dict[str, Any]]:
    """One S/4HANA journal entry (SOAP Journal Entry - Post) with the items, once per instruction key: the document number and
    what later steps need (`detail`: AccountingDocument, CompanyCode, FiscalYear, duplicate). A refusal is `Refused`."""
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
        f"<DocumentHeaderText>{escape(header[:25])}</DocumentHeaderText>"
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
    detail = {"AccountingDocument": doc, "CompanyCode": _find(root, "CompanyCode"), "FiscalYear": _find(root, "FiscalYear")}
    return doc, detail | {"duplicate": severity == "2"}


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


def payout(s: Session, ins: dict, c: store.Case, prev: dict) -> Sent:  # noqa: ARG001 - every writer takes (session, instruction, case, previous)
    """Device Lab (the trade-in platform): PATCH /tradeins/{tradeInId} {payoutAmount}, the payout now on the case (P9-6.8). The
    trade-in id and the amount are the key: the same PATCH twice leaves the same payout."""
    from di.repositories import device_tradeins  # lazy: the device repositories are only needed by this write

    p = c.get("payout") or {}
    row = device_tradeins.by_imei(s, str((c.get("valuer") or {}).get("imei") or ""))
    if row is None or p.get("status") not in ("adjusted", "decided"):
        raise NotApplicable("no trade-in or no payout to send")
    body = {"payoutAmount": p["adjusted"]}
    cl = client(s, "dvlab")
    try:
        cl.request("PATCH", f"/tradeins/{row.trade_in_id}", json=body)
    except SourceError as e:
        raise _refused(e) from e
    finally:
        cl.close()
    return Sent([{"call": "PATCH tradeins/{tradeInId}", "body": body}], row.trade_in_id, {"tradeInId": row.trade_in_id, **body})


# ---------------------------------------------------------------- used-car channels (P9-9.17)
UC_DMS = "/dealer-dms/api/v1"
UC_AUCTION = "/vehicle-auction/v1"


def _uc_post(s: Session, source: str, path: str, ins: dict, body: dict, id_field: str, step: bool = True) -> Sent:
    """One idempotent write to the dealer system or the auction platform (`Idempotency-Key` = the instruction key: a repeat
    answers the first document). The reply's document is the system's confirmation: `detail.confirmed` lets the send
    acknowledge the step (these systems send no completion event); `step` False for an instruction outside an approval's plan
    (P9-9.20), which has no plan step to acknowledge: the send marks its own row."""
    cl = client(s, source)
    try:
        doc = cl.request("POST", path, json=body, headers={"Idempotency-Key": ins["idem_key"]}).json()
    except SourceError as e:
        raise _refused(e) from e
    finally:
        cl.close()
    ref = str(doc.get(id_field) or "")
    return Sent(
        [{"call": f"POST {path.lstrip('/')}", "body": body}], ref or None, {"confirmed": bool(ref), id_field: ref, "step": step}
    )


def _car(s: Session, c: store.Case) -> tuple[str, dict[str, dict[str, Any]]]:
    """The car's VIN and its canonical records (`asset`, `condition`, `market`, `vendor`)."""
    from di.services.cases import car_facts  # lazy: only the used-car writers read the car's records

    vin = (c.get("vehicle") or {}).get("vin")
    if not vin:
        raise NotApplicable("the case has no VIN")
    return str(vin), car_facts.records(s, str(c["assetId"]))


def _title_ref(c: store.Case, vin: str) -> str:
    """The title reference an auction or a dealer trade carries: the lien release's reference when there was a lien, else the
    title search of the VIN (the title service gives no reference of its own)."""
    return str((c.get("title") or {}).get("lien_release_ref") or f"TITLE-{vin}")


def recon_order(s: Session, ins: dict, c: store.Case, prev: dict) -> Sent:  # noqa: ARG001 - every writer takes (session, instruction, case, previous)
    """Dealer system: POST /recon-orders {vin, estimate, lines}, the inspection's estimate and lines."""
    vin, facts = _car(s, c)
    cond = facts.get("condition", {})
    if cond.get("recon_estimate") is None:
        raise NotApplicable("no reconditioning estimate")
    body = {"vin": vin, "estimate": cond["recon_estimate"], "lines": list(cond.get("recon_lines") or [])}
    return _uc_post(s, "uc_dms", f"{UC_DMS}/recon-orders", ins, body, "orderId")


def lot_transfer(s: Session, ins: dict, c: store.Case, prev: dict) -> Sent:  # noqa: ARG001 - every writer takes (session, instruction, case, previous)
    """Dealer system: POST /transfers {vin, fromLot, toLot}. The car is at its lot (`asset.lot_id`), else at the lot nearest the
    return centre (`market.lot_distance_miles`); it goes to the retail route's lot, and nothing is sent when it is there."""
    vin, facts = _car(s, c)
    to = str((c.get("chosen") or {}).get("id", "")).partition(":")[2]
    near: dict[str, Any] = facts.get("market", {}).get("lot_distance_miles") or {}
    here = facts.get("asset", {}).get("lot_id") or min(near, key=lambda lot: near[lot], default=None)
    if not to or not here or here == to:
        raise NotApplicable("the car is already at the lot")
    return _uc_post(s, "uc_dms", f"{UC_DMS}/transfers", ins, {"vin": vin, "fromLot": here, "toLot": to}, "transferId")


def listing(s: Session, ins: dict, c: store.Case, prev: dict) -> Sent:  # noqa: ARG001 - every writer takes (session, instruction, case, previous)
    """Dealer system: POST /listings {vin, lotId, price, disclosures}: the retail price of the chosen route and the route's
    disclosures (a title brand, an open recall, an odometer that is not the actual mileage)."""
    vin, _ = _car(s, c)
    chosen = c.get("chosen") or {}
    lot = str(chosen.get("id", "")).partition(":")[2]
    price = next((t["amt"] for t in chosen.get("terms") or [] if t.get("kind") == "sale"), None)
    if not lot or price is None:
        raise NotApplicable("no lot or retail price on the chosen route")
    body = {"vin": vin, "lotId": lot, "price": price, "disclosures": list(chosen.get("disclosures") or [])}
    return _uc_post(s, "uc_dms", f"{UC_DMS}/listings", ins, body, "listingId")


def dealer_trade(s: Session, ins: dict, c: store.Case, prev: dict) -> Sent:  # noqa: ARG001 - every writer takes (session, instruction, case, previous)
    """Dealer system: POST /dealer-trades {vin, partner, price, titleRef}: the highest partner bid, read from the system."""
    vin, _ = _car(s, c)
    cl = client(s, "uc_dms")
    try:
        bids = cl.get_json(f"{UC_DMS}/partner-bids", params={"vin": vin}).get("items") or []
    except SourceError as e:
        raise _refused(e) from e
    finally:
        cl.close()
    best = max(bids, key=lambda b: b["amount"], default=None)
    if best is None:
        raise Refused("The dealer system holds no partner bid for the car")
    body = {"vin": vin, "partner": best["partner"], "price": best["amount"], "titleRef": _title_ref(c, vin)}
    return _uc_post(s, "uc_dms", f"{UC_DMS}/dealer-trades", ins, body, "dealerTradeId")


def consignment(s: Session, ins: dict, c: store.Case, prev: dict) -> Sent:  # noqa: ARG001 - every writer takes (session, instruction, case, previous)
    """Auction platform: POST /consignments {vin, saleDate, titleRef, disclosures}: the next sale of the car's site and the
    route's disclosures."""
    vin, facts = _car(s, c)
    days = facts.get("market", {}).get("auction_next_sale_days")
    if days is None:
        raise Refused("The auction platform has no next sale for the car's site")
    sale = clock.now().date() + timedelta(days=int(days))
    disclosures = list((c.get("chosen") or {}).get("disclosures") or [])
    body = {"vin": vin, "saleDate": sale.isoformat(), "titleRef": _title_ref(c, vin), "disclosures": disclosures}
    return _uc_post(s, "uc_auction", f"{UC_AUCTION}/consignments", ins, body, "consignmentId")


def salvage_sale(s: Session, ins: dict, c: store.Case, prev: dict) -> Sent:  # noqa: ARG001 - every writer takes (session, instruction, case, previous)
    """Auction platform: POST /salvage-sales {vin, buyerId}: the buyer of the best salvage bid, only when it reports to the
    national title database (G-VEH-SALV; the platform refuses a buyer that does not as well)."""
    vin, facts = _car(s, c)
    buyer = facts.get("market", {}).get("salvage_buyer")
    if not buyer:
        raise Refused("No salvage buyer on file for the car")
    if (facts.get("vendor") or {}).get("title_db_reporting") is not True:
        raise Refused("Salvage buyer must report to the national title database")
    return _uc_post(s, "uc_auction", f"{UC_AUCTION}/salvage-sales", ins, {"vin": vin, "buyerId": buyer}, "salvageSaleId")


# ---------------------------------------------------------------- the close of a used-car lease return (P9-9.20)
UC_LEASE = "/vehicle-lease/api/v1"


def _close_amount(ins: dict) -> tuple[str, float]:
    """The label and amount the close step stored on the instruction (`detail.close`, di.services.cases.close_used_cars)."""
    close = (ins.get("detail") or {}).get("close") or {}
    if close.get("amount") is None:
        raise NotApplicable("no amount on the instruction")
    return str(close.get("label") or "Residual"), float(close["amount"])


def residual(s: Session, ins: dict, c: store.Case, prev: dict) -> Sent:  # noqa: ARG001 - every writer takes (session, instruction, case, previous)
    """SAP S/4HANA: the residual gain or loss of a lease return, realised net less the book value (the lease's residual). A
    gain is a credit on the residual account, a loss a debit, balanced on the clearing account, like the lines of `finance`."""
    label, amount = _close_amount(ins)
    if amount == 0:
        raise NotApplicable("no gain or loss to post")
    ref = journal_ref(f"RES-{c['id']}")
    items = [
        _item(1, GL["residual"], -amount, label, "residual", None, None),
        _item(2, GL_CLEARING, amount, f"Residual clearing {c['id']}", CLEARING, None, None),
    ]
    doc, detail = post_journal(s, ins, ref, f"Residual {c['id']}", items)
    call = {"call": "POST JournalEntryCreateRequestConfirmation_In", "body": {"DocumentReferenceID": ref, "residual": amount}}
    return Sent([call], doc, detail | {"confirmed": True, "step": False})


def lessee_charge(s: Session, ins: dict, c: store.Case, prev: dict) -> Sent:  # noqa: ARG001 - every writer takes (session, instruction, case, previous)
    """Lease system: POST /charges {leaseId, kind, amount}: the excess-mileage or the excess-wear charge to the lessee, the
    lease's own id read from the car's `asset.lease_ref`."""
    label, amount = _close_amount(ins)
    kind = str(((ins.get("detail") or {}).get("close") or {}).get("kind") or "")
    _vin, facts = _car(s, c)
    lease = facts.get("asset", {}).get("lease_ref")
    if not lease:
        raise NotApplicable("the car has no lease")
    body = {"leaseId": str(lease), "kind": kind, "amount": amount}
    return _uc_post(s, "uc_lease", f"{UC_LEASE}/charges", ins, body, "chargeId", step=False)


def security_inspection(s: Session, ins: dict, c: store.Case, prev: dict) -> Sent:  # noqa: ARG001 - every writer takes (session, instruction, case, previous)
    """A core-site unit's security inspection (P9-10.12, diversion DV-TN-CORE): a person's checklist step at Wipe and test.
    No system is written to, so nothing is sent: the step is acknowledged by the simulated adapter and a person ticks it."""
    raise NotApplicable("a person's checklist step: no system write")


def firmware_upgrade(s: Session, ins: dict, c: store.Case, prev: dict) -> Sent:  # noqa: ARG001 - every writer takes (session, instruction, case, previous)
    """The test bench (tn_bench): POST /refurb-orders {serial, kind: firmware}, the firmware upgrade of a unit behind
    (P9-10.12, diversion DV-TN-FW). The bench deduplicates on the serial: sending it twice gives the one order."""
    serial = str(c.get("serial") or c.get("assetId") or "").rpartition(":")[2]
    if not serial:
        raise NotApplicable("no unit serial to order the upgrade for")
    body = {"serial": serial, "kind": "firmware"}
    cl = client(s, "tn_bench")
    try:
        r = cl.request("POST", "/refurb-orders", json=body)
    except SourceError as e:
        raise _refused(e) from e
    finally:
        cl.close()
    order_id = r.json().get("orderId")
    return Sent([{"call": "POST refurb-orders", "body": body}], order_id, {"orderId": order_id, "serial": serial})


def enhanced_decon(s: Session, ins: dict, c: store.Case, prev: dict) -> Sent:  # noqa: ARG001 - every writer takes (session, instruction, case, previous)
    """Decontamination log (the medical rental company's): POST /cycles {tag, enhanced: true} schedules an enhanced cycle for the
    device, the step DV-MR-ISO adds for a device from an isolation ward (P9-11.12, MR-12). The tag is the key: a repeat while a
    cycle is scheduled answers with that cycle and schedules no second one. The gate G-MED-DECON then needs the record of that
    cycle (`decon_enhanced`). Decontamination guidance needs review by Kinective's Legal team before it is relied on."""
    key = str(c.get("assetId") or "")
    if ":" not in key:
        raise NotApplicable("no device tag to decontaminate")
    body = {"tag": key.split(":", 1)[1], "enhanced": True}
    cl = client(s, "mr_decon")
    try:
        r = cl.request("POST", "/cycles", json=body)
    except SourceError as e:
        raise _refused(e) from e
    finally:
        cl.close()
    cycle = r.json().get("cycleId")
    return Sent([{"call": "POST cycles", "body": body}], cycle, {"cycleId": cycle, "enhanced": True})


def battery_assessment(s: Session, ins: dict, c: store.Case, prev: dict) -> Sent:  # noqa: ARG001 - every writer takes (session, instruction, case, previous)
    """The vehicle inspection app (uc_insp): POST /battery-assessments {vin}, the traction battery assessment of an EV under
    the used-car pack's diversion DV-UC-EV (P9-9.14). Idempotent on the instruction key (header Idempotency-Key): sending it
    again gives the first assessment, never a second one. The assessment's result comes back as the fact
    `condition.battery_assessment_result` (the adapter reads it), which releases the case's hold."""
    vin = str((c.get("vehicle") or {}).get("vin") or str(c.get("assetId") or "").rpartition(":")[2])
    if not vin:
        raise NotApplicable("no VIN to assess the battery of")
    body = {"vin": vin}
    cl = client(s, "uc_insp")
    try:
        r = cl.request("POST", "/battery-assessments", json=body, headers={"Idempotency-Key": ins["idem_key"]})
    except SourceError as e:
        raise _refused(e) from e
    finally:
        cl.close()
    ref = r.json().get("assessmentId")
    return Sent([{"call": "POST battery-assessments", "body": body}], ref, {"assessmentId": ref, "vin": vin})


def list_device(s: Session, ins: dict, c: store.Case, prev: dict) -> Sent:  # noqa: ARG001 - every writer takes (session, instruction, case, previous)
    """Device market: POST /listings, the received device on its channel at the forecast P50 (P9-6.12). The listing id is
    made from the case and the channel (`<case id>:<channel>`), so a repeat is the market's own 409: the first listing is
    read and no second is made. The body carries the instruction key (`issuedKey`), which the market's
    `devicemarket.listing.created` event returns."""
    from di.services.device import settle  # lazy: the device services are only needed by this write

    body = settle.listing_body(c)
    if body is None:
        raise NotApplicable("nothing to list: not a received device on a listing channel")
    body = body | {"issuedKey": ins["idem_key"]}
    lid, duplicate = body["listingId"], False
    cl = client(s, "dvmkt")
    try:
        try:
            cl.request("POST", "/listings", json=body)
        except SourceError as e:
            if e.status != 409:
                raise
            cl.get_json(f"/listings/{lid}")  # listed before: the first listing stands
            duplicate = True
    except SourceError as e:
        raise _refused(e) from e
    finally:
        cl.close()
    return Sent(
        [{"call": "POST listings", "body": body}], lid,
        {"listingId": lid, "channel": body["channel"], "price": body["price"], "duplicate": duplicate},
    )  # fmt: skip


WRITERS = {
    "list": list_device,
    "battery_assessment": battery_assessment,
    "enhanced_decon": enhanced_decon,
    "security_inspection": security_inspection,
    "firmware_upgrade": firmware_upgrade,
    "residual": residual,
    "lessee_charge": lessee_charge,
    "recon_order": recon_order,
    "lot_transfer": lot_transfer,
    "listing": listing,
    "dealer_trade": dealer_trade,
    "consignment": consignment,
    "salvage_sale": salvage_sale,
    "payout": payout,
    "order": order,
    "repair": repair,
    "teardown": repair,
    "transport": transport,
    "move": move,
    "pod": pod,
    "finance": finance,
}
from di.services.instructions import writers_fleet  # noqa: E402 - it uses Sent, Refused and client, defined above

WRITERS |= {
    "fleet_issue": writers_fleet.fleet_issue,
    "parts_issue": writers_fleet.parts_issue,
    "nonreturnfee": writers_fleet.fee_post,
    "proposal_send": writers_fleet.proposal_send,
    "lines_draft": writers_fleet.lines_draft,
    "units_reserve": writers_fleet.units_reserve,
}


def operations(system: str) -> list[str]:
    """The write operations of a target system (the step kinds written to it): the choices of a write connector's
    Target operation. oms: order, pod; repair: repair, teardown; tms: transport; wms: move; erp: finance; fleet: lease;
    parts: partsxfer (the tool fleet's re-issue and harvest, P9-3.17)."""
    own = [k for t in TEMPLATE_SYSTEM_OF.values() for k, sys in t.items() if sys == system]
    return [k for k, sys in SYSTEM_OF.items() if sys == system] + own


# P9-3.17: the writer of a step of a template that writes it to its own system (the industrial `lease` and `partsxfer` steps
# have none: the simulated adapter acknowledges them)
WRITE_KIND = {
    "tool_fleet": {
        "lease": "fleet_issue", "partsxfer": "parts_issue",
        "propsend": "proposal_send", "propdraft": "lines_draft", "propreserve": "units_reserve",
    }
}  # fmt: skip


def write_kind(c: store.Case, kind: str) -> str:
    """The writer a case's step of `kind` goes through: its template's own (`fleet_issue`, `parts_issue`), else the kind."""
    return WRITE_KIND.get(c.get("template") or "", {}).get(kind, kind)


def operation_for(kind: str, operation: str | None) -> str:
    """The write a step of `kind` makes when its target's write connector names `operation`: that operation when it
    is the same call with another option (Oracle Depot Repair's repair order: Refurbishment `repair` or Teardown
    `teardown`), else the step's own (an allocation is never sent as a delivery)."""
    if operation and operation != kind and kind in WRITERS and WRITERS.get(operation) is WRITERS[kind]:
        return operation
    return kind
