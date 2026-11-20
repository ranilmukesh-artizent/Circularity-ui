"""Oracle Lease and Finance Management mock: HTTP surface (docs/backend-steps.md, B5b). See the package docstring."""

from datetime import date, datetime

from fastapi import APIRouter, Request
from sqlalchemy import Table, insert, select, update
from sqlalchemy.engine import Connection

from sim import clock, events, scheduler
from sim.db import engine
from sim.vendors.depot_repair.isg import (
    IST,
    Gateway,
    IsgFault,
    dispatch,
    ebs_ts,
    input_parameters,
    output,
    paging,
    parse_ts,
    table,
)
from sim.vendors.oracle_lease import tables as t
from sim.vendors.oracle_lease.seed import day_end

SOURCE = "lease"
PRODUCT = "okl"
GW = Gateway("/oracle-lease", {"DI_CONNECTOR": "lease-demo-password"}, "EBSOKL1")
QUERY, RETURNS = "xxoklleasequery", "oklamassetreturn"
ARS = ("SCHEDULED", "RETURNED")
ART1 = ("TERM_EXPIRATION", "EARLY_TERMINATION", "REPOSSESSION")

router = APIRouter()
GW.routes(router)


def expire_all_tokens() -> int:
    return GW.expire_all_tokens()


def today(conn: Connection) -> date:
    return clock.now(conn).astimezone(IST).date()


# ------------------------------------------------------------------ business rule: contract status at term end
def _set_contract(conn: Connection, doc: dict, status: str, now: datetime, **changes) -> None:
    new = {**doc, "CONTRACT_STATUS": status, **changes}
    conn.execute(
        update(t.CONTRACTS).where(t.CONTRACTS.c.contract_number == doc["CONTRACT_NUMBER"]).values(doc=new, last_update_date=now)
    )
    name = {"EXPIRED": "expired", "EVERGREEN": "evergreen", "TERMINATED": "terminated"}[status]
    events.emit(
        conn,
        SOURCE,
        f"oracle.apps.okl.la.contract.{name}",
        doc["CONTRACT_NUMBER"],
        {"CONTRACT_NUMBER": doc["CONTRACT_NUMBER"], "FROM_STATUS": doc["CONTRACT_STATUS"], "TO_STATUS": status},
        now,
    )


def _all_returned(conn: Connection, contract: str) -> bool:
    rows = conn.execute(select(t.ASSETS.c.doc).where(t.ASSETS.c.doc["LEASE_CONTRACT_ID"].astext == contract)).scalars().all()
    return bool(rows) and all(a["LEASE_STATUS"] == "RETURNED" for a in rows)


def process_term_ends(conn: Connection, as_of: date | None = None) -> list[str]:
    """What OKL's daily expiration run does: a booked contract past its end date expires when all its assets are back,
    else it goes evergreen (month-to-month rent until the assets are returned). Returns the contracts it changed."""
    as_of = as_of or today(conn)
    now = clock.now(conn)
    changed = []
    rows = conn.execute(
        select(t.CONTRACTS).where(t.CONTRACTS.c.doc["CONTRACT_STATUS"].astext == "BOOKED").with_for_update(skip_locked=True)
    ).all()
    for r in rows:
        if date.fromisoformat(r.doc["CONTRACT_END_DATE"]) >= as_of:
            continue
        _set_contract(conn, r.doc, "EXPIRED" if _all_returned(conn, r.contract_number) else "EVERGREEN", now)
        changed.append(r.contract_number)
    return changed


@scheduler.handler("okl.contract.term_end")
def _term_end(conn: Connection, payload: dict) -> None:  # noqa: ARG001 - scheduled handlers take (conn, payload)
    process_term_ends(conn)


# ------------------------------------------------------------------ reads (custom query package XXOKL_LEASE_QUERY)
def _read(request: Request, conn: Connection, tbl: Table, method: str, name: str, filters: tuple[str, ...]):
    p = request.query_params
    since = parse_ts(p.get("P_LAST_UPDATE_DATE_FROM"), "P_LAST_UPDATE_DATE_FROM", QUERY, method)
    start, size = paging(p, QUERY, method)
    rows = [
        {**r.doc, "LAST_UPDATE_DATE": ebs_ts(r.last_update_date)} for r in conn.execute(select(tbl).order_by(*tbl.primary_key))
    ]
    for f in filters:
        if v := p.get("P_" + f):
            rows = [r for r in rows if str(r.get(f)) == v]
    if since:
        rows = [r for r in rows if datetime.fromisoformat(r["LAST_UPDATE_DATE"]) > since]
    chunk = rows[start - 1 : start - 1 + size]
    return output(
        PRODUCT,
        QUERY,
        method,
        {"X_TOTAL_COUNT": str(len(rows)), "X_HAS_MORE": "Y" if start - 1 + size < len(rows) else "N", name: table(name, chunk)},
    )


def get_contracts(request, conn):
    return _read(
        request,
        conn,
        t.CONTRACTS,
        "get_contracts",
        "X_CONTRACTS",
        ("CONTRACT_NUMBER", "ASSET_NUMBER", "LESSEE_NAME", "CONTRACT_STATUS"),
    )


