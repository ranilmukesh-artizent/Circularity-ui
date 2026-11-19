"""Optoro mock: HTTP surface. See the package docstring for the contract and its assumptions."""

import base64
import secrets
import time
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy.engine import Connection

from sim import clock, events, scheduler
from sim.db import engine
from sim.vendors.optoro import seed as db

SOURCE = "rl"
BASE = "/optoro"
CLIENTS = {"di-connector": "rl-demo-secret"}  # OAuth client issued by "Client Success"
API_KEYS = {"rl-demo-key"}  # the per-program api_key some endpoints (inventory_receipt) document
TOKEN_TTL = 90000  # 25 hours, as documented
PER_PAGE, MAX_PER_PAGE = 20, 100
CHANNELS = (
    "b2b",
    "d2c",
    "client_liquidation",
    "destroy",
    "dispose",
    "donate",
    "outlets",
    "recycle",
    "removed",
    "rts",
    "rts_drop_ship",
    "rtv",
    "stock_transfer",
)
PROGRAM_CHANNELS = ("refurbish", "needs_testing")  # program-configured channels of the lease-returns program
CONDITIONS = ("N", "TT", "R", "A", "B", "C", "X")
RETURN_METHODS = ("mail-back", "express-returns", "customer-keep", "home-pickup")
ASN_STATUSES = ("pending", "shipped", "delivered", "cancelled")
FINALIZE_AFTER = {"rts": timedelta(days=1), "refurbish": timedelta(days=3), "recycle": timedelta(days=2)}
DEFAULT_FINALIZE = timedelta(days=2)

router = APIRouter()
_tokens: dict[str, float] = {}


# ------------------------------------------------------------------ errors
class Invalid(Exception):
    def __init__(self, errors: list[tuple[str, str]], message: str = "Validation Failed", status: int = 422):
        super().__init__(message)
        self.errors, self.message, self.status = errors, message, status

    def response(self) -> JSONResponse:
        body: dict = {"message": self.message}
        if self.errors:
            body["errors"] = [{"field": f, "code": c} for f, c in self.errors]
        return JSONResponse(body, self.status)


def _not_found() -> JSONResponse:
    return JSONResponse({"message": "Not Found"}, 404)


def _require(body: dict, fields: tuple[str, ...], prefix: str = "") -> list[tuple[str, str]]:
    return [(prefix + f, "missing_field") for f in fields if body.get(f) in (None, "")]


# ------------------------------------------------------------------ auth (Doorkeeper-style OAuth 2.0)
@router.post(BASE + "/auth/oauth/token")
async def oauth_token(request: Request):
    ctype = request.headers.get("content-type", "")
    try:
        body = await request.json() if "json" in ctype else dict(await request.form())
    except ValueError:
        return JSONResponse({"error": "invalid_request", "error_description": "Malformed request body"}, 400)
    h = request.headers.get("authorization", "")
    client, secret = body.get("client_id"), body.get("client_secret")
    if h.lower().startswith("basic "):
        try:
            client, _, secret = base64.b64decode(h[6:]).decode().partition(":")
        except ValueError:
            client = secret = None
    if body.get("grant_type") != "client_credentials":
        return JSONResponse(
            {"error": "unsupported_grant_type", "error_description": "The authorization grant type is not supported."}, 400
        )
    if not client or CLIENTS.get(str(client)) != secret:
        return JSONResponse(
            {
                "error": "invalid_client",
                "error_description": "Client authentication failed due to unknown client, no client authentication "
                "included, or unsupported authentication method.",
            },
            401,
        )
    tok = secrets.token_urlsafe(24)
    _tokens[tok] = time.time() + TOKEN_TTL
    return {
        "access_token": tok,
        "token_type": "Bearer",
        "expires_in": TOKEN_TTL,
        "scope": "read write",
        "created_at": int(time.time()),
    }


def expire_all_tokens() -> int:
    n = len(_tokens)
    _tokens.clear()
    return n


