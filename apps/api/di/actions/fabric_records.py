"""Connection Fabric records: Source Tables (tables.update), Manual Import (import.commit) and the Conflict Queue
(conflict.resolve, conflict.escalate).

Ports of the demo's handlers (index.html, `defAction('tables.update' ...)`, `defAction('import.commit' ...)`,
`defAction('conflict.resolve' ...)`, `defAction('conflict.escalate' ...)`) with the checks its pages made before calling
them (ACT.tgAddOk, ACT.tgEditOk, ACT.tgFkOk, ACT.csvValidate), so the server refuses what the page would, with the same
texts. The pipeline has already validated the input types and checked the permission (manageIntegrations).

Workspace collections written here:
- "table_models" (registered by di.screens.integration, seeded from the demo's TBL_MODELS laid out by tgLayout): one
  item per source, {cl, t, fk}. Every op rewrites the source's item, so the Source Tables page, its tiles and the
  Source Map's counts read the change back. Two ops beyond the demo's: `restore` (the page's Undo after a delete puts
  the table and its links back) and `layout` (positions after a drag or Auto Align, which the demo kept in memory for
  the session; here they survive a reload);
- "imports": one item per loaded import (the demo's S.imports), with the rows when the page sends them, tagged manual;
- "conflict_escalations": who escalated which conflict, when (the demo's c.escalated). An escalated conflict stays
  open, as in the demo ("it stays open and dependent routes stay held"), so the canonical store keeps managing it
  (its unique open index, closing it when the sources agree again) and a person can still accept the authority.

Each resolve, escalate and import writes an Event Streams entry, as the demo's pushEvent did.
"""

import re
from typing import Any

from sqlalchemy import text

from di import golden, state
from di.actions.decisions import NOW, push_event
from di.actions.pipeline import CallContext
from di.actions.registry import ActionError, guard, implement

state.register("imports", list)
state.register("conflict_escalations", list)

_REF = golden.load("screens/reference")
TENANTS: list[str] = _REF["TENANTS"]
FACILITIES: list[str] = _REF["FACILITIES"]
_SOURCES = {s["id"]: s for s in golden.load("sources")["sources"]}

COL = re.compile(r"[A-Za-z_][\w$]*")
TABLE = re.compile(r"[A-Za-z][\w$]{1,40}")


# ---------------------------------------------------------------- tables.update
def table_height(t: dict) -> int:
    """tgH: a card's height from its column count."""
    n = len(t["cols"])
    return 34 + min(n, 4) * 19 + (18 if n > 4 else 0) + 38


def _model(ctx: CallContext, src: str) -> dict | None:
    return state.get(ctx.session, "table_models", src, for_update=True)


@guard("tables.update")
def tables_guard(i: dict[str, Any], ctx: CallContext):
    if _model(ctx, i["src"]) is None:
        return "not_found", f"No table model for {i['src']}."
    return None


def _table(m: dict, name: Any) -> dict:
    t = next((y for y in m["t"] if y["n"] == name), None)
    if t is None:
        raise ActionError("not_found", f"No table {name}.")
    return t


def _uses(f: list, name: str) -> bool:
    return f[0].split(".")[0] == name or f[1].split(".")[0] == name


def _ref_ok(m: dict, ref: Any) -> str:
    """A foreign key end, Table.Column, that names a column of a table in the model."""
    tn, _, cn = str(ref).partition(".")
    t = _table(m, tn)
    if cn not in [c[0] for c in t["cols"]]:
        raise ActionError("not_found", f"No column {ref}.")
    return tn


def _add(m: dict, t: dict) -> dict:
    n = str(t.get("n") or "").strip()
    if not TABLE.fullmatch(n):
        raise ActionError("validation_error", "Enter a table name: letters, numbers and underscores.")
    if any(y["n"].lower() == n.lower() for y in m["t"]):
        raise ActionError("duplicate", f"{n} is already in this model")
    cols = [c[0] if isinstance(c, list) and c else c for c in t.get("cols") or []]
    if not cols or not all(isinstance(c, str) and COL.fullmatch(c) for c in cols):
        raise ActionError("validation_error", "Add at least one valid column name.")
    cl = t.get("cl") if any(c[0] == t.get("cl") for c in m["cl"]) else (m["cl"][0][0] if m["cl"] else "")
    new = {
        "cl": cl,
        "cols": [[c, ""] for c in cols],
        "desc": str(t.get("desc") or "").strip() or "Table extracted for evidence.",
        "n": n,
        "rows": t.get("rows") or "—",
    }
    # where the page put it (ACT.tgAddOk: under its cluster, or below everything); computed the same way if missing
    mem = [y for y in m["t"] if y["cl"] == cl]
    x = max(y["x"] for y in mem) if mem else 24
    y0 = (
        max(y["y"] + table_height(y) for y in mem) + 30
        if mem
        else (max(y["y"] + table_height(y) for y in m["t"]) + 60 if m["t"] else 60)
    )
    new["x"] = t["x"] if isinstance(t.get("x"), int | float) else x
    new["y"] = t["y"] if isinstance(t.get("y"), int | float) else y0
    m["t"].append(new)
    return new


