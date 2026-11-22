"""Manhattan Active WM mock: HTTP surface. See the package docstring for the contract and its assumptions."""

import base64
import secrets
import time
import uuid
from datetime import timedelta
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy.engine import Connection

from sim.core import clock, events, scheduler
from sim.core.db import engine
from sim.vendors.manhattan import seed as db
from sim.vendors.manhattan.query import QueryError, parse_query

SOURCE = "wms"
BASE = "/manhattan"
CLIENTS = {"di-connector": "wms-demo-secret"}  # OAuth client (HTTP Basic on the token call)
USERS = {"circularity.integration@northfield": "wms-demo-password"}  # password grant users
TOKEN_TTL = 43199
DEFAULT_SIZE, MAX_SIZE = 100, 1000
PICK_AFTER, PACK_AFTER, SHIP_AFTER = timedelta(hours=2), timedelta(hours=1), timedelta(hours=1)
PRODUCT_STATUSES = ("AVAILABLE", "HOLD", "DAMAGED", "QUARANTINE")
ORDER_STATUS = {
    "1000": "Created",
    "3000": "Allocated",
    "7000": "Picked",
    "7200": "Packed",
    "8000": "Shipped",
    "9000": "Canceled",
}
HTTP_NAME = {200: "OK", 400: "BAD_REQUEST", 401: "UNAUTHORIZED", 404: "NOT_FOUND", 409: "CONFLICT"}

router = APIRouter()
_tokens: dict[str, tuple[float, str]] = {}  # token -> (expires, user)


# ------------------------------------------------------------------ envelope and errors
def envelope(request: Request, component: str, data: Any, header: dict | None = None, messages=None, status: int = 200):
    msgs = messages or []
    return JSONResponse(
        {
            "header": header,
            "data": data,
            "messages": {"Message": msgs, "Size": len(msgs)},
            "success": status < 400,
            "exceptions": [],
            "cloudComponent": f"com-manh-cp-{component}",
            "cloudComponentHostName": f"{component}-6f9c7d8b5-x2kqp",
            "requestUri": request.url.path.removeprefix(BASE),
            "rootCause": None if status < 400 else msgs[0]["Description"] if msgs else None,
            "statusCode": HTTP_NAME.get(status, str(status)),
        },
        status,
    )


class ManhError(Exception):
    def __init__(self, status: int, key: str, description: str, *args: str):
        super().__init__(description)
        self.status, self.key, self.description, self.args_ = status, key, description, list(args)

    def message(self) -> dict:
        return {
            "Type": "ERROR",
            "Code": self.key.rsplit(".", 1)[-1],
            "MessageKey": self.key,
            "Description": self.description,
            "Args": self.args_,
        }


def _fail(request: Request, component: str, e: ManhError) -> JSONResponse:
    return envelope(request, component, None, messages=[e.message()], status=e.status)


# ------------------------------------------------------------------ auth (Spring OAuth2 style, as Manhattan Active)
@router.post(BASE + "/oauth/token")
async def token(request: Request):
    form = dict(await request.form())
    h = request.headers.get("authorization", "")
    client, secret = form.get("client_id", ""), form.get("client_secret", "")
    if h.lower().startswith("basic "):
        try:
            client, _, secret = base64.b64decode(h[6:]).decode().partition(":")
        except ValueError:
            client, secret = "", ""
    if not client or CLIENTS.get(str(client)) != secret:
        return JSONResponse({"error": "unauthorized", "error_description": "Bad client credentials"}, 401)
    grant = form.get("grant_type")
    if grant == "password":
        user = str(form.get("username", ""))
        if USERS.get(user) != form.get("password"):
            return JSONResponse({"error": "invalid_grant", "error_description": "Bad credentials"}, 400)
    elif grant == "client_credentials":
        user = str(client)
    else:
        return JSONResponse({"error": "unsupported_grant_type", "error_description": f"Unsupported grant type: {grant}"}, 400)
    tok = secrets.token_hex(16)
    _tokens[tok] = (time.time() + TOKEN_TTL, user)
    out = {
        "access_token": tok,
        "token_type": "bearer",
        "expires_in": TOKEN_TTL,
        "scope": "omni",
        "jti": str(uuid.uuid4()),
    }
    if grant == "password":
        out["refresh_token"] = secrets.token_hex(16)
    return out