def _authorized(request: Request) -> bool:
    h = request.headers.get("authorization", "")
    if h.lower().startswith("bearer "):
        return _tokens.get(h[7:].strip(), 0) > time.time()
    return request.headers.get("x-api-key") in API_KEYS


def _unauthorized() -> Response:
    return Response(status_code=401, headers={"WWW-Authenticate": 'Bearer realm="optiturn"'})  # documented: no body


# ------------------------------------------------------------------ list endpoints (drop-ship list conventions)
def _cursor(seq: int) -> str:
    return base64.urlsafe_b64encode(f"seq:{seq}".encode()).decode().rstrip("=")


def _uncursor(v: str) -> int:
    raw = base64.urlsafe_b64decode(v + "=" * (-len(v) % 4)).decode()
    if not raw.startswith("seq:"):
        raise ValueError(v)
    return int(raw[4:])


def _since(v: str) -> datetime:
    d = datetime.fromisoformat(v.replace("Z", "+00:00"))
    return d if d.tzinfo else d.replace(tzinfo=UTC)


def _list(request: Request, name: str, key: str, match=None):
    if not _authorized(request):
        return _unauthorized()
    q = request.query_params
    try:
        per_page = int(q.get("per_page", PER_PAGE))
        if not 1 <= per_page <= MAX_PER_PAGE:
            raise ValueError
    except ValueError:
        return JSONResponse({"message": f"Invalid per_page; must be between 1 and {MAX_PER_PAGE}"}, 422)
    try:
        since = _since(q["updated_at"]) if q.get("updated_at") else None
    except ValueError:
        return JSONResponse({"message": "Invalid updated_at date; must be ISO 8601"}, 422)
    try:
        after = _uncursor(q["offset"]) if q.get("offset") else 0
    except ValueError:
        return JSONResponse({"message": "Invalid offset"}, 422)
    with engine.connect() as conn:
        rows = [r for r in db.rows(conn, name) if (since is None or r.updated > since) and (match is None or match(r.doc, q))]
    total = len(rows)
    rest = [r for r in rows if r.seq > after]
    page = rest[:per_page]
    nxt = None
    if len(rest) > per_page:
        params = dict(q) | {"offset": _cursor(page[-1].seq)}
        query = "&".join(f"{k}={v}" for k, v in params.items())
        path = f"{request.url.path.removeprefix(BASE)}?{query}"
        nxt = {"offset": params["offset"], "path": path, "uri": f"{str(request.base_url).rstrip('/')}{request.url.path}?{query}"}
    return JSONResponse({key: [r.doc for r in page], "next_page": nxt}, headers={"record_count": str(total)})


def _one(request: Request, name: str, id_: str):
    if not _authorized(request):
        return _unauthorized()
    with engine.connect() as conn:
        doc = db.get(conn, name, id_)
    return JSONResponse(doc) if doc else _not_found()


def _filter(*fields):
    """Exact-match query filters over (possibly nested) fields: ?sku=MTR-2041."""

    def match(doc: dict, q) -> bool:
        for param, getter in fields:
            if param in q and q[param] != getter(doc):
                return False
        return True

    return match


def _item0(doc: dict) -> dict:
    return (doc.get("items") or [{}])[0]


def _detail0(doc: dict) -> dict:
    return ((doc.get("cartons") or [{}])[0].get("details") or [{}])[0]


RMA_FILTER = _filter(
    ("status", lambda d: d.get("status")),
    ("sku", lambda d: _item0(d).get("sku")),
    ("secondary_identifier", lambda d: _item0(d).get("secondary_identifier")),
)
LP_FILTER = _filter(("optiturn_lp", lambda d: d.get("optiturn_lp")), ("sku", lambda d: d.get("to_sku") or d.get("sku")))
RECEIPT_FILTER = _filter(
    ("sku", lambda d: d.get("sku")),
    ("asn_number", lambda d: d.get("asn_number")),
    ("rma_identifier", lambda d: (d.get("reference") or {}).get("identifier")),
)
ASN_FILTER = _filter(("status", lambda d: d.get("status")), ("sku", lambda d: _detail0(d).get("sku")))


