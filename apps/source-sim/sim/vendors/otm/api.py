"""Oracle Transportation Management mock: HTTP surface (docs/backend-steps.md, B5b). See the package docstring."""

import base64
import re
import secrets
import time
from datetime import UTC, datetime, timedelta
from urllib.parse import quote, urlencode

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import insert, select, update
from sqlalchemy.engine import Connection
from sqlalchemy.exc import IntegrityError

from sim import clock, events, scheduler
from sim.db import engine
from sim.vendors.otm import query
from sim.vendors.otm import tables as t
from sim.vendors.otm.demo import LOCS, lane_cost, transit_h
from sim.vendors.otm.seed import (
    DOMAIN,
    TZ,
    amount,
    dtt,
    gid,
    rate_geo_xid,
    shipment_doc,
    status,
    tracking,
    xid_of,
)

SOURCE = "tms"
HOST = "/otm"
BASES = (HOST + "/logisticsRestApi/resources/v2", HOST + "/logisticsRestApi/resources-int/v2")
USERS = {"NORTHFIELD.DI_CONNECTOR": "otm-demo-password"}  # OTM user (DOMAIN.USER) for Basic auth
CLIENTS = {"di-connector": "tms-demo-secret"}  # OAuth 2.0 client of the identity domain (client credentials)
TOKEN_TTL = 3600
DEFAULT_LIMIT, MAX_LIMIT = 25, 500
MEDIA = "application/vnd.oracle.resource+json"
ID_FIELD = {
    "locations": "locationGid",
    "serviceProviders": "servprovGid",
    "rateOfferings": "rateOfferingGid",
    "xLanes": "xLaneGid",
    "rateGeos": "rateGeoGid",
    "orderReleases": "orderReleaseGid",
    "shipments": "shipmentGid",
}
CHILDREN = {
    "locations": ("roles",),
    "serviceProviders": ("servprovAliases",),
    "rateOfferings": (),
    "xLanes": (),
    "rateGeos": ("costs",),
    "orderReleases": ("refnums", "statuses"),
    "shipments": ("refnums", "stops", "statuses", "orderReleases", "trackingEvents"),
}
TITLES = {400: "Bad Request", 401: "Unauthorized", 403: "Forbidden", 404: "Not Found", 405: "Method Not Allowed"}

router = APIRouter()
_tokens: dict[str, float] = {}


class OtmError(Exception):
    def __init__(self, status_: int, detail: str, code: str | None = None):
        super().__init__(detail)
        self.status, self.detail, self.code = status_, detail, code

    @property
    def response(self) -> JSONResponse:
        return err(self.status, self.detail, self.code)


def err(status_: int, detail: str, code: str | None = None, headers: dict | None = None) -> JSONResponse:
    body = {
        "type": f"https://www.w3.org/Protocols/rfc2616/rfc2616-sec10.html#sec10.4.{status_ - 399}",
        "title": TITLES.get(status_, "Error"),
        "status": status_,
        "detail": detail,
    }
    if code:
        body["o:errorCode"] = code
    return JSONResponse(body, status_, media_type=MEDIA + ";type=error", headers=headers)


# ------------------------------------------------------------------ auth
@router.post(HOST + "/oauth2/v1/token")
async def token(request: Request):
    form = dict(await request.form())
    h = request.headers.get("authorization", "")
    client, secret = form.get("client_id", ""), form.get("client_secret", "")
    if h.lower().startswith("basic "):
        try:
            client, _, secret = base64.b64decode(h[6:]).decode().partition(":")
        except ValueError:
            client, secret = "", ""
    if form.get("grant_type") != "client_credentials":
        return JSONResponse(
            {"error": "unsupported_grant_type", "error_description": "Only client_credentials is allowed for this client"}, 400
        )
    if not client or CLIENTS.get(str(client)) != secret:
        return JSONResponse({"error": "invalid_client", "error_description": "Client authentication failed."}, 401)
    tok = secrets.token_urlsafe(32)
    _tokens[tok] = time.time() + TOKEN_TTL
    return {"access_token": tok, "token_type": "Bearer", "expires_in": TOKEN_TTL}