def expire_all_tokens() -> int:
    n = len(_tokens)
    _tokens.clear()
    return n


def _user(request: Request) -> str | JSONResponse:
    h = request.headers.get("authorization", "")
    tok = h[7:].strip() if h.lower().startswith("bearer ") else ""
    exp, user = _tokens.get(tok, (0, ""))
    if exp < time.time():
        return JSONResponse(
            {"error": "invalid_token", "error_description": "Invalid access token: " + (tok or "<none>")},
            401,
            headers={"WWW-Authenticate": 'Bearer realm="oauth", error="invalid_token"'},
        )
    return user


def _scope(request: Request, need_location: bool) -> tuple[str, str | None]:
    org = request.headers.get("selectedorganization")
    loc = request.headers.get("selectedlocation")
    if org != db.ORG:
        raise ManhError(
            400,
            "com.manh.cp.common.invalidOrganization",
            f"SelectedOrganization header is missing or invalid: {org!r}",
            str(org),
        )
    if need_location and not loc:
        raise ManhError(400, "com.manh.cp.common.invalidLocation", "SelectedLocation header is required")
    return org, loc


# ------------------------------------------------------------------ search
def _search(conn: Connection, entity: str, body: dict, facility: str | None) -> tuple[list[dict], dict]:
    if not isinstance(body, dict):
        raise ManhError(400, "com.manh.cp.common.invalidRequest", "Request body must be a JSON object")
    try:
        pred = parse_query(body.get("Query"))
    except QueryError as e:
        raise ManhError(400, "com.manh.cp.common.invalidQuery", str(e), str(body.get("Query"))) from e
    try:
        size = int(body.get("Size", DEFAULT_SIZE))
        page = int(body.get("Page", 0))
    except (TypeError, ValueError) as e:
        raise ManhError(400, "com.manh.cp.common.invalidRequest", "Size and Page must be integers") from e
    if size < 1 or size > MAX_SIZE or page < 0:
        raise ManhError(400, "com.manh.cp.common.invalidRequest", f"Size must be 1-{MAX_SIZE} and Page 0 or more")
    docs = [d for d in db.all_docs(conn, entity, facility) if pred(d)]
    for s in reversed(body.get("Sort") or []):
        attr = s.get("attribute") or s.get("Attribute")
        desc = str(s.get("direction") or s.get("Direction") or "asc").lower() == "desc"
        docs.sort(key=lambda d, a=attr: (d.get(a) is None, d.get(a) if d.get(a) is not None else ""), reverse=desc)
    total = len(docs)
    chunk = docs[page * size : (page + 1) * size]
    pages = (total + size - 1) // size
    return chunk, {"totalCount": total, "page": page, "size": size, "totalPages": pages}


def _search_route(path: str, component: str, entity: str, scoped: bool):
    async def handler(request: Request):
        who = _user(request)
        if isinstance(who, JSONResponse):
            return who
        try:
            _, loc = _scope(request, scoped)
            try:
                body = await request.json()
            except ValueError:
                body = {}
            with engine.connect() as conn:
                data, header = _search(conn, entity, body or {}, loc if scoped else None)
        except ManhError as e:
            return _fail(request, component, e)
        return envelope(request, component, data, header)

    router.add_api_route(BASE + path, handler, methods=["POST"], name=f"manhattan_{entity}_search")


_search_route("/facility/api/facility/facility/search", "facility", "facility", False)
_search_route("/item-master/api/item-master/item/search", "item-master", "item", False)
_search_route("/dcinventory/api/dcinventory/location/search", "dcinventory", "location", True)
_search_route("/dcinventory/api/dcinventory/inventory/search", "dcinventory", "inventory", True)
_search_route("/pix/api/pix/pix/search", "pix", "pix", True)
_search_route("/dcinventory/api/dcinventory/reservation/search", "dcinventory", "reservation", True)
_search_route("/dcorder/api/dcorder/order/search", "dcorder", "order", True)
_search_route("/task/api/task/task/search", "task", "task", True)
_search_route("/shipment/api/shipment/shipment/search", "shipment", "shipment", True)