@router.get(BASE + "/returns/rmas")
def list_rmas(request: Request):
    return _list(request, "rma", "rmas", RMA_FILTER)


@router.get(BASE + "/returns/rmas/{rma_identifier}")
def get_rma(request: Request, rma_identifier: str):
    return _one(request, "rma", rma_identifier)


@router.get(BASE + "/returns/dispositions")
def list_dispositions(request: Request):
    return _list(request, "disposition", "dispositions", LP_FILTER)


@router.get(BASE + "/returns/final_dispositions")
def list_final_dispositions(request: Request):
    return _list(request, "final_disposition", "final_dispositions", LP_FILTER)


@router.get(BASE + "/inventory/inventory_receipts")
def list_receipts(request: Request):
    return _list(request, "receipt", "inventory_receipts", RECEIPT_FILTER)


@router.get(BASE + "/inventory/inventory_receipts/{unit_identifier}")
def get_receipt(request: Request, unit_identifier: str):
    return _one(request, "receipt", unit_identifier)


@router.get(BASE + "/asn/asns")
def list_asns(request: Request):
    return _list(request, "asn", "asns", ASN_FILTER)


@router.get(BASE + "/asn/asns/{asn_number}")
def get_asn(request: Request, asn_number: str):
    return _one(request, "asn", asn_number)


# ------------------------------------------------------------------ writes
async def _body(request: Request) -> dict:
    try:
        body = await request.json()
    except ValueError as e:
        raise Invalid([], "Bad Request: the body is not valid JSON", 400) from e
    if not isinstance(body, dict):
        raise Invalid([], "Bad Request: the body must be a JSON object", 400)
    return body


async def _run(request: Request, fn, ok_status: int, **path):
    if not _authorized(request):
        return _unauthorized()
    try:
        body = await _body(request)
        with engine.begin() as conn:
            out = fn(conn, body, **path)
    except Invalid as e:
        return e.response()
    if isinstance(out, tuple):  # (status, body)
        return JSONResponse(out[1], out[0])
    return JSONResponse(out, ok_status)


def _write(fn, ok_status: int):
    async def handler(request: Request):
        return await _run(request, fn, ok_status)

    return handler


def _create_rma(conn: Connection, body: dict) -> dict:
    errs = _require(body, ("items", "return_method"))
    items = body.get("items")
    if items is not None and (not isinstance(items, list) or not items):
        errs.append(("items", "invalid_type"))
    for i, it in enumerate(items if isinstance(items, list) else []):
        if not isinstance(it, dict):
            errs.append((f"items[{i}]", "invalid_type"))
            continue
        errs += _require(it, ("sku", "order_identifier", "return_reason"), f"items[{i}].")
        if "quantity" in it and (not isinstance(it["quantity"], int) or it["quantity"] < 1):
            errs.append((f"items[{i}].quantity", "invalid"))
    if body.get("return_method") and body["return_method"] not in RETURN_METHODS:
        errs.append(("return_method", "invalid"))
    rid = body.get("rma_identifier")
    if rid and db.get(conn, "rma", rid):
        errs.append(("rma_identifier", "invalid"))
    if errs:
        raise Invalid(errs)
    at = clock.now(conn)
    rid = rid or f"RMA-{57000 + db.next_no(conn, 'rma')}"
    rma = {
        "rma_identifier": rid,
        "status": "CREATED",
        "created_at": db.z(at),
        "updated_at": db.z(at),
        "items": [
            {
                "order_line_item_identifier": str(it.get("order_line_item_identifier") or n),
                "order_identifier": it["order_identifier"],
                "secondary_identifier": it.get("secondary_identifier"),
                "return_reason": it["return_reason"],
                "is_exchange": bool(it.get("exchange_order_identifier")),
                "sku": it["sku"],
                "upc": it.get("upc"),
                "quantity": it.get("quantity", 1),
                "tracking_number": it.get("tracking_number"),
                "package_tracking_status": "PRE_TRANSIT" if it.get("tracking_number") else None,
                "receiving_status": "PENDING",
                "refund_financials": {
                    "estimated_refund_amount_cents": 0,
                    "optoro_refund_amount_cents": 0,
                    "shopper_refund_amount_cents": 0,
                },
                "refund_type": "STANDARD_EXCHANGE" if it.get("exchange_order_identifier") else "REFUND",
                "warehouse_receipt_condition": None,
            }
            | ({"exchange_order_identifier": it["exchange_order_identifier"]} if it.get("exchange_order_identifier") else {})
            for n, it in enumerate(items, 1)
        ],
        "return_method": body["return_method"],
        "return_shipping_cost_cents": int(body.get("return_shipping_cost_cents") or 0),
        "bonus_credit_amount_cents": 0,
        "gift_refund_only": False,
        "warehouse_id": body.get("warehouse_id"),
        "receiving_complete": False,
        "concept": body.get("concept") or db.CONCEPT,
        "customer": {"tags": list((body.get("customer") or {}).get("tags") or [])},
    }
    db.put(conn, "rma", rid, rma, at)
    events.emit(conn, SOURCE, "optoro.rma.created", rid, {"rma": rma}, at)
    return rma