def get_lease_assets(request, conn):
    return _read(
        request,
        conn,
        t.ASSETS,
        "get_lease_assets",
        "X_ASSETS",
        ("ASSET_NUMBER", "LEASE_CONTRACT_ID", "LEASE_STATUS", "OWNER_NAME", "KLE_ID"),
    )


def get_renewals(request, conn):
    return _read(
        request,
        conn,
        t.RENEWALS,
        "get_renewals",
        "X_RENEWALS",
        ("ASSET_NUMBER", "LEASE_OPPORTUNITY_ID", "LEASE_CONTRACT_ID", "STATUS"),
    )


def get_asset_returns(request, conn):
    return _read(request, conn, t.ASSET_RETURNS, "get_asset_returns", "X_ASSET_RETURNS", ("KLE_ID", "ASSET_NUMBER", "ARS_CODE"))


# ------------------------------------------------------------------ writes (OKL_AM_ASSET_RETURN_PUB)
def _error(method: str, msg: str) -> dict:
    return output(PRODUCT, RETURNS, method, {}, "E", [msg])


def _rec(params: dict, method: str) -> dict | str:  # noqa: ARG001 - same signature as the other record builders
    if str(params.get("P_API_VERSION") or "") not in ("1.0", "1"):
        return "FND_AS_INCOMPATIBLE_API_CALL: P_API_VERSION must be 1.0."
    rec = params.get("P_ARTV_REC")
    if not isinstance(rec, dict):
        return "OKL_API_INVALID_RECORD: P_ARTV_REC (the asset return record) is required."
    return rec


def _returned_on(rec: dict, conn: Connection) -> date | str:
    v = rec.get("DATE_RETURNED")
    if not v:
        return today(conn)
    try:
        d = date.fromisoformat(str(v)[:10])
    except ValueError:
        return f"OKL_INVALID_VALUE: DATE_RETURNED {v} is not a valid date."
    if d > today(conn):
        return "OKL_AM_DATE_RETURNED_FUTURE: DATE_RETURNED cannot be in the future."
    return d


def _mark_returned(conn: Connection, asset: dict, ret: dict, on: date, now: datetime) -> None:
    conn.execute(
        update(t.ASSETS)
        .where(t.ASSETS.c.asset_number == asset["ASSET_NUMBER"])
        .values(doc={**asset, "LEASE_STATUS": "RETURNED", "RETURN_DATE": on.isoformat()}, last_update_date=now)
    )
    events.emit(
        conn,
        SOURCE,
        "oracle.apps.okl.am.asset_return.returned",
        asset["ASSET_NUMBER"],
        ret | {"DATE_RETURNED": on.isoformat()},
        now,
    )
    cid = asset.get("LEASE_CONTRACT_ID")
    contract = (
        conn.execute(select(t.CONTRACTS).where(t.CONTRACTS.c.contract_number == cid).with_for_update()).first() if cid else None
    )
    if contract is None:
        return
    status = contract.doc["CONTRACT_STATUS"]
    if status == "EVERGREEN" and _all_returned(conn, cid):
        _set_contract(conn, contract.doc, "TERMINATED", now, DATE_TERMINATED=on.isoformat())
    elif status == "BOOKED":
        end = date.fromisoformat(contract.doc["CONTRACT_END_DATE"])
        if end < today(conn):
            process_term_ends(conn)
        else:
            scheduler.schedule(conn, day_end(end), "okl.contract.term_end", {"CONTRACT_NUMBER": cid}, SOURCE)


def create_asset_return(params: dict, conn: Connection) -> dict:
    """OKL_AM_ASSET_RETURN_PUB.CREATE_ASSET_RETURN: record that a leased asset is coming (SCHEDULED) or came back."""
    m = "create_asset_return"
    rec = _rec(params, m)
    if isinstance(rec, str):
        return _error(m, rec)
    try:
        kle = int(rec.get("KLE_ID"))
    except (TypeError, ValueError):
        return _error(m, "OKL_REQUIRED_VALUE: KLE_ID (the contract asset line) is required.")
    ars = rec.get("ARS_CODE") or "SCHEDULED"
    if ars not in ARS:
        return _error(m, f"OKL_INVALID_VALUE: ARS_CODE {ars} is not valid ({', '.join(ARS)}).")
    art1 = rec.get("ART1_CODE") or "TERM_EXPIRATION"
    if art1 not in ART1:
        return _error(m, f"OKL_INVALID_VALUE: ART1_CODE {art1} is not valid ({', '.join(ART1)}).")
    asset = conn.execute(select(t.ASSETS.c.doc).where(t.ASSETS.c.doc["KLE_ID"].astext == str(kle)).with_for_update()).scalar()
    if asset is None:
        return _error(m, f"OKL_AM_INVALID_ASSET_LINE: No contract asset line {kle}.")
    if conn.execute(select(t.ASSET_RETURNS.c.id).where(t.ASSET_RETURNS.c.kle_id == kle)).first():
        return _error(m, f"OKL_AM_RETURN_EXISTS: Asset {asset['ASSET_NUMBER']} already has an asset return.")
    on = _returned_on(rec, conn) if ars == "RETURNED" else None
    if isinstance(on, str):
        return _error(m, on)
    now = clock.now(conn)
    ret = {
        "KLE_ID": kle,
        "ASSET_NUMBER": asset["ASSET_NUMBER"],
        "CONTRACT_NUMBER": asset.get("LEASE_CONTRACT_ID"),
        "ARS_CODE": ars,
        "ART1_CODE": art1,
        "DATE_RETURNED": on.isoformat() if on else None,
        "COMMENTS": rec.get("COMMENTS"),
    }
    rid = conn.execute(
        insert(t.ASSET_RETURNS).values(kle_id=kle, doc=ret, last_update_date=now).returning(t.ASSET_RETURNS.c.id)
    ).scalar_one()
    events.emit(conn, SOURCE, "oracle.apps.okl.am.asset_return.created", asset["ASSET_NUMBER"], {"ID": rid, **ret}, now)
    if ars == "RETURNED":
        _mark_returned(conn, asset, {"ID": rid, **ret}, on, now)
    return output(PRODUCT, RETURNS, m, {"X_ARTV_REC": {"ID": str(rid), **ret}})