def _get_route(path: str, component: str, entity: str, scoped: bool):
    async def handler(request: Request, key: str):
        who = _user(request)
        if isinstance(who, JSONResponse):
            return who
        try:
            _, loc = _scope(request, scoped)
            with engine.connect() as conn:
                doc = db.get_doc(conn, entity, key)
            if doc is None or (scoped and doc.get("FacilityId") != loc):
                raise ManhError(404, f"com.manh.cp.{component}.{entity}NotFound", f"{entity.title()} {key} not found", key)
        except ManhError as e:
            return _fail(request, component, e)
        return envelope(request, component, doc)

    router.add_api_route(BASE + path, handler, methods=["GET"], name=f"manhattan_{entity}_get")


_get_route("/item-master/api/item-master/item/itemId/{key}", "item-master", "item", False)
_get_route("/dcinventory/api/dcinventory/inventory/inventoryId/{key}", "dcinventory", "inventory", True)
_get_route("/dcinventory/api/dcinventory/reservation/reservationId/{key}", "dcinventory", "reservation", True)
_get_route("/dcorder/api/dcorder/order/orderId/{key}", "dcorder", "order", True)
_get_route("/shipment/api/shipment/shipment/shipmentId/{key}", "shipment", "shipment", True)


# ------------------------------------------------------------------ writes
def _write(component: str, fn):
    """A write endpoint: auth, scope, JSON body, one transaction; ManhError -> Manhattan error envelope."""

    async def handler(request: Request):
        who = _user(request)
        if isinstance(who, JSONResponse):
            return who
        try:
            _, loc = _scope(request, True)
            try:
                body = await request.json()
            except ValueError as e:
                raise ManhError(400, "com.manh.cp.common.invalidRequest", "Request body is not valid JSON") from e
            if not isinstance(body, dict):
                raise ManhError(400, "com.manh.cp.common.invalidRequest", "Request body must be a JSON object")
            with engine.begin() as conn:
                data = fn(conn, body, loc, who)
        except ManhError as e:
            return _fail(request, component, e)
        return envelope(request, component, data)

    return handler


def _num(body: dict, key: str) -> float:
    v = body.get(key)
    if isinstance(v, bool) or not isinstance(v, int | float) or v <= 0:
        raise ManhError(400, "com.manh.cp.common.invalidValue", f"{key} must be a positive number", key)
    return int(v) if float(v).is_integer() else v


def _available(inv: dict) -> float:
    return max(0, inv["OnHand"] - inv["Allocated"]) if inv["ProductStatusId"] == "AVAILABLE" else 0


def _save_inv(conn: Connection, inv: dict, at, user: str) -> dict:
    inv["Available"] = _available(inv)
    return db.put_doc(conn, "inventory", inv, at, user)


def _pix(conn: Connection, at, user: str, inv: dict, kind: str, qty, reason: str, ref: str | None, frm=None, to=None):
    n = db.next_no(conn, "pix")
    doc = {
        "PixId": f"PIX-{90000000 + n}",
        "TransactionType": kind,
        "ReasonCode": reason,
        "ItemId": inv["ItemId"],
        "Quantity": qty,
        "Uom": inv["Uom"],
        "FacilityId": inv["FacilityId"],
        "FromLocationId": frm,
        "ToLocationId": to,
        "InventoryId": inv["InventoryId"],
        "ReferenceId": ref,
        "TransactionTimestamp": db.ts(at),
    }
    return db.put_doc(conn, "pix", doc, at, user)


