"""IBM Sterling OMS mock: HTTP surface (docs/backend-steps.md, B5). See the package docstring for the contract."""

import base64
import secrets
import time
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select, update
from sqlalchemy.engine import Connection
from sqlalchemy.exc import IntegrityError

from sim import clock, events
from sim.db import engine
from sim.vendors.sterling import tables as t
from sim.vendors.sterling.seed import ENTERPRISE, RETURN, SALES, STATUS

SOURCE = "oms"
BASE = "/sterling/smcfs/restapi"
CLIENTS = {"di-connector": "circularity-demo-sterling-secret"}  # demo OAuth 2.0 client (see the package docstring)
TOKEN_TTL = 3600
PAGE_SIZE, MAX_PAGE_SIZE = 50, 200
IST = timezone(timedelta(hours=5, minutes=30))
NEXT = {"1500": ("RELEASE", "3200"), "3200": ("SHIP", "3700"), "3700": ("DELIVER", "3700.7777")}
EVENT = {"3200": "sterling.order.released", "3700": "sterling.order.shipped", "3700.7777": "sterling.order.fulfilled"}

router = APIRouter()
_tokens: dict[str, float] = {}


def _err(status: int, code: str, description: str) -> JSONResponse:
    return JSONResponse({"errors": [{"ErrorCode": code, "ErrorDescription": description, "httpcode": status}]}, status)


class SterlingError(Exception):
    def __init__(self, status: int, code: str, description: str):
        super().__init__(description)
        self.response = _err(status, code, description)


# ------------------------------------------------------------------ auth
async def _token(request: Request):
    form = dict(await request.form())
    h = request.headers.get("authorization", "")
    client, secret = form.get("client_id", ""), form.get("client_secret", "")
    if h.lower().startswith("basic "):
        try:
            client, _, secret = base64.b64decode(h[6:]).decode().partition(":")
        except ValueError:
            client, secret = "", ""
    if form.get("grant_type") != "client_credentials":
        return JSONResponse({"error": "unsupported_grant_type", "error_description": "Use client_credentials"}, 400)
    if not client or CLIENTS.get(str(client)) != secret:
        return JSONResponse({"error": "invalid_client", "error_description": "Client authentication failed"}, 401)
    tok = secrets.token_urlsafe(32)
    _tokens[tok] = time.time() + TOKEN_TTL
    return {"access_token": tok, "token_type": "Bearer", "expires_in": TOKEN_TTL, "scope": "oms"}


router.add_api_route(BASE + "/oauth/token", _token, methods=["POST"], include_in_schema=True)
router.add_api_route("/sterling/oauth2/token", _token, methods=["POST"], include_in_schema=False)


def expire_all_tokens() -> int:
    """Fault injection: every issued token stops working."""
    n = len(_tokens)
    _tokens.clear()
    return n


def _guard(request: Request) -> JSONResponse | None:
    h = request.headers.get("authorization", "")
    if not h.lower().startswith("bearer ") or _tokens.get(h[7:].strip(), 0) < time.time():
        return _err(401, "YFS10001", "Authentication failed: the access token is missing, invalid or expired")
    return None


# ------------------------------------------------------------------ rendering
def _ist(v) -> str | None:
    if v is None or v == "":
        return None
    if isinstance(v, str):
        v = datetime.fromisoformat(v)
    return v.astimezone(IST).isoformat(timespec="seconds")


def _day(d) -> str | None:
    return f"{d.isoformat()}T00:00:00+05:30" if d else None


def _times(d: dict | None, keys=("StatusDate", "ShipDate", "DeliveryDate", "ExtnReceivedDate")) -> dict:
    return {k: (_ist(v) if k in keys else v) for k, v in (d or {}).items()}


def _qty(v) -> str:
    return f"{Decimal(v):.2f}"


def _line_status(codes: list[str]) -> tuple[str, str, str]:
    """(Status description, min status, max status) as Sterling reports them on an order."""
    live = [c for c in codes if c != "9000"] or codes
    lo, hi = min(live, key=float), max(live, key=float)
    return (STATUS[lo] if lo == hi else f"Partially {STATUS[hi]}"), lo, hi


