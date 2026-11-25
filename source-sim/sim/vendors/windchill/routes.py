"""Windchill REST Services, ProdMgmt domain (OData v4), read-only, as a Windchill server answers them.

    GET  /Windchill/servlet/odata/ProdMgmt/Parts?$top=&$skip=
         -> {"@odata.context", "value": [{"ID", "Number", "Name", "Version", "Iteration", "State": {"Value",
            "Display"}, "UnitCost"}], "@odata.nextLink"?}
    POST /Windchill/servlet/odata/ProdMgmt/Parts('<ID>')/PTC.ProdMgmt.GetPartStructure
         -> {"@odata.context", "value": [{"Number", "Uses": [{"Quantity", "Part": {"Number", "Version"}}]}]}

Paging: `$top` caps the answer and `$skip` skips rows (ordered by ID); the server sends at most PAGE rows and links
the rest with `@odata.nextLink`. Every call needs HTTP Basic authentication (401 with `WWW-Authenticate: Basic`).
Errors are OData error bodies `{"error": {"code", "message"}}`.
"""

import base64
import binascii
from urllib.parse import urlencode

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select

from sim.core.db import engine
from sim.vendors.windchill.models import USAGE, WTPART
from sim.vendors.windchill.seed import STATES

router = APIRouter(prefix="/Windchill/servlet/odata")
USERS = {"di_connector": "Circularity-demo-wc-1"}  # demo credentials, not secrets
PAGE = 25  # the server's page size


def error(status: int, code: str, message: str, headers: dict[str, str] | None = None) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message}}, status_code=status, headers=headers)


def _user(request: Request) -> str | None:
    h = request.headers.get("authorization", "")
    if not h.lower().startswith("basic "):
        return None
    try:
        user, _, pw = base64.b64decode(h[6:], validate=True).decode().partition(":")
    except (binascii.Error, UnicodeDecodeError):
        return None
    return user if USERS.get(user) == pw else None


def _unauthorized() -> JSONResponse:
    return error(401, "401", "Authentication required.", {"WWW-Authenticate": 'Basic realm="Windchill"'})


class BadOption(ValueError):
    """A malformed query option (answered 400)."""


def _whole(request: Request, name: str) -> int | None:
    """A non-negative whole query option, or None when absent."""
    raw = request.query_params.get(name)
    if raw is None:
        return None
    if not raw.isdigit():
        raise BadOption(f"The value '{raw}' of {name} is not a non-negative integer.")
    return int(raw)


def _context(request: Request, what: str) -> str:
    return f"{request.base_url}Windchill/servlet/odata/ProdMgmt/$metadata#{what}"


SOFT = (  # (column, soft attribute): served only when the part has a value (P9-3.3)
    ("rated_life_hours", "RatedLifeHours"), ("criticality_weight", "CriticalityWeight"), ("critical", "Critical"),
    ("end_of_parts_date", "EndOfPartsDate"), ("successor_number", "SuccessorNumber"), ("tool_class", "ToolClass"),
)  # fmt: skip


def _part(r) -> dict:
    soft = {name: getattr(r, col) for col, name in SOFT if getattr(r, col) is not None}
    return {
        "ID": r.id, "Number": r.number, "Name": r.name, "Version": r.version, "Iteration": r.iteration,
        "State": {"Value": r.state, "Display": STATES[r.state]}, "UnitCost": r.unit_cost,
    } | soft  # fmt: skip


@router.get("/ProdMgmt/Parts")
def parts(request: Request):
    if _user(request) is None:
        return _unauthorized()
    try:
        top, skip = _whole(request, "$top"), _whole(request, "$skip") or 0
    except BadOption as e:
        return error(400, "400", str(e))
    want = PAGE if top is None else min(top, PAGE)
    with engine.connect() as conn:
        rows = conn.execute(select(WTPART).order_by(WTPART.c.id).offset(skip).limit(want + 1)).all()
    body: dict = {"@odata.context": _context(request, "Parts"), "value": [_part(r) for r in rows[:want]]}
    left = None if top is None else top - want  # rows of the caller's $top after this page
    if len(rows) > want and (left is None or left > 0):
        q = {"$skip": skip + want} | ({} if left is None else {"$top": left})
        body["@odata.nextLink"] = f"{str(request.url).split('?')[0]}?{urlencode(q)}"
    return body


@router.post("/ProdMgmt/Parts('{pid}')/PTC.ProdMgmt.GetPartStructure")
def part_structure(pid: str, request: Request):
    if _user(request) is None:
        return _unauthorized()
    with engine.connect() as conn:
        root = conn.execute(select(WTPART.c.number).where(WTPART.c.id == pid)).scalar()
        if root is None:
            return error(404, "404", f"Entity with ID '{pid}' not found.")
        uses = conn.execute(
            select(USAGE.c.quantity, WTPART.c.number, WTPART.c.version)
            .join(WTPART, WTPART.c.number == USAGE.c.child_number)
            .where(USAGE.c.parent_id == pid)
            .order_by(USAGE.c.line_number)
        ).all()
    return {
        "@odata.context": _context(request, "Collection(PTC.ProdMgmt.PartStructureItem)"),
        "value": [{"Number": root, "Uses": [{"Quantity": q, "Part": {"Number": n, "Version": v}} for q, n, v in uses]}],
    }