def _find_inventory(conn: Connection, loc: str, item: str, inventory_id: str | None, qty) -> dict:
    if inventory_id:
        inv = db.get_doc(conn, "inventory", inventory_id, lock=True)
        if inv is None or inv["FacilityId"] != loc:
            raise ManhError(404, "com.manh.cp.dcinventory.inventoryNotFound", f"Inventory {inventory_id} not found at {loc}")
        if inv["ItemId"] != item:
            raise ManhError(400, "com.manh.cp.dcinventory.itemMismatch", f"Inventory {inventory_id} holds {inv['ItemId']}")
        cands = [inv]
    else:
        cands = [d for d in db.all_docs(conn, "inventory", loc) if d["ItemId"] == item]
        if not cands:
            raise ManhError(
                400, "com.manh.cp.dcinventory.noInventory", f"No inventory for item {item} at facility {loc}", item, loc
            )
        cands = [db.get_doc(conn, "inventory", d["InventoryId"], lock=True) for d in cands]
    for inv in cands:
        if inv["ProductStatusId"] == "AVAILABLE" and _available(inv) >= qty:
            return inv
    held = [i["ProductStatusId"] for i in cands if i["ProductStatusId"] != "AVAILABLE"]
    if held and len(held) == len(cands):
        raise ManhError(
            400,
            "com.manh.cp.dcinventory.inventoryNotAvailable",
            f"Inventory for item {item} is in status {held[0]} and cannot be allocated",
            item,
        )
    if any(i["Allocated"] > 0 for i in cands):
        raise ManhError(
            409,
            "com.manh.cp.dcinventory.alreadyAllocated",
            f"Item {item} at {loc} is already allocated; available {sum(_available(i) for i in cands)}, requested {qty}",
            item,
        )
    raise ManhError(
        400,
        "com.manh.cp.dcinventory.insufficientInventory",
        f"Insufficient inventory for item {item} at {loc}: available {sum(_available(i) for i in cands)}, requested {qty}",
        item,
    )


def _reserve(conn: Connection, body: dict, loc: str, user: str) -> dict:
    item = body.get("ItemId")
    if not item:
        raise ManhError(400, "com.manh.cp.common.missingField", "ItemId is required", "ItemId")
    qty = _num(body, "Quantity")
    if db.get_doc(conn, "item", item) is None:
        raise ManhError(404, "com.manh.cp.item-master.itemNotFound", f"Item {item} not found", item)
    if body.get("ReservationId") and db.get_doc(conn, "reservation", body["ReservationId"]):
        raise ManhError(409, "com.manh.cp.dcinventory.duplicateReservation", f"Reservation {body['ReservationId']} exists")
    at = clock.now(conn)
    inv = _find_inventory(conn, loc, item, body.get("InventoryId"), qty)
    inv["Allocated"] += qty
    _save_inv(conn, inv, at, user)
    rid = body.get("ReservationId") or f"R-{77100 + db.next_no(conn, 'reservation')}"
    doc = {
        "ReservationId": rid,
        "ItemId": item,
        "FacilityId": loc,
        "InventoryId": inv["InventoryId"],
        "LocationId": inv["LocationId"],
        "Quantity": qty,
        "Uom": inv["Uom"],
        "ReservationStatus": "RESERVED",
        "OrderId": body.get("OrderId"),
        "ReferenceId": body.get("ReferenceId"),
        "ExpiryTimestamp": body.get("ExpiryTimestamp"),
    }
    db.put_doc(conn, "reservation", doc, at, user)
    events.emit(conn, SOURCE, "manhattan.reservation.created", rid, {"reservation": doc}, at)
    return doc


def _cancel_reservation(conn: Connection, body: dict, loc: str, user: str) -> dict:
    rid = body.get("ReservationId")
    doc = db.get_doc(conn, "reservation", rid or "", lock=True)
    if doc is None or doc["FacilityId"] != loc:
        raise ManhError(404, "com.manh.cp.dcinventory.reservationNotFound", f"Reservation {rid} not found", str(rid))
    if doc["ReservationStatus"] != "RESERVED":
        raise ManhError(
            409,
            "com.manh.cp.dcinventory.invalidReservationStatus",
            f"Reservation {rid} is {doc['ReservationStatus']} and cannot be cancelled",
        )
    at = clock.now(conn)
    inv = db.get_doc(conn, "inventory", doc["InventoryId"], lock=True)
    inv["Allocated"] = max(0, inv["Allocated"] - doc["Quantity"])
    _save_inv(conn, inv, at, user)
    doc["ReservationStatus"] = "CANCELLED"
    db.put_doc(conn, "reservation", doc, at, user)
    events.emit(conn, SOURCE, "manhattan.reservation.cancelled", rid, {"reservation": doc}, at)
    return doc