def _edit(m: dict, name: Any, t: dict) -> None:
    cur = _table(m, name)
    cols = [str(c).strip() for c in t.get("cols") or [] if str(c).strip()]
    if not cols:
        raise ActionError("validation_error", "Add at least one column.")
    if len({c.lower() for c in cols}) != len(cols):
        raise ActionError("validation_error", "Column names must be unique.")
    if not all(COL.fullmatch(c) for c in cols):
        raise ActionError("validation_error", "Use letters, numbers and underscores only.")
    old = {c[0]: c[1] for c in cur["cols"]}
    cur["cols"] = [[c, old.get(c, "")] for c in cols]
    cur["desc"] = str(t.get("desc") or "").strip() or cur["desc"]
    if t.get("cl") and any(c[0] == t["cl"] for c in m["cl"]):
        cur["cl"] = t["cl"]
    # links to a column that is gone go with it
    m["fk"] = [f for f in m["fk"] if all(r.split(".")[0] != name or r.split(".", 1)[1] in cols for r in f[:2])]


@implement("tables.update")
def tables_update(i: dict[str, Any], ctx: CallContext):
    src, op, t = i["src"], i["op"], i.get("table") or {}
    m = _model(ctx, src)
    if m is None:  # not reached: the guard refused it
        raise ActionError("not_found", f"No table model for {src}.")
    out: dict[str, Any]
    if op == "add":
        out = {"op": "add", "name": _add(m, t)["n"]}
    elif op == "edit":
        _edit(m, i.get("name"), t)
        out = {"op": "edit", "name": i.get("name")}
    elif op == "delete":
        cur = _table(m, i.get("name"))
        k = m["t"].index(cur)
        gone = [f for f in m["fk"] if _uses(f, cur["n"])]
        m["t"].pop(k)
        m["fk"] = [f for f in m["fk"] if not _uses(f, cur["n"])]
        out = {"op": "delete", "name": cur["n"], "fks": len(gone), "table": cur, "index": k, "gone": gone}
    elif op == "restore":  # the page's Undo of a delete
        n = str(t.get("n") or "")
        if any(y["n"].lower() == n.lower() for y in m["t"]):
            raise ActionError("duplicate", f"{n} is already in this model")
        if not TABLE.fullmatch(n) or not t.get("cols"):
            raise ActionError("validation_error", "Enter a table name: letters, numbers and underscores.")
        at = i.get("index")
        k = int(at) if isinstance(at, int | float) else len(m["t"])
        m["t"].insert(max(0, min(k, len(m["t"]))), t)
        for f in i.get("fk") or []:
            if isinstance(f, list) and len(f) >= 2 and not any(y[0] == f[0] and y[1] == f[1] for y in m["fk"]):
                m["fk"].append([f[0], f[1], f[2] if len(f) > 2 and f[2] else "Foreign key link"])
        out = {"op": "restore", "name": n}
    elif op == "fkAdd":
        f = i.get("fk") or []
        if len(f) < 2:
            raise ActionError("validation_error", "Choose a column on each side.")
        if _ref_ok(m, f[0]) == _ref_ok(m, f[1]):
            raise ActionError("validation_error", "Choose two different tables.")
        if any(y[0] == f[0] and y[1] == f[1] for y in m["fk"]):
            raise ActionError("duplicate", "That foreign key already exists")
        row = [f[0], f[1], (f[2] if len(f) > 2 else "") or "Foreign key link"]
        k = i.get("index")  # the page's Undo of fkDel puts the link back where it was
        if isinstance(k, int | float):
            m["fk"].insert(max(0, min(int(k), len(m["fk"]))), row)
        else:
            m["fk"].append(row)
        out = {"op": "fkAdd", "from": f[0], "to": f[1]}
    elif op == "fkDel":
        k = i.get("index")
        if not isinstance(k, int | float) or not 0 <= int(k) < len(m["fk"]):
            raise ActionError("not_found", "No such foreign key.")
        f = m["fk"].pop(int(k))
        out = {"op": "fkDel", "from": f[0], "to": f[1], "fk": f, "index": int(k)}
    elif op == "describe":
        cur = _table(m, i.get("name"))
        if t.get("desc"):
            cur["desc"] = t["desc"]
        cd = t.get("colDesc") or {}
        for c in cur["cols"]:
            if cd.get(c[0]):
                c[1] = cd[c[0]]
        out = {"op": "describe", "name": cur["n"]}
    elif op == "layout":  # positions after a drag or Auto Align
        pos = t.get("pos") or {}
        moved = 0
        for y in m["t"]:
            p = pos.get(y["n"])
            if isinstance(p, list) and len(p) == 2 and all(isinstance(v, int | float) for v in p):
                y["x"], y["y"] = max(0, round(p[0])), max(0, round(p[1]))
                moved += 1
        out = {"op": "layout", "moved": moved}
    else:
        raise ActionError("validation_error", f"Unknown table operation {op}.")
    state.put(ctx.session, "table_models", src, m)
    return out