def _validate_asn(body: dict) -> list[tuple[str, str]]:
    errs = _require(body, ("program_identifier", "from", "to", "asn_number", "status", "details_type", "cartons"))
    for side in ("from", "to"):
        if isinstance(body.get(side), dict):
            errs += _require(body[side], ("identifier", "type"), side + ".")
        elif side in body:
            errs.append((side, "invalid_type"))
    if body.get("status") and body["status"] not in ASN_STATUSES:
        errs.append(("status", "invalid"))
    if body.get("details_type") and body["details_type"] not in ("unit", "sku"):
        errs.append(("details_type", "invalid"))
    cartons = body.get("cartons")
    if cartons is not None and (not isinstance(cartons, list) or not cartons):
        errs.append(("cartons", "invalid_type"))
    for i, c in enumerate(cartons if isinstance(cartons, list) else []):
        details = c.get("details") if isinstance(c, dict) else None
        if not isinstance(details, list) or not details:
            errs.append((f"cartons[{i}].details", "missing_field"))
            continue
        for j, d in enumerate(details):
            errs += _require(d, ("line_identifier", "sku", "quantity"), f"cartons[{i}].details[{j}].")
    return errs


def _create_asn(conn: Connection, body: dict) -> tuple[int, dict]:
    errs = _validate_asn(body)
    if body.get("asn_number") and db.get(conn, "asn", body["asn_number"]):
        errs.append(("asn_number", "invalid"))
    if errs:
        raise Invalid(errs)
    at = clock.now(conn)
    asn = dict(body) | {"receptions": 0, "created_at": db.z(at), "updated_at": db.z(at)}
    db.put(conn, "asn", body["asn_number"], asn, at)
    events.emit(conn, SOURCE, "optoro.asn.created", body["asn_number"], {"asn": asn}, at)
    return 202, {"message": "Accepted", "asn_number": body["asn_number"]}


def _update_asn(conn: Connection, body: dict, asn_number: str) -> tuple[int, dict]:
    cur = db.get(conn, "asn", asn_number, lock=True)
    if cur is None:
        raise Invalid([], "Not Found", 404)
    if cur["status"] not in ("pending", "shipped") or cur.get("receptions"):
        raise Invalid([("asn_number", "invalid")], "ASN is no longer active or has receptions and cannot be updated")
    body = body | {"asn_number": asn_number}
    errs = _validate_asn(body)
    if errs:
        raise Invalid(errs)
    at = clock.now(conn)
    asn = dict(body) | {"receptions": 0, "created_at": cur["created_at"], "updated_at": db.z(at)}
    db.put(conn, "asn", asn_number, asn, at)
    events.emit(conn, SOURCE, "optoro.asn.updated", asn_number, {"asn": asn}, at)
    return 202, {"message": "Accepted", "asn_number": asn_number}