def _change_status(conn: Connection, body: dict, loc: str, user: str) -> dict:
    iid, new = body.get("InventoryId"), body.get("ProductStatusId")
    if new not in PRODUCT_STATUSES:
        raise ManhError(
            400, "com.manh.cp.dcinventory.invalidProductStatus", f"ProductStatusId must be one of {', '.join(PRODUCT_STATUSES)}"
        )
    inv = db.get_doc(conn, "inventory", iid or "", lock=True)
    if inv is None or inv["FacilityId"] != loc:
        raise ManhError(404, "com.manh.cp.dcinventory.inventoryNotFound", f"Inventory {iid} not found at {loc}", str(iid))
    if new == inv["ProductStatusId"]:
        raise ManhError(409, "com.manh.cp.dcinventory.statusUnchanged", f"Inventory {iid} is already {new}")
    if inv["Allocated"] > 0 and new != "AVAILABLE":
        raise ManhError(
            409,
            "com.manh.cp.dcinventory.inventoryAllocated",
            f"Inventory {iid} has {inv['Allocated']} allocated; release it before changing status",
        )
    at = clock.now(conn)
    old = inv["ProductStatusId"]
    inv["ProductStatusId"] = new
    _save_inv(conn, inv, at, user)
    _pix(conn, at, user, inv, "INVENTORY_STATUS_CHANGE", inv["OnHand"], body.get("ReasonCode") or "STATUS_CHANGE", iid)
    events.emit(conn, SOURCE, "manhattan.inventory.statusChanged", iid, {"inventory": inv, "fromStatus": old}, at)
    return inv


def _task(conn: Connection, at, user: str, order: dict, kind: str, line: dict, status: str = "Released") -> dict:
    n = db.next_no(conn, "task")
    doc = {
        "TaskId": f"T{70000000 + n}",
        "TaskType": kind,
        "Status": status,
        "FacilityId": order["FacilityId"],
        "OrderId": order["OrderId"],
        "ItemId": line["ItemId"],
        "Quantity": line["OrderedQuantity"],
        "SourceLocationId": line.get("_from"),
        "DestinationLocationId": f"{order['FacilityId']}-STAGE" if kind == "PICK" else f"{order['FacilityId']}-DOCK-01",
        "InventoryId": line["InventoryId"],
    }
    return db.put_doc(conn, "task", doc, at, user)