# ---------------------------------------------------------------- import.commit
def row_errors(r: dict) -> list[str]:
    """ACT.csvValidate's checks on a row the page already normalised (grade A-D, date YYYY-MM-DD)."""
    e = []
    if not re.fullmatch(r"(MTR|PMP|CTL|DRL|BAT|ITE)-\d{4}", str(r.get("asset_id", ""))):
        e.append("asset_id does not match a known class pattern")
    if not re.fullmatch(r"[1-9]\d*", str(r.get("qty", ""))):
        e.append("qty must be a positive whole number")
    if not re.fullmatch(r"[ABCD]", str(r.get("grade", ""))):
        e.append("grade must be A–D")
    if r.get("location") not in FACILITIES:
        e.append(f'unknown location "{r.get("location", "")}"')
    if r.get("owner") not in TENANTS:
        e.append("owner is not a tenant on this account")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(r.get("received", ""))):
        e.append("received must be YYYY-MM-DD")
    return e


@guard("import.commit")
def import_guard(i: dict[str, Any], ctx: CallContext):  # noqa: ARG001 - guards take (input, ctx)
    return ("conflict", "No valid rows to load.") if i["ok"] < 1 else None


KEEP = ("asset_id", "qty", "grade", "location", "owner", "received")


@implement("import.commit", idem=lambda i, ctx: f"imp:{i['hash']}")  # noqa: ARG005 - idem keys take (input, ctx)
def import_commit(i: dict[str, Any], ctx: CallContext):
    """Loads the valid rows as manual evaluation data. The page sends the rows it validated (beyond the demo's counts);
    the server checks them again, and refuses the whole import if any fails: rejected rows are never partially loaded."""
    rows = i.get("rows")
    kept: list[dict] | None = None
    if rows is not None:
        if not isinstance(rows, list) or len(rows) != int(i["ok"]) or not all(isinstance(r, dict) for r in rows):
            raise ActionError("validation_error", f"Expected the {int(i['ok'])} valid rows.")
        for r in rows:
            if bad := row_errors(r):
                raise ActionError(
                    "validation_error", f"{r.get('asset_id') or 'A row'}: {bad[0]}. Rejected rows are never partially loaded."
                )
        kept = [{k: r.get(k) for k in KEEP} for r in rows]
    s = ctx.session
    n = state.next_number(s, "imports", "IMP-", 0)
    item = {
        "id": f"IMP-{n}",
        "at": NOW,
        "ok": int(i["ok"]),
        "err": int(i["err"]),
        "by": _by(ctx),
        "hash": i["hash"],
        "tag": "manual",
        "rows": kept,
    }
    state.add(s, "imports", item["id"], item)
    push_event(
        ctx,
        {
            "dir": "in", "type": "import.evaluated", "caseId": None, "decisionId": None, "approval": None, "ver": None,
            "dest": "Controlled CSV import", "ack": "acknowledged", "key": "imp-" + str(i["hash"])[:6].lower(),
            "note": f"{int(i['ok'])} rows loaded as manual evaluation data; no outbound instruction possible",
        },
        f"import.commit:imp:{i['hash']}",
    )  # fmt: skip
    return {"id": item["id"], "ref": item["id"], "ok": int(i["ok"])}