def _receive(conn: Connection, body: dict) -> tuple[int, dict]:
    errs = _require(
        body,
        (
            "program_identifier",
            "asn_number",
            "from",
            "to",
            "unit_identifier",
            "sku",
            "initial_condition",
            "initial_channel",
            "ot_user_login",
        ),
    )
    if body.get("initial_condition") and body["initial_condition"] not in CONDITIONS:
        errs.append(("initial_condition", "invalid"))
    if body.get("initial_channel") and body["initial_channel"] not in CHANNELS + PROGRAM_CHANNELS:
        errs.append(("initial_channel", "invalid"))
    if isinstance(body.get("to"), dict):
        errs += _require(body["to"], ("identifier", "type"), "to.")
        if body["to"].get("identifier") is not None and not isinstance(body["to"]["identifier"], int):
            errs.append(("to.identifier", "invalid_type"))
    if errs:
        raise Invalid(errs)
    existing = db.get(conn, "receipt", body["unit_identifier"])
    if existing:
        return 200, existing  # documented: 200 for a receipt already received
    ref = body.get("reference") or {}
    rma = item = None
    if ref.get("type") == "RMA":
        rma = db.get(conn, "rma", ref.get("identifier") or "", lock=True)
        if rma is None:
            raise Invalid([("reference.identifier", "invalid")])
        item = next((i for i in rma["items"] if i["sku"] == body["sku"] and i.get("receiving_status") != "RECEIVED"), None)
        if item is None:
            raise Invalid([("sku", "invalid")], "Validation Failed: the SKU is not open on the RMA")
    at = clock.now(conn)
    fid = body["to"].get("original_identifier") or str(body["to"]["identifier"])
    receipt = dict(body) | {
        "quantity": body.get("quantity", 1),
        "received_at": db.local(at),
        "created_at": db.z(at),
        "updated_at": db.z(at),
    }
    db.put(conn, "receipt", body["unit_identifier"], receipt, at)
    events.emit(conn, SOURCE, "optoro.inventory_receipt.created", body["unit_identifier"], {"inventory_receipt": receipt}, at)
    if rma is not None:
        item["receiving_status"] = "RECEIVED"
        item["package_tracking_status"] = "DELIVERED"
        item["warehouse_receipt_condition"] = body["initial_condition"]
        rma["receiving_complete"] = all(i.get("receiving_status") == "RECEIVED" for i in rma["items"])
        rma["warehouse_id"] = rma.get("warehouse_id") or fid
        rma["updated_at"] = db.z(at)
        db.put(conn, "rma", rma["rma_identifier"], rma, at)
        events.emit(conn, SOURCE, "optoro.rma.updated", rma["rma_identifier"], {"rma": rma}, at)
    asn = db.get(conn, "asn", body["asn_number"], lock=True)
    if asn is not None:
        asn["status"] = "delivered"
        asn["receptions"] = int(asn.get("receptions") or 0) + 1
        asn.setdefault("delivered_at", db.local(at))
        asn["updated_at"] = db.z(at)
        db.put(conn, "asn", body["asn_number"], asn, at)
        events.emit(conn, SOURCE, "optoro.asn.updated", body["asn_number"], {"asn": asn}, at)
    return 201, receipt


def _current(conn: Connection, unit: str) -> tuple[str, str, dict | None]:
    """(channel, condition, latest disposition) of a received unit."""
    receipt = db.get(conn, "receipt", unit)
    latest = None
    for r in db.rows(conn, "disposition"):
        if r.doc["optiturn_lp"] == unit:
            latest = r.doc
    if latest:
        return latest["to_disposition"], latest["to_condition"], latest
    return receipt["initial_channel"], receipt["initial_condition"], None