def _save_order(conn: Connection, body: dict, loc: str, user: str) -> dict:
    lines = body.get("OrderLine")
    if not isinstance(lines, list) or not lines:
        raise ManhError(400, "com.manh.cp.common.missingField", "OrderLine is required", "OrderLine")
    otype = body.get("OrderType", "OUTBOUND")
    if otype not in ("OUTBOUND", "TRANSFER"):
        raise ManhError(400, "com.manh.cp.dcorder.invalidOrderType", "OrderType must be OUTBOUND or TRANSFER")
    dest = body.get("DestinationFacilityId")
    if otype == "TRANSFER":
        if not dest or db.get_doc(conn, "facility", dest) is None:
            raise ManhError(400, "com.manh.cp.dcorder.invalidDestination", f"DestinationFacilityId {dest!r} is not a facility")
        if dest == loc:
            raise ManhError(400, "com.manh.cp.dcorder.invalidDestination", "A transfer must leave the facility")
    elif not dest and not body.get("DestinationAddress"):
        raise ManhError(400, "com.manh.cp.common.missingField", "DestinationFacilityId or DestinationAddress is required")
    if body.get("OrderId") and db.get_doc(conn, "order", body["OrderId"]):
        raise ManhError(409, "com.manh.cp.dcorder.duplicateOrder", f"Order {body['OrderId']} already exists", body["OrderId"])
    at = clock.now(conn)
    oid = body.get("OrderId") or f"DO-{30000 + db.next_no(conn, 'order')}"
    out_lines = []
    for i, ln in enumerate(lines, 1):
        item = ln.get("ItemId")
        if not item or db.get_doc(conn, "item", item) is None:
            raise ManhError(404, "com.manh.cp.item-master.itemNotFound", f"Item {item} not found", str(item))
        qty = _num(ln, "OrderedQuantity")
        rid = ln.get("ReservationId")
        if rid:
            rsv = db.get_doc(conn, "reservation", rid, lock=True)
            if rsv is None or rsv["FacilityId"] != loc:
                raise ManhError(404, "com.manh.cp.dcinventory.reservationNotFound", f"Reservation {rid} not found", rid)
            if rsv["ReservationStatus"] != "RESERVED":
                raise ManhError(
                    409, "com.manh.cp.dcinventory.invalidReservationStatus", f"Reservation {rid} is {rsv['ReservationStatus']}"
                )
            if rsv["ItemId"] != item or rsv["Quantity"] < qty:
                raise ManhError(400, "com.manh.cp.dcorder.reservationMismatch", f"Reservation {rid} does not cover the line")
            inv = db.get_doc(conn, "inventory", rsv["InventoryId"], lock=True)
            rsv["ReservationStatus"] = "CONSUMED"
            rsv["OrderId"] = oid
            db.put_doc(conn, "reservation", rsv, at, user)
            events.emit(conn, SOURCE, "manhattan.reservation.consumed", rid, {"reservation": rsv}, at)
        else:
            inv = _find_inventory(conn, loc, item, ln.get("InventoryId"), qty)
            inv["Allocated"] += qty
            _save_inv(conn, inv, at, user)
        out_lines.append(
            {
                "OrderLineId": str(ln.get("OrderLineId") or i),
                "ItemId": item,
                "OrderedQuantity": qty,
                "AllocatedQuantity": qty,
                "ShippedQuantity": 0,
                "Uom": inv["Uom"],
                "InventoryId": inv["InventoryId"],
                "ReservationId": rid,
                "_from": inv["LocationId"],
            }
        )
    order = {
        "OrderId": oid,
        "OrderType": otype,
        "FacilityId": loc,
        "DestinationFacilityId": dest,
        "DestinationAddress": body.get("DestinationAddress"),
        "ExternalReference": body.get("ExternalReference"),
        "CarrierId": body.get("CarrierId"),
        "RequestedShipDate": body.get("RequestedShipDate"),
        "MinFulfillmentStatusId": "3000",
        "MaxFulfillmentStatusId": "3000",
        "FulfillmentStatus": ORDER_STATUS["3000"],
        "OrderLine": out_lines,
        "StatusHistory": [{"StatusId": "3000", "Status": "Allocated", "Timestamp": db.ts(at)}],
    }
    for ln in out_lines:
        _task(conn, at, user, order, "PICK", ln)
    for ln in out_lines:
        ln.pop("_from")
    db.put_doc(conn, "order", order, at, user)
    events.emit(conn, SOURCE, "manhattan.order.allocated", oid, _order_event(order), at)
    scheduler.schedule(conn, at + PICK_AFTER, "manhattan.pick", {"OrderId": oid}, SOURCE)
    return order


router.add_api_route(BASE + "/dcinventory/api/dcinventory/reservation/save", _write("dcinventory", _reserve), methods=["POST"])
router.add_api_route(
    BASE + "/dcinventory/api/dcinventory/reservation/cancel", _write("dcinventory", _cancel_reservation), methods=["POST"]
)
router.add_api_route(
    BASE + "/dcinventory/api/dcinventory/inventory/changeProductStatus",
    _write("dcinventory", _change_status),
    methods=["POST"],
)
router.add_api_route(BASE + "/dcorder/api/dcorder/order/save", _write("dcorder", _save_order), methods=["POST"])


# ------------------------------------------------------------------ scheduled fulfilment: pick -> pack -> ship
def _order_event(order: dict) -> dict:
    """Order event data: the order, plus the ids a caller matches it by at the top level."""
    return {"OrderId": order["OrderId"], "ExternalReference": order.get("ExternalReference"), "order": order}


def _advance(conn: Connection, order: dict, status: str, at) -> None:
    order["MinFulfillmentStatusId"] = order["MaxFulfillmentStatusId"] = status
    order["FulfillmentStatus"] = ORDER_STATUS[status]
    order["StatusHistory"].append({"StatusId": status, "Status": ORDER_STATUS[status], "Timestamp": db.ts(at)})
    db.put_doc(conn, "order", order, at, "system")


