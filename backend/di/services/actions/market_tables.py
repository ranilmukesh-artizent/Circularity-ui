# ruff: noqa: E501 - long lines in the docstring, the action texts and the SQL
"""Market table actions (plan 9, P9-4.2; registry entry I-15; story SD-03): per-market rate cards and decision tables, each
change a new version with its own maker-checker.

    marketTable.list     read    {pack, flow?, market?, name?, org_unit_id?}   every version the actor may see, with who made and checked it
    marketTable.test     read    {id, inputs}                                  a stored version (any status) on the inputs; writes nothing
    marketTable.save     act     {pack, flow, market, name, kind, valid_from, body, id?, valid_to?, currency?, org_unit_id?}
                                                                               a draft: a new version, or an edit of the actor's own draft
    marketTable.submit   act     {id}                                          draft -> submitted
    marketTable.approve  commit  {id}                                          submitted -> approved, not by anyone who saved or submitted it
    marketTable.reject   act     {id, reason}                                  submitted -> rejected, with a reason

`approve` and `reject` are in `FORBIDDEN_ACTIONS` (no agent decides which rates price a repair), `save` and `submit` in
`HELD_FOR_PERSON`. A table of an org unit is reached only by those who may see the org (the tenant boundary); a shared table (no
org unit) is changed only by someone who sees every tenant. Approving closes the version in force the day before the new one starts.
A table is computed rules, not language: nothing here reads or writes free text but the reasons people type.
Needs review by Kinective's Legal team before a customer relies on the prices.
"""

import json
from datetime import date, timedelta
from typing import Any

from sqlalchemy import text

from di.core import policy
from di.repositories import market_tables as repo
from di.repositories.market_tables import TableRow
from di.repositories.orgs import units
from di.services.actions.modeler import _boundary, _org_ok
from di.services.actions.pipeline import CallContext
from di.services.actions.registry import ACTIONS, ActionDef, ActionError, Risk, guard, implement
from di.services.modeler import tables
from di.services.modeler.pack import pack_keys

_MANAGE, _APPROVE = "manageMarketTables", "approve.packs"
_STR = {"req": True, "t": "string"}
_ID = {"id": {"req": True, "t": "number"}}
MAKER_CHECKER = "Maker-checker: you changed this table, so you cannot approve it."
_REASON = {"req": True, "t": "string", "min": 15, "minText": "Add a reason of at least 15 characters."}


def _declare(
    action_id: str, title: str, verb: str, desc: str, risk: Risk, inp: dict[str, dict[str, Any]], perm: str | None
) -> None:
    ACTIONS.setdefault(
        action_id,
        ActionDef(id=action_id, title=title, desc=desc, risk=risk, perm=perm, scope="none", input=inp, verb=verb),
    )


_declare("marketTable.list", "List market tables", "see market tables",
         "The versions of a pack's per-market rate cards and decision tables, with who made and checked each.", "read",
         {"pack": _STR, "flow": {"t": "string"}, "market": {"t": "string"}, "name": {"t": "string"}, "org_unit_id": {"t": "string"}},
         None)  # fmt: skip
_declare("marketTable.test", "Test a market table", "test market tables",
         "Run a stored rate card or decision table on the inputs given. Changes nothing.", "read",
         {**_ID, "inputs": {"req": True, "t": "object"}}, None)  # fmt: skip
_declare("marketTable.save", "Save a market table draft", "draft market tables",
         "Draft a new version of a market's rate card or decision table, or edit your own draft.", "act",
         {"pack": _STR, "flow": _STR, "market": _STR, "name": _STR, "kind": _STR, "valid_from": _STR,
          "body": {"req": True, "t": "object"}, "id": {"t": "number"}, "valid_to": {"t": "string"},
          "currency": {"t": "string"}, "org_unit_id": {"t": "string"}}, _MANAGE)  # fmt: skip
_declare("marketTable.submit", "Submit a market table", "submit market tables",
         "Send a draft market table version to a different person for approval.", "act", _ID, _MANAGE)  # fmt: skip
_declare("marketTable.approve", "Approve a market table", "approve market tables",
         "Approve a submitted market table version; priced lines use it from its start date.", "commit", _ID, _APPROVE)  # fmt: skip
