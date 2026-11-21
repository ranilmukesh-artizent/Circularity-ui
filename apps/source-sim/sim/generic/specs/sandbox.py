"""A sandbox API for connections set up by hand in the Connection Fabric (plan 6, task A3).

    GET /sandbox/{name}/records?limit=&offset=&updated_since=    {"items": [...], "next": <offset or null>, "total": n}
    GET /sandbox/{name}/records/{id}                             one record

Every name serves its own 25 synthetic records (id, sku, description, qty, unit_price, currency, site, updated_at),
derived from the name, so a hand-made source pointing at http://source-sim:8100/sandbox/demo has something real to read.
It asks for no credentials (a credential sent is ignored). Nothing is stored: the records are computed per request.
"""

import hashlib
import re
from datetime import datetime, timedelta

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from sim.mock import Mock
from sim.seed import Seed

COUNT = 25
SITES = ("Pune DC", "Chennai Repair Centre", "Rotterdam Hub", "Houston Depot")
ITEMS = ("Bearing kit", "Drive motor", "Hydraulic pump", "Control board", "Battery pack", "Gearbox", "Sensor module")
AS_OF = datetime.fromisoformat("2026-10-07T09:00:00+00:00")
NAME = re.compile(r"^[a-z0-9][a-z0-9_-]{0,39}$")
router = APIRouter(prefix="/sandbox")


def _h(*parts: object) -> int:
    return int(hashlib.md5("|".join(str(p) for p in parts).encode()).hexdigest()[:8], 16)


def records(name: str) -> list[dict]:
    out = []
    for n in range(1, COUNT + 1):
        out.append(
            {"id": f"{name}-{n:04d}", "sku": f"SKU-{_h(name, n) % 90000 + 10000}",
             "description": ITEMS[_h(name, n, "i") % len(ITEMS)],
             "qty": 1 + _h(name, n, "q") % 40, "unit_price": round(10 + (_h(name, n, "p") % 500000) / 100, 2),
             "currency": ("USD", "EUR", "INR")[_h(name, n, "c") % 3], "site": SITES[_h(name, n, "s") % len(SITES)],
             "updated_at": (AS_OF - timedelta(minutes=_h(name, n, "t") % (30 * 24 * 60))).isoformat()}
        )  # fmt: skip
    return out


def _bad(message: str, status: int = 400) -> JSONResponse:
    return JSONResponse({"error": {"code": "invalid_request" if status == 400 else "not_found", "message": message}}, status)


@router.get("/{name}/records")
def list_records(name: str, request: Request):
    if not NAME.match(name):
        return _bad("A sandbox name is 1 to 40 lower-case letters, digits, - or _.", 404)
    q = request.query_params
    try:
        limit, offset = min(int(q.get("limit", 50)), 200), int(q.get("offset", 0))
        if limit < 1 or offset < 0:
            raise ValueError
    except ValueError:
        return _bad("Invalid paging parameters")
    rows = records(name)
    if "updated_since" in q:
        try:
            since = datetime.fromisoformat(q["updated_since"].replace("Z", "+00:00"))
        except ValueError:
            return _bad("Invalid updated_since")
        rows = [r for r in rows if datetime.fromisoformat(r["updated_at"]) > since]
    page = rows[offset : offset + limit]
    return {"items": page, "next": offset + limit if offset + limit < len(rows) else None, "total": len(rows)}


@router.get("/{name}/records/{record_id}")
def get_record(name: str, record_id: str):
    doc = next((r for r in records(name) if r["id"] == record_id), None) if NAME.match(name) else None
    return doc if doc is not None else _bad(f"record {record_id} not found", 404)


def _ensure(conn, seed: Seed) -> None:  # noqa: ARG001 - nothing stored
    return None


def _reset(conn, seed: Seed) -> dict[str, int]:  # noqa: ARG001 - nothing stored
    return {"records_per_name": COUNT}


MOCK = Mock("sandbox", router, _ensure, _reset, "Sandbox for hand-made connections")