def update_asset_return(params: dict, conn: Connection) -> dict:
    """OKL_AM_ASSET_RETURN_PUB.UPDATE_ASSET_RETURN: a scheduled return is received (ARS_CODE RETURNED)."""
    m = "update_asset_return"
    rec = _rec(params, m)
    if isinstance(rec, str):
        return _error(m, rec)
    stmt = select(t.ASSET_RETURNS).with_for_update()
    if rec.get("ID") not in (None, ""):
        stmt = stmt.where(t.ASSET_RETURNS.c.id == int(rec["ID"]))
    elif rec.get("KLE_ID") not in (None, ""):
        stmt = stmt.where(t.ASSET_RETURNS.c.kle_id == int(rec["KLE_ID"]))
    else:
        return _error(m, "OKL_REQUIRED_VALUE: ID or KLE_ID of the asset return is required.")
    row = conn.execute(stmt).first()
    if row is None:
        return _error(m, "OKL_AM_RETURN_NOT_FOUND: No such asset return.")
    if rec.get("ARS_CODE") != "RETURNED":
        return _error(m, "OKL_INVALID_VALUE: Only ARS_CODE RETURNED can be recorded on an existing return.")
    if row.doc["ARS_CODE"] == "RETURNED":
        return _error(
            m, f"OKL_AM_ASSET_ALREADY_RETURNED: Asset {row.doc['ASSET_NUMBER']} was returned on {row.doc['DATE_RETURNED']}."
        )
    on = _returned_on(rec, conn)
    if isinstance(on, str):
        return _error(m, on)
    now = clock.now(conn)
    ret = {**row.doc, "ARS_CODE": "RETURNED", "DATE_RETURNED": on.isoformat()}
    conn.execute(update(t.ASSET_RETURNS).where(t.ASSET_RETURNS.c.id == row.id).values(doc=ret, last_update_date=now))
    asset = conn.execute(select(t.ASSETS.c.doc).where(t.ASSETS.c.asset_number == ret["ASSET_NUMBER"]).with_for_update()).scalar()
    _mark_returned(conn, asset, {"ID": row.id, **ret}, on, now)
    return output(PRODUCT, RETURNS, m, {"X_ARTV_REC": {"ID": str(row.id), **ret}})


SERVICES = {
    QUERY: {
        "get_contracts": ("GET", get_contracts),
        "get_lease_assets": ("GET", get_lease_assets),
        "get_renewals": ("GET", get_renewals),
        "get_asset_returns": ("GET", get_asset_returns),
    },
    RETURNS: {"create_asset_return": ("POST", create_asset_return), "update_asset_return": ("POST", update_asset_return)},
}


async def _call(alias: str, method: str, request: Request):
    try:
        GW.user(request)
        fn = dispatch(GW, request, alias, method, SERVICES)
        if request.method == "GET":
            with engine.begin() as conn:
                process_term_ends(conn)  # the daily expiration run has caught up before anyone reads
            with engine.connect() as conn:
                return fn(request, conn)
        params = await input_parameters(request, method, alias)
        with engine.begin() as conn:
            return fn(params, conn)
    except IsgFault as e:
        if not e.service:
            e.service, e.operation = alias, method
        return e.response


@router.api_route(GW.rest + "/{alias}/{method}/", methods=["GET", "POST", "PUT", "DELETE"])
async def call(alias: str, method: str, request: Request):
    return await _call(alias, method, request)


@router.api_route(GW.rest + "/{alias}/{method}", methods=["GET", "POST", "PUT", "DELETE"], include_in_schema=False)
async def call_no_slash(alias: str, method: str, request: Request):
    return await _call(alias, method, request)