_declare("marketTable.reject", "Reject a market table", "reject market tables",
         "Return a submitted market table version to its maker with a reason.", "act", {**_ID, "reason": _REASON},
         _APPROVE)  # fmt: skip


# ---------------------------------------------------------------- helpers
def _org_refusal(org: str | None, ctx: CallContext, write: bool) -> tuple[str, str] | None:
    """The refusal for an unknown org unit or one outside the actor's units; a shared table (no org) is changed only by
    someone who sees every tenant."""
    if org is None:
        if write and policy.policy(ctx.actor.person).get("tenantScoped"):
            return "tenant_boundary", "Shared market tables are changed by someone who sees every tenant."
        return None
    if org not in units(ctx.session):
        return "not_found", f"No org unit {org}."
    return None if _org_ok(ctx, org) else _boundary(org)


def _own(i: dict[str, Any], ctx: CallContext, write: bool) -> tuple[str, str] | TableRow:
    """The table version named by `id`, or the refusal: unknown, or outside the actor's orgs."""
    row = repo.get(ctx.session, int(i["id"]))
    if row is None:
        return "not_found", f"No market table {i['id']}."
    return _org_refusal(row.org_unit_id, ctx, write) or row


def _status(row: TableRow, want: str, msg: str) -> tuple[str, str] | None:
    return None if row.status == want else ("conflict", msg)


def _label(row: TableRow) -> str:
    return str(tables.TableRef(row.pack, row.flow, row.market, row.name, row.version))


def _date(i: dict[str, Any], key: str) -> date | None | str:
    v = i.get(key)
    if v in (None, ""):
        return None
    try:
        return date.fromisoformat(str(v))
    except ValueError:
        return f'"{key}" must be a date like 2026-11-01.'


def _problems(i: dict[str, Any]) -> str | None:
    """Why the draft may not be saved (the pack's markets and tables, dates, currency, the body's rules), or None."""
    pack = str(i["pack"])
    spec = tables.market_spec(pack) if pack in pack_keys() else None
    if spec is None:
        return f"The pack {pack} has no market tables."
    if i["flow"] != spec.flow:
        return f"The market tables of {pack} belong to the {spec.flow} flow."
    if i["market"] not in spec.markets:
        return f"No market {i['market']}: use {', '.join(spec.markets)}."
    if not spec.has(i["name"]):
        return f"The pack {pack} has no table {i['name']}: use {', '.join(t.name for t in spec.tables)}."
    t = spec.table(i["name"])
    if i["kind"] != t.kind:
        return f"{t.title} is a {t.kind.replace('_', ' ')}."
    start, end = _date(i, "valid_from"), _date(i, "valid_to")
    for d in (start, end):
        if isinstance(d, str):
            return d
    if start is None:
        return 'Missing "valid_from".'
    if isinstance(end, date) and isinstance(start, date) and end < start:
        return "The table cannot end before it starts."
    currency = spec.markets[i["market"]]
    if i.get("currency") not in (None, "", currency):
        return f"{i['market']} prices are in {currency}."
    if t.kind == "rate_card":
        keys = t.versions[0].values[i["market"]] if t.versions else None
        found = tables.values_problems(i["body"], keys)
    else:
        found = tables.validate_table(i["body"], declared=t.inputs)
    return " ".join(found) or None


def _view(r: TableRow) -> dict[str, Any]:
    return {
        "id": r.id, "org_unit_id": r.org_unit_id, "pack": r.pack, "flow": r.flow, "market": r.market, "name": r.name,
        "title": tables.table_title(r.pack, r.name), "label": _label(r), "kind": r.kind, "version": r.version,
        "status": r.status, "valid_from": r.valid_from.isoformat(), "valid_to": r.valid_to.isoformat() if r.valid_to else None,
        "currency": r.currency, "body": r.body, "created_by": r.created_by, "submitted_by": r.submitted_by,
        "approved_by": r.approved_by, "reason": r.reason,
    }  # fmt: skip


def _same(r: TableRow) -> dict[str, Any]:
    return {"o": r.org_unit_id, "p": r.pack, "f": r.flow, "m": r.market, "n": r.name}


_SAME = "org_unit_id IS NOT DISTINCT FROM :o AND pack = :p AND flow = :f AND market = :m AND name = :n"