def _line(r) -> dict:
    out = {
        "OrderLineKey": r.order_line_key,
        "OrderHeaderKey": r.order_header_key,
        "PrimeLineNo": str(r.prime_line_no),
        "SubLineNo": str(r.sub_line_no),
        "LineType": r.line_type,
        "OrderedQty": _qty(r.ordered_qty),
        "Status": STATUS[r.status],
        "MinLineStatus": r.status,
        "MaxLineStatus": r.status,
        "ShipNode": r.ship_node or "",
        "ShipToKey": r.ship_to_key or "",
        "ReqDeliveryDate": _day(r.req_delivery_date),
        "Item": {"ItemID": r.item_id, "ItemShortDesc": r.item_desc, "UnitOfMeasure": r.uom, "ProductClass": r.product_class},
        "OrderStatuses": {"OrderStatus": [_times(h) for h in r.history]},
        "Modifyts": _ist(r.modifyts),
        "Extn": _times(r.extn),
    }
    if r.unit_price is not None:
        out["LinePriceInfo"] = {"UnitPrice": f"{r.unit_price:.2f}", "LineTotal": f"{r.unit_price * r.ordered_qty:.2f}"}
    if r.serial_no:
        out["SerialNo"] = r.serial_no
        out["ReturnReason"] = r.return_reason
        out["ReceivedQty"] = _qty(r.ordered_qty) if r.status == "3900" else "0.00"
    if r.reservation:
        out["OrderLineReservations"] = {"OrderLineReservation": [r.reservation]}
    if r.shipment:
        out["Shipment"] = _times(r.shipment)
    if r.pod:
        out["ProofOfDelivery"] = _times(r.pod)
    return out


def _order(h, lines: list, with_lines: bool = True) -> dict:
    desc, lo, hi = _line_status([ln.status for ln in lines])
    total = sum((ln.unit_price * ln.ordered_qty for ln in lines if ln.unit_price is not None), Decimal(0))
    out = {
        "OrderHeaderKey": h.order_header_key,
        "OrderNo": h.order_no,
        "EnterpriseCode": h.enterprise_code,
        "SellerOrganizationCode": h.enterprise_code,
        "BuyerOrganizationCode": h.buyer_organization_code,
        "DocumentType": h.document_type,
        "OrderType": h.order_type,
        "OrderDate": _ist(h.order_date),
        "Status": desc,
        "MinOrderStatus": lo,
        "MaxOrderStatus": hi,
        "PriceInfo": {"Currency": h.currency, "TotalAmount": f"{total:.2f}"},
        "Createts": _ist(h.createts),
        "Modifyts": _ist(h.modifyts),
        "Extn": _times(h.extn),
    }
    if h.document_type == SALES:
        out |= {"ReqDeliveryDate": _day(h.req_delivery_date), "ShipToKey": h.ship_to_key, "PersonInfoShipTo": h.ship_to}
    else:
        out["ReceivingNode"] = h.receiving_node
    if with_lines:
        out["OrderLines"] = {"TotalNumberOfRecords": str(len(lines)), "OrderLine": [_line(ln) for ln in lines]}
    return out


def _lines_of(conn: Connection, keys: list[str]) -> dict[str, list]:
    out: dict[str, list] = {k: [] for k in keys}
    if keys:
        rows = conn.execute(
            select(t.ORDER_LINE)
            .where(t.ORDER_LINE.c.order_header_key.in_(keys))
            .order_by(t.ORDER_LINE.c.prime_line_no, t.ORDER_LINE.c.sub_line_no)
        ).all()
        for r in rows:
            out[r.order_header_key].append(r)
    return out


def _load(conn: Connection, key: str, lock: bool = False):
    stmt = select(t.ORDER_HEADER).where(t.ORDER_HEADER.c.order_header_key == key)
    h = conn.execute(stmt.with_for_update() if lock else stmt).first()
    if h is None:
        raise SterlingError(404, "YFS10003", f"Order with OrderHeaderKey {key} does not exist")
    return h


# ------------------------------------------------------------------ list (getOrderList)
def _when(params, name: str) -> datetime | None:
    v = params.get(name)
    if not v:
        return None
    try:
        d = datetime.fromisoformat(v.replace("Z", "+00:00"))
    except ValueError as e:
        raise SterlingError(400, "YFC0101", f"{name} must be an ISO 8601 timestamp, e.g. 2026-10-07T09:00:00Z") from e
    return d if d.tzinfo else d.replace(tzinfo=UTC)


def _int(params, name: str, default: int, lo: int, hi: int) -> int:
    v = params.get(name)
    try:
        n = int(v) if v not in (None, "") else default
    except ValueError:
        n = lo - 1
    if not lo <= n <= hi:
        raise SterlingError(400, "YFC0101", f"{name} must be a whole number from {lo} to {hi}")
    return n