def _by(ctx: CallContext) -> str:
    return ctx.actor.account.label if ctx.actor.account else "Enterprise system adapter"


# ---------------------------------------------------------------- conflicts
def _name(ctx: CallContext, sid: str) -> str:
    """The source's name as the Connection Fabric shows it (Fabric._source: the demo's name, else its type's label)."""
    if sid in _SOURCES:
        return str(_SOURCES[sid]["name"])
    from di.reads.fabric import type_of

    t = ctx.session.execute(text("SELECT type FROM source_system WHERE id = :i"), {"i": sid}).scalar()
    return str(type_of(t)["label"]) if t else sid


def conflict_row(ctx: CallContext, cid: Any) -> dict:
    """The conflict CF-<n>, locked for the action, with the names the screens show (Fabric._conflict)."""
    try:
        n = int(str(cid).removeprefix("CF-"))
    except ValueError as e:
        raise ActionError("not_found", f"No conflict {cid}.") from e
    row = ctx.session.execute(text("SELECT * FROM conflict WHERE id = :i FOR UPDATE"), {"i": n}).mappings().first()
    if row is None:
        raise ActionError("not_found", f"No conflict {cid}.")
    c = dict(row)
    auth = c["authority"]
    others = sorted(k for k in (c["values"] or {}) if k != auth)
    c["ref"] = f"CF-{n}"
    c["kind"] = c["field"].replace("_", " ").capitalize()
    c["auth_name"] = _name(ctx, auth)
    c["other_name"] = _name(ctx, others[0]) if others else c["auth_name"]
    return c


def resolve(ctx: CallContext, cid: Any) -> dict:
    c = conflict_row(ctx, cid)
    if c["status"] == "resolved":
        raise ActionError("duplicate", f"{c['ref']} is already resolved")
    ctx.session.execute(
        text("UPDATE conflict SET status = 'resolved', closed_at = now(), closed_by = :by, note = :n WHERE id = :i"),
        {"by": ctx.actor.id, "n": f"Resolved in favour of {c['authority']} (the system with authority)", "i": c["id"]},
    )
    push_event(
        ctx,
        {
            "dir": "in", "type": "conflict.resolved", "caseId": None, "decisionId": None, "approval": None, "ver": None,
            "dest": f"{c['auth_name']} vs {c['other_name']}", "ack": "acknowledged", "key": "conf-" + c["ref"].lower(),
            "note": f"{c['kind']} conflict on {c['key']} resolved by source authority {c['auth_name']}",
        },
        "conflict.resolve",
    )  # fmt: skip
    return {
        "id": c["ref"], "ref": c["ref"], "kept": c["authority"], "field": f"{c['model']}.{c['field']}",
        "authority": c["auth_name"], "kind": c["kind"],
    }  # fmt: skip


def escalate(ctx: CallContext, cid: Any) -> dict:
    c = conflict_row(ctx, cid)
    if c["status"] == "resolved":
        raise ActionError("conflict", f"Conflict {c['ref']} is already resolved.")
    if c["status"] == "escalated" or state.get(ctx.session, "conflict_escalations", c["ref"]):
        raise ActionError("duplicate", f"{c['ref']} is already escalated to the data owner")
    state.add(ctx.session, "conflict_escalations", c["ref"], {"id": c["ref"], "by": _by(ctx), "byId": ctx.actor.id, "at": NOW})
    push_event(
        ctx,
        {
            "dir": "out", "type": "conflict.escalated", "caseId": None, "decisionId": None, "approval": None, "ver": None,
            "dest": f"{c['auth_name']} data owner", "ack": "sent", "key": "esc-" + c["ref"].lower(),
            "note": f"{c['kind']} conflict on {c['key']} escalated", "sim": True,
        },
        "conflict.escalate",
    )  # fmt: skip
    return {"id": c["ref"], "ref": c["ref"], "escalated_to": c["authority"]}


def escalations(s) -> dict[str, dict]:
    """Who escalated which conflict (for the Conflict Queue), keyed by CF-<n>."""
    return {e["id"]: e for e in state.items(s, "conflict_escalations")}