# ---------------------------------------------------------------- list, test
@guard("marketTable.list")
def list_guard(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | None:
    if i["pack"] not in pack_keys():
        return "not_found", f"No pack {i['pack']}."
    return _org_refusal(i.get("org_unit_id"), ctx, False) if i.get("org_unit_id") else None


@implement("marketTable.list")
def list_tables(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    repo.ensure_seeded(ctx.session, i["pack"])
    org = i.get("org_unit_id") or None
    visible = [org] if org else [u for u in units(ctx.session) if _org_ok(ctx, u)]
    rows = repo.listed(
        ctx.session, i["pack"], i.get("flow") or None, i.get("market") or None, org, name=i.get("name") or None, visible=visible
    )
    spec = tables.market_spec(i["pack"])
    return {
        "pack": i["pack"],
        "markets": spec.markets if spec else {},
        "inputs": {t.name: t.inputs for t in spec.tables} if spec else {},
        "tables": [_view(r) for r in rows],
        "can": {
            "edit": policy.can(ctx.actor.account, _MANAGE, ctx.actor.ctx),
            "approve": policy.can(ctx.actor.account, _APPROVE, ctx.actor.ctx),
        },
    }


@guard("marketTable.test")
def test_guard(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | None:
    row = _own(i, ctx, False)
    return row if isinstance(row, tuple) else None


@implement("marketTable.test")
def test_table(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    row = repo.get(ctx.session, int(i["id"]))
    if row is None:  # not reached: the guard found it
        raise ActionError("not_found", f"No market table {i['id']}.")
    if row.kind == "rate_card":
        return {"id": row.id, "label": _label(row), "outputs": row.body.get("values") or {}, "matched": [], "trace": []}
    try:
        res = tables.ZenEvaluator().evaluate(tables.JdmTable.model_validate(row.body), i["inputs"])
    except (tables.TableError, ValueError) as e:
        raise ActionError("validation_error", str(e)) from e
    return {"id": row.id, "label": _label(row), "outputs": res.outputs, "matched": res.matched, "trace": res.trace}


# ---------------------------------------------------------------- save
@guard("marketTable.save")
def save_guard(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | None:
    if i.get("id") is not None:
        row = _own(i, ctx, True)
        if isinstance(row, tuple):
            return row
        if (row.org_unit_id, row.pack, row.flow, row.market, row.name) != (
            i.get("org_unit_id") or None, i["pack"], i["flow"], i["market"], i["name"]
        ):  # fmt: skip
            return "conflict", f"Table {row.id} is {_label(row)}: draft a new version to change another table."
        if row.status != "draft":
            return "conflict", f"{_label(row)} is {row.status}: only a draft is edited. Draft a new version instead."
        if row.created_by != ctx.actor.id:
            return "conflict", f"{_label(row)} is {row.created_by}'s draft: only they edit it."
    elif bad := _org_refusal(i.get("org_unit_id") or None, ctx, True):
        return bad
    problem = _problems(i)
    return ("validation_error", problem) if problem else None


@implement("marketTable.save")
def save(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    repo.ensure_seeded(ctx.session, i["pack"])
    spec = tables.market_spec(i["pack"])
    currency = spec.markets[i["market"]] if spec else None
    start, end = _date(i, "valid_from"), _date(i, "valid_to")
    body = {"vf": start, "vt": end if isinstance(end, date) else None, "c": currency, "b": json.dumps(i["body"])}
    if i.get("id") is not None:
        row = repo.get(ctx.session, int(i["id"]), for_update=True)
        if row is None or row.status != "draft":  # changed between the guard and this lock
            raise ActionError("conflict", f"Table {i['id']} can no longer be changed.")
        ctx.session.execute(
            text(
                "UPDATE market_table SET valid_from = :vf, valid_to = :vt, currency = :c, body = CAST(:b AS jsonb) WHERE id = :i"
            ),
            {**body, "i": row.id},
        )
        return {
            "id": row.id,
            "version": row.version,
            "status": "draft",
            "label": _label(row),
            "log": f"Saved the draft of {_label(row)}",
        }
    key = {"o": i.get("org_unit_id") or None, "p": i["pack"], "f": i["flow"], "m": i["market"], "n": i["name"]}
    ctx.session.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": "market_table:" + "|".join(str(v) for v in key.values())}
    )
    version = ctx.session.execute(
        text(f"SELECT coalesce(max(version), 0) + 1 FROM market_table WHERE {_SAME}"),  # noqa: S608 - fixed text; values are bound
        key,
    ).scalar_one()
    new_id = ctx.session.execute(
        text(
            "INSERT INTO market_table (org_unit_id, pack, flow, market, name, kind, version, status, valid_from, valid_to, "
            "currency, body, created_by) VALUES (:o, :p, :f, :m, :n, :k, :v, 'draft', :vf, :vt, :c, CAST(:b AS jsonb), :by) "
            "RETURNING id"
        ),
        {**key, **body, "k": i["kind"], "v": version, "by": ctx.actor.id},
    ).scalar_one()
    label = str(tables.TableRef(i["pack"], i["flow"], i["market"], i["name"], version))
    return {"id": new_id, "version": version, "status": "draft", "label": label, "log": f"Saved the draft of {label}"}


# ---------------------------------------------------------------- submit, approve, reject
@guard("marketTable.submit")
def submit_guard(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | None:
    row = _own(i, ctx, True)
    if isinstance(row, tuple):
        return row
    return _status(row, "draft", f"{_label(row)} has no draft to submit.")


@implement("marketTable.submit")
def submit(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    ctx.session.execute(
        text("UPDATE market_table SET status = 'submitted', submitted_by = :a WHERE id = :i"),
        {"a": ctx.actor.id, "i": int(i["id"])},
    )
    return {"id": int(i["id"]), "status": "submitted", "log": f"Submitted market table {i['id']} for approval"}


def _previous(ctx: CallContext, row: TableRow) -> TableRow | None:
    """The approved version of the same table in force when this one starts (it ends the day before)."""
    r = ctx.session.execute(
        text(
            f"SELECT id FROM market_table WHERE {_SAME} AND status = 'approved' AND id <> :i AND valid_from <= :vf "  # noqa: S608 - fixed text; values are bound
            "AND (valid_to IS NULL OR valid_to >= :vf) ORDER BY valid_from DESC, version DESC"
        ),
        {**_same(row), "i": row.id, "vf": row.valid_from},
    ).first()
    return repo.get(ctx.session, r.id) if r else None


@guard("marketTable.approve")
def approve_guard(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | None:
    row = _own(i, ctx, True)
    if isinstance(row, tuple):
        return row
    if bad := _status(row, "submitted", f"{_label(row)} is not waiting for approval."):
        return bad
    if ctx.actor.id in (row.created_by, row.submitted_by):
        return "conflict", MAKER_CHECKER
    prev = _previous(ctx, row)
    if prev is not None and prev.valid_from >= row.valid_from:
        return "conflict", f"{_label(prev)} already starts on {prev.valid_from.isoformat()}: this version must start later."
    return None


@implement("marketTable.approve")
def approve(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    row = repo.get(ctx.session, int(i["id"]), for_update=True)
    if row is None or row.status != "submitted":  # decided by someone else between the guard and this lock
        raise ActionError("conflict", f"Table {i['id']} is not waiting for approval.")
    prev = _previous(ctx, row)
    if prev is not None:
        ctx.session.execute(
            text("UPDATE market_table SET valid_to = :d WHERE id = :i"), {"d": row.valid_from - timedelta(days=1), "i": prev.id}
        )
    ctx.session.execute(
        text("UPDATE market_table SET status = 'approved', approved_by = :a WHERE id = :i"), {"a": ctx.actor.id, "i": row.id}
    )
    log = f"Approved {_label(row)}; it applies from {row.valid_from.isoformat()}"
    return {"id": row.id, "version": row.version, "status": "approved", "log": log}


@guard("marketTable.reject")
def reject_guard(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | None:
    row = _own(i, ctx, True)
    if isinstance(row, tuple):
        return row
    return _status(row, "submitted", f"{_label(row)} is not waiting for approval.")


@implement("marketTable.reject")
def reject(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    ctx.session.execute(
        text("UPDATE market_table SET status = 'rejected', reason = :r WHERE id = :i AND status = 'submitted'"),
        {"r": i["reason"].strip(), "i": int(i["id"])},
    )
    log = f"Returned market table {i['id']} to its maker"
    return {"id": int(i["id"]), "status": "rejected", "reason": i["reason"].strip(), "log": log}