def _list(request: Request, doc_type: str | None):
    if (denied := _guard(request)) is not None:
        return denied
    p = request.query_params
    try:
        page = _int(p, "PageNumber", 1, 1, 100000)
        size = _int(p, "PageSize", PAGE_SIZE, 1, MAX_PAGE_SIZE)
        frm, to = _when(p, "FromModifyts"), _when(p, "ToModifyts")
        doc = p.get("DocumentType") or doc_type
        if doc not in (SALES, RETURN):
            raise SterlingError(400, "YFC0101", "DocumentType must be 0001 (sales order) or 0003 (return order)")
    except SterlingError as e:
        return e.response
    h = t.ORDER_HEADER
    stmt = select(h).where(h.c.document_type == doc).order_by(h.c.order_header_key)
    for name, col in (
        ("OrderNo", h.c.order_no),
        ("EnterpriseCode", h.c.enterprise_code),
        ("BuyerOrganizationCode", h.c.buyer_organization_code),
        ("ShipToKey", h.c.ship_to_key),
        ("ReceivingNode", h.c.receiving_node),
    ):
        if v := p.get(name):
            stmt = stmt.where(col == v)
    if frm:
        stmt = stmt.where(h.c.modifyts >= frm)
    if to:
        stmt = stmt.where(h.c.modifyts <= to)
    serial, item = p.get("SerialNo"), p.get("ItemID")
    status = p.get("Status")
    with engine.connect() as conn:
        headers = conn.execute(stmt).all()
        lines = _lines_of(conn, [x.order_header_key for x in headers])
    rows = []
    for x in headers:
        ls = lines[x.order_header_key]
        if serial and not any(serial in (ln.serial_no, ln.allocated_serial) for ln in ls):
            continue
        if item and not any(ln.item_id == item for ln in ls):
            continue
        if status and _line_status([ln.status for ln in ls])[1] != status:
            continue
        rows.append((x, ls))
    chunk = rows[(page - 1) * size : page * size]
    return {
        "TotalOrderList": len(rows),
        "PageNumber": page,
        "PageSize": size,
        "IsLastPage": "Y" if page * size >= len(rows) else "N",
        "LastOrderHeaderKey": chunk[-1][0].order_header_key if chunk else "",
        "Order": [_order(x, ls) for x, ls in chunk],
    }


@router.get(BASE + "/order")
def list_orders(request: Request):
    return _list(request, SALES)


@router.get(BASE + "/return")
def list_returns(request: Request):
    return _list(request, RETURN)


def _one(request: Request, key: str, doc: str | None = None, lines_only: bool = False):
    if (denied := _guard(request)) is not None:
        return denied
    with engine.connect() as conn:
        try:
            h = _load(conn, key)
        except SterlingError as e:
            return e.response
        if doc and h.document_type != doc:
            return _err(404, "YFS10003", f"Return order with OrderHeaderKey {key} does not exist")
        ls = _lines_of(conn, [key])[key]
    if lines_only:
        return {"TotalLineList": len(ls), "OrderLine": [_line(ln) for ln in ls]}
    return _order(h, ls)


@router.get(BASE + "/order/{order_header_key}")
def get_order(order_header_key: str, request: Request):
    return _one(request, order_header_key)


@router.get(BASE + "/order/{order_header_key}/lines")
def get_order_lines(order_header_key: str, request: Request):
    return _one(request, order_header_key, lines_only=True)


@router.get(BASE + "/return/{order_header_key}")
def get_return(order_header_key: str, request: Request):
    return _one(request, order_header_key, RETURN)


# ------------------------------------------------------------------ writes
async def _body(request: Request) -> dict:
    try:
        body = await request.json()
    except ValueError as e:
        raise SterlingError(400, "YFC0101", "The request body must be a JSON object") from e
    if not isinstance(body, dict):
        raise SterlingError(400, "YFC0101", "The request body must be a JSON object")
    return body


def _line_for(conn: Connection, h, body: dict):
    try:
        prime, sub = int(body.get("PrimeLineNo")), int(body.get("SubLineNo") or 1)
    except (TypeError, ValueError) as e:
        raise SterlingError(400, "YFC0101", "PrimeLineNo is required (and SubLineNo, default 1)") from e
    ln = conn.execute(
        select(t.ORDER_LINE)
        .where(
            t.ORDER_LINE.c.order_header_key == h.order_header_key,
            t.ORDER_LINE.c.prime_line_no == prime,
            t.ORDER_LINE.c.sub_line_no == sub,
        )
        .with_for_update()
    ).first()
    if ln is None:
        raise SterlingError(404, "YFS10004", f"Order line {prime}.{sub} does not exist on order {h.order_no}")
    return ln