def _guard(request: Request) -> JSONResponse | None:
    h = request.headers.get("authorization", "")
    challenge = {"WWW-Authenticate": 'Basic realm="OTM"'}
    if h.lower().startswith("basic "):
        try:
            user, _, pw = base64.b64decode(h[6:]).decode().partition(":")
        except ValueError:
            user, pw = "", ""
        if USERS.get(user) == pw:
            return None
        return err(401, "Invalid user name or password.", headers=challenge)
    if h.lower().startswith("bearer "):
        if _tokens.get(h[7:].strip(), 0) >= time.time():
            return None
        return err(
            401, "The access token is invalid or has expired.", headers={"WWW-Authenticate": 'Bearer error="invalid_token"'}
        )
    return err(401, "Authentication is required to access this resource.", headers=challenge)


def expire_all_tokens() -> int:
    n = len(_tokens)
    _tokens.clear()
    return n


# ------------------------------------------------------------------ rendering
def _stamp(d: datetime) -> dict:
    """insertDate / updateDate: UTC, to the millisecond (the delta filter compares exactly what is shown)."""
    return {"value": d.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z"), "timezone": "UTC"}


def _collection(items: list[dict], href: str) -> dict:
    return {
        "items": items,
        "count": len(items),
        "hasMore": False,
        "limit": len(items),
        "offset": 0,
        "links": [{"rel": "self", "href": href}],
    }


def _href(request: Request, base: str, resource: str, g: str, child: str | None = None) -> str:
    root = str(request.base_url).rstrip("/") + base
    return f"{root}/{resource}/{quote(g, safe='')}" + (f"/{child}" if child else "")


def _event(e) -> dict:
    return {
        "iTransactionNo": e.i_transaction_no,
        **e.doc,
        "insertDate": _stamp(e.insert_date),
        "updateDate": _stamp(e.update_date),
    }


def _render(request: Request, base: str, resource: str, row, tracking_events: list | None = None) -> dict:
    """The full representation, every child collection expanded (filters see it all; _shape trims it)."""
    doc = dict(row.doc)
    self_href = _href(request, base, resource, row.gid)
    for child in CHILDREN[resource]:
        items = [_event(e) for e in tracking_events or []] if child == "trackingEvents" else doc.get(child) or []
        doc[child] = _collection(items, _href(request, base, resource, row.gid, child))
    doc["insertDate"] = _stamp(row.insert_date)
    doc["updateDate"] = _stamp(row.update_date)
    doc["links"] = [{"rel": "self", "href": self_href}, {"rel": "canonical", "href": self_href}] + [
        {"rel": "child", "href": _href(request, base, resource, row.gid, c), "name": c} for c in CHILDREN[resource]
    ]
    return doc


def _shape(doc: dict, resource: str, expand: set[str], fields: set[str] | None) -> dict:
    out = {}
    for k, v in doc.items():
        if k in CHILDREN[resource] and k not in expand and "all" not in expand:
            continue
        if fields is not None and k not in fields and k != "links":
            continue
        out[k] = v
    return out


def _csv(v: str | None) -> set[str]:
    return {x.strip() for x in (v or "").split(",") if x.strip()}


def _int(params, name: str, default: int, lo: int) -> int:
    v = params.get(name)
    if v in (None, ""):
        return default
    if not re.fullmatch(r"\d+", v) or int(v) < lo:
        raise OtmError(
            400, f"Invalid value {v!r} for query parameter {name}: a {'positive' if lo else 'non-negative'} integer is required."
        )
    return int(v)


def _rows(conn: Connection, resource: str):
    return conn.execute(select(t.OBJECT).where(t.OBJECT.c.resource == resource).order_by(t.OBJECT.c.gid)).all()


def _events_by_shipment(conn: Connection, gids: list[str] | None = None) -> dict[str, list]:
    stmt = select(t.TRACKING_EVENT).order_by(t.TRACKING_EVENT.c.i_transaction_no)
    if gids is not None:
        stmt = stmt.where(t.TRACKING_EVENT.c.shipment_gid.in_(gids))
    out: dict[str, list] = {}
    for e in conn.execute(stmt).all():
        out.setdefault(e.shipment_gid, []).append(e)
    return out


def _resource(resource: str) -> None:
    if resource not in ID_FIELD:
        raise OtmError(404, f"The resource {resource} is not found.")


def _sort_key(field: str):
    def key(d: dict):
        v = query._scalar(d.get(field))
        return (v is None, str(v) if not isinstance(v, int | float) else f"{v:020.4f}")

    return key


def _list(request: Request, base: str, resource: str):
    if (denied := _guard(request)) is not None:
        return denied
    p = request.query_params
    try:
        _resource(resource)
        limit = min(_int(p, "limit", DEFAULT_LIMIT, 1), MAX_LIMIT)
        offset = _int(p, "offset", 0, 0)
        try:
            node = query.parse(p.get("q"))
        except query.QueryError as e:
            raise OtmError(400, f"Invalid q parameter: {e}") from e
        expand = _csv(p.get("expand"))
        bad = expand - set(CHILDREN[resource]) - {"all"}
        if bad:
            raise OtmError(400, f"Invalid expand value {sorted(bad)[0]!r} for resource {resource}.")
        fields = _csv(p.get("fields")) or None
        with engine.connect() as conn:
            rows = _rows(conn, resource)
            tev = _events_by_shipment(conn) if resource == "shipments" else {}
        docs = [_render(request, base, resource, r, tev.get(r.gid)) for r in rows]
        try:
            docs = [d for d in docs if query.matches(node, d)]
        except query.QueryError as e:
            raise OtmError(400, f"Invalid q parameter: {e}") from e
        for part in reversed([x.strip() for x in (p.get("orderBy") or "").split(",") if x.strip()]):
            name, _, direction = part.partition(":")
            if direction.lower() not in ("", "asc", "desc"):
                raise OtmError(400, f"Invalid orderBy value {part!r}: use field:asc or field:desc.")
            docs.sort(key=_sort_key(name), reverse=direction.lower() == "desc")
    except OtmError as e:
        return e.response
    page = docs[offset : offset + limit]
    has_more = offset + limit < len(docs)
    here = str(request.url).split("?")[0]
    keep = {k: v for k, v in p.items() if k != "offset"}
    links = [{"rel": "self", "href": str(request.url)}]
    if has_more:
        links.append({"rel": "next", "href": here + "?" + urlencode(keep | {"offset": offset + limit})})
    if offset > 0:
        links.append({"rel": "prev", "href": here + "?" + urlencode(keep | {"offset": max(0, offset - limit)})})
    body: dict = {"items": [_shape(d, resource, expand, fields) for d in page]}
    if p.get("totalResults", "").lower() == "true":
        body["totalResults"] = len(docs)
    body |= {"count": len(page), "hasMore": has_more, "limit": limit, "offset": offset, "links": links}
    return JSONResponse(body, media_type=MEDIA + ";type=collection")


def _get(conn: Connection, resource: str, g: str, lock: bool = False):
    stmt = select(t.OBJECT).where(t.OBJECT.c.resource == resource, t.OBJECT.c.gid == g)
    row = conn.execute(stmt.with_for_update() if lock else stmt).first()
    if row is None:
        raise OtmError(404, f"The {resource} resource with the ID {g} is not found.")
    return row


def _one(request: Request, base: str, resource: str, g: str, child: str | None = None):
    if (denied := _guard(request)) is not None:
        return denied
    try:
        _resource(resource)
        if child and child not in CHILDREN[resource]:
            raise OtmError(404, f"The child resource {child} of {resource} is not found.")
        expand = _csv(request.query_params.get("expand"))
        with engine.connect() as conn:
            row = _get(conn, resource, g)
            tev = _events_by_shipment(conn, [g]).get(g) if resource == "shipments" else None
        doc = _render(request, base, resource, row, tev)
    except OtmError as e:
        return e.response
    if child:
        return JSONResponse(doc[child], media_type=MEDIA + ";type=collection")
    return JSONResponse(
        _shape(doc, resource, expand, _csv(request.query_params.get("fields")) or None), media_type=MEDIA + ";type=singular"
    )


for _base in BASES:

    def _bind(base: str):
        @router.get(base + "/{resource}", include_in_schema=base == BASES[0])
        def list_resource(resource: str, request: Request):
            return _list(request, base, resource)

        @router.get(base + "/{resource}/{g}", include_in_schema=base == BASES[0])
        def get_resource(resource: str, g: str, request: Request):
            return _one(request, base, resource, g)

        @router.get(base + "/{resource}/{g}/{child}", include_in_schema=base == BASES[0])
        def get_child(resource: str, g: str, child: str, request: Request):
            return _one(request, base, resource, g, child)

        @router.post(base + "/orderReleases", include_in_schema=base == BASES[0])
        async def create_order_release(request: Request):
            return await _create_order_release(request, base)

    _bind(_base)


# ------------------------------------------------------------------ writes: order release → planned shipment
def _when(v, name: str) -> datetime | None:
    if v is None:
        return None
    raw = v.get("value") if isinstance(v, dict) else v
    try:
        d = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError as e:
        raise OtmError(400, f"Invalid value for {name}: an ISO 8601 date-time is required.") from e
    return d if d.tzinfo else d.replace(tzinfo=UTC)


def _kg(v) -> float | None:
    if v is None:
        return None
    if not isinstance(v, dict) or not isinstance(v.get("value"), int | float) or v["value"] <= 0:
        raise OtmError(400, 'Invalid value for totalWeight: {"value": <positive number>, "unit": "KG" | "LB"} is required.')
    unit = (v.get("unit") or "KG").upper()
    if unit not in ("KG", "LB"):
        raise OtmError(400, f"Invalid unit of measure {unit} for totalWeight.")
    return v["value"] * (0.45359237 if unit == "LB" else 1)


def _refnums(body: dict) -> list[dict]:
    r = body.get("refnums") or []
    items = r.get("items", []) if isinstance(r, dict) else r
    out = []
    for x in items:
        if not isinstance(x, dict) or not x.get("orderReleaseRefnumQualGid") or x.get("orderReleaseRefnumValue") is None:
            raise OtmError(400, "Each refnum needs orderReleaseRefnumQualGid and orderReleaseRefnumValue.")
        out.append({**x, "orderReleaseRefnumValue": str(x["orderReleaseRefnumValue"]), "domainName": DOMAIN})
    return out


def _next_load_xid(conn: Connection) -> str:
    xids = conn.execute(select(t.OBJECT.c.xid).where(t.OBJECT.c.resource == "shipments", t.OBJECT.c.xid.like("LD-5%"))).scalars()
    n = max((int(x[3:]) for x in xids if x[3:].isdigit()), default=50000)
    return f"LD-{n + 1}"


async def _create_order_release(request: Request, base: str):
    if (denied := _guard(request)) is not None:
        return denied
    try:
        try:
            body = await request.json()
        except ValueError as e:
            raise OtmError(400, "The request body is not valid JSON.") from e
        if not isinstance(body, dict):
            raise OtmError(400, "The request body must be a JSON object.")
        with engine.begin() as conn:
            doc = _book(conn, body)
            row = _get(conn, "orderReleases", doc["orderReleaseGid"])
    except OtmError as e:
        return e.response
    except IntegrityError:
        return err(400, f"The orderReleases resource with the ID {gid(str(body.get('orderReleaseXid')))} already exists.")
    out = _render(request, base, "orderReleases", row)
    href = _href(request, base, "orderReleases", row.gid)
    return JSONResponse(out, 201, media_type=MEDIA + ";type=singular", headers={"Location": href})


def _book(conn: Connection, body: dict) -> dict:
    xid = body.get("orderReleaseXid") or xid_of(body.get("orderReleaseGid"))
    if not xid or not re.fullmatch(r"[A-Za-z0-9_\-.>]{1,50}", str(xid)):
        raise OtmError(400, "orderReleaseXid is required (letters, digits, '-', '_', '.'; at most 50).")
    xid = str(xid)
    org = gid(xid)
    if conn.execute(select(t.OBJECT.c.gid).where(t.OBJECT.c.resource == "orderReleases", t.OBJECT.c.gid == org)).first():
        raise OtmError(400, f"The orderReleases resource with the ID {org} already exists.")
    ends = {}
    for name in ("sourceLocationGid", "destLocationGid"):
        g = body.get(name)
        if not g:
            raise OtmError(400, f"{name} is required.")
        try:
            _get(conn, "locations", g)
        except OtmError as e:
            raise OtmError(400, f"Invalid {name}: location {g} does not exist.") from e
        ends[name] = xid_of(g)
    a, b = ends["sourceLocationGid"], ends["destLocationGid"]
    if a == b:
        raise OtmError(400, "sourceLocationGid and destLocationGid must differ.")
    early = _when(body.get("earlyPickupDate"), "earlyPickupDate")
    late = _when(body.get("lateDeliveryDate"), "lateDeliveryDate")
    if early and late and late <= early:
        raise OtmError(400, "lateDeliveryDate must be after earlyPickupDate.")
    kg = _kg(body.get("totalWeight"))
    qty = body.get("totalShipUnitCount", 1)
    if not isinstance(qty, int) or qty < 1:
        raise OtmError(400, "totalShipUnitCount must be a positive integer.")
    carrier = body.get("servprovGid")
    if carrier:
        try:
            _get(conn, "serviceProviders", carrier)
        except OtmError as e:
            raise OtmError(400, f"Invalid servprovGid: service provider {carrier} does not exist.") from e
    refnums = _refnums(body)
    now = clock.now(conn)
    rate_geo = conn.execute(
        select(t.OBJECT).where(t.OBJECT.c.resource == "rateGeos", t.OBJECT.c.gid == gid(rate_geo_xid(a, b)))
    ).first()
    plannable = rate_geo is not None and rate_geo.doc.get("attribute1") != "PARTNER"
    or_doc = {
        "orderReleaseGid": org,
        "orderReleaseXid": xid,
        "orderReleaseName": body.get("orderReleaseName") or f"{a} to {b}",
        "orderReleaseTypeGid": body.get("orderReleaseTypeGid") or "CUSTOMER_ORDER",
        "sourceLocationGid": gid(a),
        "destLocationGid": gid(b),
        "earlyPickupDate": dtt(early) if early else None,
        "lateDeliveryDate": dtt(late) if late else None,
        "totalWeight": amount(round(kg, 1), "KG") if kg else None,
        "totalShipUnitCount": qty,
        "servprovGid": carrier,
        "refnums": refnums,
        "statuses": [status("PLANNING", "PLANNING_PLANNED - FINAL" if plannable else "PLANNING_NEW")],
        "domainName": DOMAIN,
    }
    conn.execute(
        insert(t.OBJECT).values(resource="orderReleases", gid=org, xid=xid, doc=or_doc, insert_date=now, update_date=now)
    )
    events.emit(conn, SOURCE, "otm.orderRelease.created", xid, {"orderReleaseGid": org, "source": a, "dest": b}, now)
    if not plannable:
        events.emit(
            conn,
            SOURCE,
            "otm.orderRelease.planningFailed",
            xid,
            {"orderReleaseGid": org, "reason": f"No active rate record for lane {a} > {b}"},
            now,
        )
        return or_doc
    # bulk plan (the agent on ORDER RELEASE - CREATED): one direct shipment on the contracted lane rate
    bill_kg = 150 if kg is None else max(1, round(kg))  # from 150 kg a dedicated LCV, below it part load
    km = lane_cost(a, b, bill_kg)["km"]
    etd = early if early and early > now else now + timedelta(hours=2)
    eta = etd + timedelta(hours=transit_h(km))
    sx = _next_load_xid(conn)
    refs = {xid_of(r["orderReleaseRefnumQualGid"]): r["orderReleaseRefnumValue"] for r in refnums}
    refs.setdefault("MOVE_TYPE", "OUTBOUND")
    scac = xid_of(carrier) if carrier else "NLTL"
    sdoc = shipment_doc(
        sx,
        a=a,
        b=b,
        scac=scac,
        kg=bill_kg,
        qty=qty,
        etd=etd,
        eta=eta,
        refnums=refs,
        name=or_doc["orderReleaseName"],
        enroute="NOT STARTED",
        order_release=org,
    )
    if kg is not None:
        sdoc["totalWeight"] = amount(round(kg, 1), "KG")
    if late and eta > late:
        sdoc["attribute3"] = "LATE"  # planned delivery after the order's late delivery date
    sg = sdoc["shipmentGid"]
    conn.execute(insert(t.OBJECT).values(resource="shipments", gid=sg, xid=sx, doc=sdoc, insert_date=now, update_date=now))
    data = shipment_refs(sdoc) | {
        "orderReleaseGid": org,
        "servprovGid": sdoc["servprovGid"],
        "rateGeoGid": sdoc["rateGeoGid"],
        "totalActualCost": sdoc["totalActualCost"],
        "startTime": sdoc["startTime"],
        "endTime": sdoc["endTime"],
    }
    events.emit(conn, SOURCE, "otm.orderRelease.planned", xid, data, now)
    events.emit(conn, SOURCE, "otm.shipment.created", sx, data, now)
    events.emit(conn, SOURCE, "otm.shipment.tenderAccepted", sx, shipment_refs(sdoc) | {"servprovGid": sdoc["servprovGid"]}, now)
    scheduler.schedule(conn, etd, "otm.shipment.depart", {"shipmentGid": sg}, SOURCE)
    scheduler.schedule(conn, eta, "otm.shipment.arrive", {"shipmentGid": sg}, SOURCE)
    scheduler.schedule(conn, eta + timedelta(minutes=30), "otm.shipment.deliver", {"shipmentGid": sg}, SOURCE)
    return or_doc


def shipment_refs(doc: dict) -> dict:
    """What a caller matches a shipment event by: the shipment, the order releases it carries and its refnums."""
    gids = [r["orderReleaseGid"] for r in doc.get("orderReleases") or [] if r.get("orderReleaseGid")]
    return {
        "shipmentGid": doc["shipmentGid"],
        "shipmentXid": doc["shipmentXid"],
        "orderReleaseGids": gids,
        "orderReleaseXids": [xid_of(g) for g in gids],
        "refnums": [
            {"shipmentRefnumQualGid": r["shipmentRefnumQualGid"], "shipmentRefnumValue": r["shipmentRefnumValue"]}
            for r in doc.get("refnums") or []
        ],
    }


# ------------------------------------------------------------------ scheduled: tracking events up to proof of delivery
def _progress(conn: Connection, sg: str, step: str) -> None:
    row = conn.execute(select(t.OBJECT).where(t.OBJECT.c.resource == "shipments", t.OBJECT.c.gid == sg).with_for_update()).first()
    if row is None:
        return  # reset since it was scheduled
    doc = dict(row.doc)
    now = clock.now(conn)
    enroute = next((s["statusValueGid"] for s in doc["statuses"] if s["statusTypeGid"] == gid("ENROUTE")), "")
    order = {"NOT STARTED": 0, "STARTED": 1, "COMPLETED": 2}
    state = enroute.removeprefix(gid("ENROUTE_"))
    a, b = xid_of(doc["sourceLocationGid"]), xid_of(doc["destLocationGid"])
    stops = [dict(s) for s in doc["stops"]]
    extra = {}
    if step == "depart":
        if order.get(state, 0) >= 1:
            return
        code, desc, loc, new_state = "AF", "Departed pickup location", a, "STARTED"
        stops[0]["actualArrival"] = stops[0]["actualDeparture"] = dtt(now)
        doc["startTime"] = dtt(now)
    elif step == "arrive":
        if state == "COMPLETED" or any(s.get("actualArrival") for s in stops[1:]):
            return
        code, desc, loc, new_state = "X1", "Arrived at delivery location", b, "STARTED"
        stops[-1]["actualArrival"] = dtt(now)
    else:
        if state == "COMPLETED":
            return
        code, desc, loc, new_state = "D1", "Completed unloading at delivery location", b, "COMPLETED"
        place = LOCS.get(b, {})
        extra = {
            "externalEventReference": "POD-" + doc["shipmentXid"].removeprefix("LD-"),
            "ssContactName": f"Receiving · {place.get('name') or b}",
        }
        stops[-1].setdefault("actualArrival", dtt(now))
        stops[-1]["actualDeparture"] = dtt(now)
        doc["endTime"] = dtt(now)
    doc["stops"] = stops
    doc["statuses"] = [
        status("ENROUTE", f"ENROUTE_{new_state}") if s["statusTypeGid"] == gid("ENROUTE") else s for s in doc["statuses"]
    ]
    ev = tracking(code, desc, now, loc, sg, **extra)
    conn.execute(insert(t.TRACKING_EVENT).values(shipment_gid=sg, doc=ev, insert_date=now, update_date=now))
    conn.execute(
        update(t.OBJECT).where(t.OBJECT.c.resource == "shipments", t.OBJECT.c.gid == sg).values(doc=doc, update_date=now)
    )
    name = {"depart": "otm.shipment.departed", "arrive": "otm.shipment.arrived", "deliver": "otm.shipment.delivered"}[step]
    events.emit(
        conn,
        SOURCE,
        name,
        doc["shipmentXid"],
        shipment_refs(doc) | {"statusCodeGid": ev["statusCodeGid"], "eventdate": ev["eventdate"], "timezone": TZ} | extra,
        now,
    )


@scheduler.handler("otm.shipment.depart")
def _depart(conn: Connection, payload: dict) -> None:
    _progress(conn, payload["shipmentGid"], "depart")


@scheduler.handler("otm.shipment.arrive")
def _arrive(conn: Connection, payload: dict) -> None:
    _progress(conn, payload["shipmentGid"], "arrive")


@scheduler.handler("otm.shipment.deliver")
def _deliver(conn: Connection, payload: dict) -> None:
    _progress(conn, payload["shipmentGid"], "deliver")