def _complete_tasks(conn: Connection, order_id: str, kind: str, at) -> list[dict]:
    done = []
    for t in db.all_docs(conn, "task"):
        if t["OrderId"] == order_id and t["TaskType"] == kind and t["Status"] != "Completed":
            t["Status"] = "Completed"
            t["CompletedTimestamp"] = db.ts(at)
            db.put_doc(conn, "task", t, at, "system")
            done.append(t)
    return done


@scheduler.handler("manhattan.pick")
def _picked(conn: Connection, payload: dict) -> None:
    at = clock.now(conn)
    order = db.get_doc(conn, "order", payload["OrderId"], lock=True)
    if order is None or order["MaxFulfillmentStatusId"] != "3000":
        return
    stage = f"{order['FacilityId']}-STAGE"
    _complete_tasks(conn, order["OrderId"], "PICK", at)
    for ln in order["OrderLine"]:  # the warehouse move: reserve bin -> outbound staging
        inv = db.get_doc(conn, "inventory", ln["InventoryId"], lock=True)
        frm = inv["LocationId"]
        inv["LocationId"] = stage
        _save_inv(conn, inv, at, "system")
        _pix(conn, at, "system", inv, "INVENTORY_MOVE", ln["OrderedQuantity"], "PICK", order["OrderId"], frm, stage)
        _task(conn, at, "system", order, "PACK", ln | {"_from": stage})
    _advance(conn, order, "7000", at)
    events.emit(conn, SOURCE, "manhattan.order.picked", order["OrderId"], _order_event(order), at)
    scheduler.schedule(conn, at + PACK_AFTER, "manhattan.pack", {"OrderId": order["OrderId"]}, SOURCE)


@scheduler.handler("manhattan.pack")
def _packed(conn: Connection, payload: dict) -> None:
    at = clock.now(conn)
    order = db.get_doc(conn, "order", payload["OrderId"], lock=True)
    if order is None or order["MaxFulfillmentStatusId"] != "7000":
        return
    _complete_tasks(conn, order["OrderId"], "PACK", at)
    order["OlpnId"] = f"OLPN{order['OrderId'].split('-')[-1]}01"
    _advance(conn, order, "7200", at)
    events.emit(conn, SOURCE, "manhattan.order.packed", order["OrderId"], _order_event(order), at)
    scheduler.schedule(conn, at + SHIP_AFTER, "manhattan.ship", {"OrderId": order["OrderId"]}, SOURCE)


@scheduler.handler("manhattan.ship")
def _shipped(conn: Connection, payload: dict) -> None:
    at = clock.now(conn)
    order = db.get_doc(conn, "order", payload["OrderId"], lock=True)
    if order is None or order["MaxFulfillmentStatusId"] != "7200":
        return
    for ln in order["OrderLine"]:
        inv = db.get_doc(conn, "inventory", ln["InventoryId"], lock=True)
        q = ln["OrderedQuantity"]
        inv["OnHand"] = max(0, inv["OnHand"] - q)
        inv["Allocated"] = max(0, inv["Allocated"] - q)
        frm = inv["LocationId"]
        _save_inv(conn, inv, at, "system")
        _pix(conn, at, "system", inv, "SHIPMENT", q, order["OrderType"], order["OrderId"], frm, None)
        ln["ShippedQuantity"] = q
    n = db.next_no(conn, "shipment")
    shp = {
        "ShipmentId": f"SHP{order['FacilityId']}{50000 + n}",
        "OrderId": order["OrderId"],
        "FacilityId": order["FacilityId"],
        "DestinationFacilityId": order.get("DestinationFacilityId"),
        "OlpnId": order.get("OlpnId"),
        "CarrierId": order.get("CarrierId"),
        "TrackingNumber": f"{order.get('CarrierId') or 'NLTL'}{at.strftime('%y%m%d')}{n:04d}",
        "ShipmentStatus": "Shipped",
        "ShippedTimestamp": db.ts(at),
        "ExternalReference": order.get("ExternalReference"),
    }
    db.put_doc(conn, "shipment", shp, at, "system")
    order["ShipmentId"] = shp["ShipmentId"]
    _advance(conn, order, "8000", at)
    events.emit(conn, SOURCE, "manhattan.order.shipped", order["OrderId"], _order_event(order) | {"shipment": shp}, at)