def _touch(conn: Connection, h, ln, values: dict, history: dict, now: datetime) -> None:
    conn.execute(
        update(t.ORDER_LINE)
        .where(t.ORDER_LINE.c.order_line_key == ln.order_line_key)
        .values(**values, history=[*ln.history, history], modifyts=now)
    )
    conn.execute(update(t.ORDER_HEADER).where(t.ORDER_HEADER.c.order_header_key == h.order_header_key).values(modifyts=now))


def _result(conn: Connection, key: str) -> dict:
    return _order(_load(conn, key), _lines_of(conn, [key])[key])


@router.post(BASE + "/order/allocate")
async def allocate(request: Request):
    if (denied := _guard(request)) is not None:
        return denied
    try:
        body = await _body(request)
        with engine.begin() as conn:
            return _allocate(conn, body, request.headers.get("idempotency-key"))
    except SterlingError as e:
        return e.response
    except IntegrityError:  # a concurrent allocation of the same unit won the unique index
        return _err(409, "YFS10261", f"Unit {body.get('SerialNo')} is already allocated to another order line")


def _allocate(conn: Connection, body: dict, idem: str | None) -> dict:
    serial = str(body.get("SerialNo") or "").strip()
    if not serial:
        raise SterlingError(400, "YFC0101", "SerialNo (the returned unit to allocate) is required")
    key = body.get("OrderHeaderKey")
    if not key:
        no = body.get("OrderNo")
        if not no:
            raise SterlingError(400, "YFC0101", "OrderHeaderKey or OrderNo is required")
        h = t.ORDER_HEADER
        key = conn.execute(
            select(h.c.order_header_key).where(
                h.c.order_no == no,
                h.c.enterprise_code == (body.get("EnterpriseCode") or ENTERPRISE),
                h.c.document_type == (body.get("DocumentType") or SALES),
            )
        ).scalar()
        if key is None:
            raise SterlingError(404, "YFS10003", f"Order {no} does not exist")
    h = _load(conn, key, lock=True)
    if h.document_type != SALES:
        raise SterlingError(400, "YFS10255", f"{h.order_no} is not a sales order; only sales order lines take allocations")
    ln = _line_for(conn, h, body)
    where = f"{h.order_no} line {ln.prime_line_no}"
    if ln.allocated_serial:
        if ln.allocated_serial == serial and idem and idem == ln.idempotency_key:
            return _result(conn, key)  # the same request again: answer as before
        raise SterlingError(409, "YFS10260", f"{where} is already allocated to unit {ln.allocated_serial}")
    if ln.status != "1100":
        raise SterlingError(409, "YFS10270", f"{where} is {STATUS[ln.status]}; only a Created line can be allocated")
    if not ln.accepts_refurbished:
        raise SterlingError(400, "YFS10255", f"{where} requires a new unit; a returned unit cannot be allocated to it")
    rl, rh = t.ORDER_LINE, t.ORDER_HEADER
    unit = conn.execute(
        select(rl, rh.c.receiving_node, rh.c.order_no)
        .join(rh, rh.c.order_header_key == rl.c.order_header_key)
        .where(rl.c.serial_no == serial, rh.c.document_type == RETURN, rl.c.status == "3900")
    ).first()
    if unit is None:
        raise SterlingError(404, "YFS10005", f"No received return holds unit {serial}")
    if unit.item_id != ln.item_id:
        raise SterlingError(400, "YFS10255", f"Unit {serial} is item {unit.item_id}; {where} orders item {ln.item_id}")
    if unit.ordered_qty < ln.ordered_qty:
        raise SterlingError(400, "YFS10255", f"Unit {serial} covers {unit.ordered_qty:.0f}; {where} needs {ln.ordered_qty:.0f}")
    elsewhere = conn.execute(
        select(rl.c.order_header_key, rl.c.prime_line_no, rh.c.order_no)
        .join(rh, rh.c.order_header_key == rl.c.order_header_key)
        .where(rl.c.allocated_serial == serial)
    ).first()
    if elsewhere:
        raise SterlingError(
            409, "YFS10261", f"Unit {serial} is already allocated to {elsewhere.order_no} line {elsewhere.prime_line_no}"
        )
    now = clock.now(conn)
    ship_node = body.get("ShipNode") or unit.receiving_node
    reservation = {
        "ReservationID": f"RSV-{ln.order_line_key[-10:]}",
        "ItemID": ln.item_id,
        "ProductClass": body.get("ProductClass") or "REFURB",
        "SerialNo": serial,
        "Node": ship_node,
        "Quantity": _qty(ln.ordered_qty),
        "ReturnOrderNo": unit.order_no,
        "Reference": str(body.get("Reference") or ""),
    }
    _touch(
        conn,
        h,
        ln,
        {
            "allocated_serial": serial,
            "reservation": reservation,
            "ship_node": ship_node,
            "product_class": reservation["ProductClass"],
            "status": "1500",
            "idempotency_key": idem,
        },
        {"Status": "1500", "StatusDescription": STATUS["1500"], "StatusDate": now.isoformat(), "StatusQty": _qty(ln.ordered_qty)},
        now,
    )
    events.emit(
        conn,
        SOURCE,
        "sterling.order.allocated",
        h.order_header_key,
        {
            "OrderHeaderKey": h.order_header_key,
            "OrderNo": h.order_no,
            "PrimeLineNo": str(ln.prime_line_no),
            "SubLineNo": str(ln.sub_line_no),
            "SerialNo": serial,
            "ShipNode": ship_node,
            "Status": "1500",
            "Reference": reservation["Reference"],
            "AllocationReference": reservation["Reference"],
        },
        now,
    )
    return _result(conn, key)