def _dispose(conn: Connection, body: dict) -> tuple[int, dict]:
    errs = _require(body, ("optiturn_lp", "to_disposition", "to_condition"))
    if body.get("to_disposition") and body["to_disposition"] not in CHANNELS + PROGRAM_CHANNELS:
        errs.append(("to_disposition", "invalid"))
    if body.get("to_condition") and body["to_condition"] not in CONDITIONS:
        errs.append(("to_condition", "invalid"))
    if errs:
        raise Invalid(errs)
    unit = body["optiturn_lp"]
    receipt = db.get(conn, "receipt", unit)
    if receipt is None:
        raise Invalid([("optiturn_lp", "invalid")], "Validation Failed: the unit has not been received")
    if any(r.doc["optiturn_lp"] == unit for r in db.rows(conn, "final_disposition")):
        raise Invalid([("optiturn_lp", "invalid")], "Validation Failed: the unit already has a final disposition")
    channel, cond, _ = _current(conn, unit)
    if channel == body["to_disposition"] and cond == body["to_condition"]:
        raise Invalid([("to_disposition", "invalid")], "Validation Failed: the unit is already in that disposition")
    at = clock.now(conn)
    did = f"DSP-9{db.next_no(conn, 'disposition'):05d}"
    doc = {
        "id": did,
        "from_disposition": channel,
        "to_disposition": body["to_disposition"],
        "timestamp": db.plain(at),
        "location_identifier": body.get("location_identifier") or receipt.get("location_identifier"),
        "warehouse_identifier": receipt["to"].get("original_identifier") or str(receipt["to"]["identifier"]),
        "optiturn_lp": unit,
        "program_identifier": receipt["program_identifier"],
        "upc": receipt.get("upc"),
        "from_condition": cond,
        "to_condition": body["to_condition"],
        "from_sku": receipt["sku"],
        "to_sku": body.get("to_sku") or receipt["sku"],
        "reference_unit_identifier": body.get("reference_unit_identifier")
        or (receipt.get("reference") or {}).get("alternate_identifier"),
        "user_login": body.get("user_login") or "api",
        "updated_at": db.z(at),
    }
    db.put(conn, "disposition", did, doc, at)
    events.emit(conn, SOURCE, "optoro.disposition.updated", unit, {"disposition": doc}, at)
    if body["to_disposition"] != "needs_testing":
        due = at + FINALIZE_AFTER.get(body["to_disposition"], DEFAULT_FINALIZE)
        scheduler.schedule(conn, due, "optoro.finalize", {"id": did}, SOURCE)
    return 201, doc


@scheduler.handler("optoro.finalize")
def _finalize(conn: Connection, payload: dict) -> None:
    """The unit leaves through its channel: a final disposition, unless a later disposition superseded this one."""
    disp = db.get(conn, "disposition", payload["id"])
    if disp is None:
        return
    _, _, latest = _current(conn, disp["optiturn_lp"])
    if latest is None or latest["id"] != disp["id"]:
        return
    if any(r.doc["optiturn_lp"] == disp["optiturn_lp"] for r in db.rows(conn, "final_disposition")):
        return
    at = clock.now(conn)
    fid = f"FD-{db.next_no(conn, 'final_disposition'):06d}"
    doc = {
        "id": fid,
        "disposition": disp["to_disposition"],
        "timestamp": db.plain(at),
        "location_identifier": disp["location_identifier"],
        "warehouse_identifier": disp["warehouse_identifier"],
        "optiturn_lp": disp["optiturn_lp"],
        "program_identifier": disp["program_identifier"],
        "condition": disp["to_condition"],
        "sku": disp["to_sku"],
        "upc": disp.get("upc"),
        "reference_unit_identifier": disp.get("reference_unit_identifier"),
        "shipment_reference_identifier": None,
        "updated_at": db.z(at),
    }
    db.put(conn, "final_disposition", fid, doc, at)
    events.emit(conn, SOURCE, "optoro.final_disposition.created", disp["optiturn_lp"], {"final_disposition": doc}, at)


router.add_api_route(BASE + "/returns/rmas", _write(_create_rma, 201), methods=["POST"])
router.add_api_route(BASE + "/returns/dispositions", _write(_dispose, 201), methods=["POST"])
router.add_api_route(BASE + "/inventory/inventory_receipt", _write(_receive, 201), methods=["POST"])
router.add_api_route(BASE + "/asn/asns", _write(_create_asn, 202), methods=["POST"])


@router.put(BASE + "/asn/asns/{asn_number}")
async def put_asn(request: Request, asn_number: str):
    return await _run(request, _update_asn, 202, asn_number=asn_number)