@router.post(BASE + "/order/{order_header_key}/fulfil")
async def fulfil(order_header_key: str, request: Request):
    if (denied := _guard(request)) is not None:
        return denied
    try:
        body = await _body(request)
        with engine.begin() as conn:
            return _fulfil(conn, order_header_key, body)
    except SterlingError as e:
        return e.response


def _fulfil(conn: Connection, key: str, body: dict) -> dict:
    h = _load(conn, key, lock=True)
    if h.document_type != SALES:
        raise SterlingError(400, "YFS10255", f"{h.order_no} is not a sales order")
    ln = _line_for(conn, h, body)
    where = f"{h.order_no} line {ln.prime_line_no}"
    if ln.status not in NEXT:
        hint = "allocate a unit first" if ln.status == "1100" else "nothing further to fulfil"
        raise SterlingError(409, "YFS10270", f"{where} is {STATUS[ln.status]}; {hint}")
    action, target = NEXT[ln.status]
    asked = str(body.get("Action") or action).upper()
    if asked != action:
        raise SterlingError(409, "YFS10270", f"{where} is {STATUS[ln.status]}; the next action is {action}, not {asked}")
    now = clock.now(conn)
    values: dict = {"status": target}
    allocation_ref = str((ln.reservation or {}).get("Reference") or "")
    data = {
        "OrderHeaderKey": key,
        "OrderNo": h.order_no,
        "PrimeLineNo": str(ln.prime_line_no),
        "SubLineNo": str(ln.sub_line_no),
        "SerialNo": ln.allocated_serial,
        # the caller's reference: this call's own Reference when it sends one, else the allocation's
        "Reference": str(body.get("Reference") or allocation_ref),
        "AllocationReference": allocation_ref,
    }
    if action == "SHIP":
        shipment = {
            "ShipmentNo": f"SHP-{ln.order_line_key[-10:]}",
            "ShipNode": ln.ship_node,
            "SCAC": str(body.get("SCAC") or ""),
            "TrackingNo": str(body.get("TrackingNo") or ""),
            "ShipDate": _when(body, "ShipDate") or now,
        }
        values["shipment"] = {k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in shipment.items()}
        data["Shipment"] = values["shipment"]
    if action == "DELIVER":
        pod = body.get("ProofOfDelivery") or {}
        if not isinstance(pod, dict) or not pod.get("ReceivedBy"):
            raise SterlingError(400, "YFC0101", "ProofOfDelivery.ReceivedBy is required to confirm delivery")
        values["pod"] = {
            "ReceivedBy": str(pod["ReceivedBy"]),
            "DeliveryDate": (_when(pod, "DeliveryDate") or now).isoformat(),
            "PODReference": str(pod.get("PODReference") or ""),
            "Remarks": str(pod.get("Remarks") or ""),
        }
        data["ProofOfDelivery"] = values["pod"]
    _touch(
        conn,
        h,
        ln,
        values,
        {"Status": target, "StatusDescription": STATUS[target], "StatusDate": now.isoformat(), "StatusQty": _qty(ln.ordered_qty)},
        now,
    )
    events.emit(conn, SOURCE, EVENT[target], key, data | {"Status": target}, now)
    return _result(conn, key)
