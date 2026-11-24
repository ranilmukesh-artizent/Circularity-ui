"""Connection Fabric records: Source Tables (tables.update), Manual Import (import.commit) and the Conflict Queue
(conflict.resolve, conflict.escalate).

Ports of the demo's handlers (index.html, `defAction('tables.update' ...)`, `defAction('import.commit' ...)`,
`defAction('conflict.resolve' ...)`, `defAction('conflict.escalate' ...)`) with the checks its pages made before calling
them (ACT.tgAddOk, ACT.tgEditOk, ACT.tgFkOk, ACT.csvValidate), so the server refuses what the page would, with the same
texts. The pipeline has already validated the input types and checked the permission (manageIntegrations).

Workspace collections written here:
- "table_models" (registered by di.repositories.fabric, seeded from the demo's TBL_MODELS laid out by tgLayout): one
  item per source, {cl, t, fk}. Every op rewrites the source's item, so the Source Tables page, its tiles and the
  Source Map's counts read the change back. Two ops beyond the demo's: `restore` (the page's Undo after a delete puts
  the table and its links back) and `layout` (positions after a drag or Auto Align, which the demo kept in memory for
  the session; here they survive a reload);
- "imports": one item per loaded import (the demo's S.imports), with the rows when the page sends them, tagged manual;
- "conflict_escalations": who escalated which conflict, when (the demo's c.escalated). An escalated conflict is
  stored as status 'escalated' (plan 6 B2) and stays active, as in the demo ("it stays open and dependent routes stay
  held"): the screens show it open, the canonical store keeps managing it (one active conflict per field, closed when
  the sources agree again) and a person can still resolve it.

conflict.resolve (plan 6 B2) keeps the authority's value (the demo's), another source's value or one a person enters,
with a reason; the resolution sticks while the sources send the same values (di/services/canonical/store.py).

Each resolve, escalate and import writes an Event Streams entry, as the demo's pushEvent did.
"""

import json
import re
from typing import Any

from sqlalchemy import text

from di.connectors import discover, lifecycle, manual
from di.core import golden, policy, state
from di.services.actions.decisions import NOW, push_event
from di.services.actions.pipeline import CallContext
from di.services.actions.registry import ACTIONS, ActionError, guard, implement
from di.services.canonical import store
from di.services.canonical.schema import MODEL_FIELDS, check_fact, top_field
from di.services.canonical.store import Fact

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
    """The stored model; a configured source with nothing stored yet starts from what it sends (plan 6 B5)."""
    import di.repositories.fabric  # noqa: F401  registers "table_models" (late: fabric imports this module)

    m = state.get(ctx.session, "table_models", src, for_update=True)
    if m is not None and m.get("discovered"):
        found = discover.merge(ctx.session, src, m)
        return None if found is None else found | {"source": src}
    if m is None and src and not lifecycle.is_deleted(ctx.session, src):
        found = discover.materialize(ctx.session, src)
        return None if found is None else found | {"source": src}
    return m


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
        if m.get("discovered") and str(f[2] if len(f) > 2 else "").startswith("Suggested:"):
            m["fkOff"] = [*(m.get("fkOff") or []), [f[0], f[1]]]  # not suggested again (plan 6 B5)
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
    if m.get("discovered") and op in ("add", "edit", "describe", "restore"):  # a person's table is kept as it is (B5)
        name = out["name"]
        for y in m["t"]:
            if y["n"] == name:
                y["manual"] = True
    state.put(ctx.session, "table_models", src, m)
    return out


# ---------------------------------------------------------------- import.commit
def row_errors(r: dict, template: str = "industrial") -> list[str]:
    """ACT.csvValidate's checks on a row the page already normalised (grade A-D, date YYYY-MM-DD). A row that opens a
    tool-fleet or device case (plan 8 MVP-8.4) may carry any asset id; its template facts are the intake's to check."""
    e = []
    if template != "industrial":
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", str(r.get("asset_id", ""))):
            e.append("asset_id is required (letters, digits, '.', '_' or '-')")
    elif not re.fullmatch(r"(MTR|PMP|CTL|DRL|BAT|ITE)-\d{4}", str(r.get("asset_id", ""))):
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
def import_guard(i: dict[str, Any], ctx: CallContext):
    if i["ok"] < 1:
        return "conflict", "No valid rows to load."
    acct = ctx.actor.account  # opening cases from the rows (plan 8 MVP-8.4) also needs openCases
    if i.get("open_cases") is not None and acct is not None and not policy.can(acct, "openCases", ctx.actor.ctx):
        return "out_of_scope", f"The {ctx.actor.role} view cannot open cases."
    return None


KEEP = ("asset_id", "qty", "grade", "location", "owner", "received")
MAX_REJECTED = 5000  # rejected rows held per import (the page caps a file at 200 KB)
ACTIONS["import.commit"].input |= {
    "rejected": {"req": False, "t": "array"},  # the rows the page rejected, held as failed records (plan 6 B3)
    # plan 8 MVP-8.4: {template, reason, org_unit_id, asset_field}: a case for each loaded row (needs openCases)
    "open_cases": {"req": False, "t": "object"},
}


@implement("import.commit", idem=lambda i, ctx: f"imp:{i['hash']}")  # noqa: ARG005 - idem keys take (input, ctx)
def import_commit(i: dict[str, Any], ctx: CallContext):
    """Loads the valid rows as manual evaluation data. The page sends the rows it validated (beyond the demo's counts);
    the server checks them again, and refuses the whole import if any fails: rejected rows are never partially loaded.
    The rows land through the pipeline like a sync (di/connectors/manual.py, plan 6 B3): raw records from source
    `manual`, then canonical facts with no confidence and no freshness, never an instruction. The rejected rows the
    page sends are held in failed_record (run_kind 'import') with their reasons."""
    rows = i.get("rows")
    oc = i.get("open_cases")  # plan 8 MVP-8.4: a tool-fleet or device case per row keeps the template's columns
    template = str(oc.get("template") or "industrial") if isinstance(oc, dict) else "industrial"
    cols = tuple(dict.fromkeys(KEEP + manual.TEMPLATE_COLUMNS.get(template, ())))
    kept: list[dict] | None = None
    if rows is not None:
        if not isinstance(rows, list) or len(rows) != int(i["ok"]) or not all(isinstance(r, dict) for r in rows):
            raise ActionError("validation_error", f"Expected the {int(i['ok'])} valid rows.")
        for r in rows:
            if bad := row_errors(r, template):
                raise ActionError(
                    "validation_error", f"{r.get('asset_id') or 'A row'}: {bad[0]}. Rejected rows are never partially loaded."
                )
        kept = [{k: r.get(k) for k in cols} for r in rows]
    rejected = [r for r in (i.get("rejected") or []) if isinstance(r, dict)]
    s = ctx.session
    n = state.next_number(s, "imports", "IMP-", 0)
    landed = manual.load(
        s, f"IMP-{n}", kept or [], [({k: r.get(k) for k in cols}, row_errors(r, template)) for r in rejected[:MAX_REJECTED]]
    )
    item = {
        "id": f"IMP-{n}",
        "at": NOW,
        "ok": int(i["ok"]),
        "err": int(i["err"]),
        "by": _by(ctx),
        "hash": i["hash"],
        "tag": "manual",
        "rows": kept,
        "facts": landed["facts"],
        "held": landed["held"],
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
    out = {"id": item["id"], "ref": item["id"], "ok": int(i["ok"]), "facts": landed["facts"], "held": landed["held"]}
    if isinstance(i.get("open_cases"), dict):
        out |= manual.open_cases(s, kept or [], i["open_cases"], _by(ctx))
    return out


def _by(ctx: CallContext) -> str:
    return ctx.actor.account.label if ctx.actor.account else "Enterprise system adapter"


# ---------------------------------------------------------------- conflicts
def _name(ctx: CallContext, sid: str) -> str:
    """The source's name as the Connection Fabric shows it (Fabric._source: the demo's name, else its type's label)."""
    if sid == store.MANUAL:  # Manual Import rows and choices made in the Conflict Queue (plan 6 B2, B3)
        return "Manual import"
    if sid in _SOURCES:
        return str(_SOURCES[sid]["name"])
    from di.repositories.fabric import type_of

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


# conflict.resolve beyond the demo (plan 6 B2): keep another source's value or enter one, with a reason
ACTIONS["conflict.resolve"].input |= {
    "choose": {"req": False, "t": "string"},  # authority (default, the demo's), other, value
    "source": {"req": False, "t": "string"},  # with other: which source's value (default: the first other source)
    "value": {"req": False, "t": "string"},  # with value: the value a person enters
    "reason": {"req": False, "t": "string"},  # required with other and value
}
CHOICES = ("authority", "other", "value")


def _entered(c: dict, raw: str) -> Any:
    """The value a person typed, as the field's type (a number for a number field, true/false for a flag)."""
    spec = MODEL_FIELDS.get(c["model"], {}).get(top_field(c["field"]))
    v: Any = raw.strip()
    if spec and spec.type == "number":
        try:
            v = float(v.replace(",", ""))
        except ValueError:
            v = raw
    elif spec and spec.type == "bool" and v.lower() in ("true", "false", "yes", "no"):
        v = v.lower() in ("true", "yes")
    if why := check_fact(Fact(c["model"], c["key"], c["field"], v)):
        raise ActionError("validation_error", f"{why}.")
    return v


def resolve(
    ctx: CallContext, cid: Any, choose: str | None = None, value: Any = None, reason: str | None = None, source: str | None = None
) -> dict:
    """Resolve a conflict. `authority` (the demo's action) keeps the value of the system with authority; `other`
    keeps another source's value and `value` a value the person enters, both with a reason. The resolution sticks
    while the sources keep sending the same values (store.values_hash); routes held by the conflict are released."""
    choose = choose or "authority"
    if choose not in CHOICES:
        raise ActionError("validation_error", f'"choose" must be one of {", ".join(CHOICES)}.')
    c = conflict_row(ctx, cid)
    if c["status"] == "resolved":
        raise ActionError("duplicate", f"{c['ref']} is already resolved")
    reason = (reason or "").strip()
    if choose != "authority" and not reason:
        raise ActionError("validation_error", "Give a reason when you do not keep the value of the system with authority.")
    vals: dict = c["values"] or {}
    kept, kept_name, chosen = c["authority"], c["auth_name"], None
    if choose == "other":
        others = sorted(k for k in vals if k != c["authority"])
        kept = source or (others[0] if others else None)
        if kept is None or kept not in others:
            raise ActionError("validation_error", f"{source or 'Another source'} has no value in {c['ref']}.")
        kept_name, chosen = _name(ctx, kept), vals[kept]
    elif choose == "value":
        if value is None or str(value).strip() == "":
            raise ActionError("validation_error", 'Missing "value".')
        kept, kept_name, chosen = store.MANUAL, _by(ctx), _entered(c, str(value))
    note = {
        "authority": f"Resolved in favour of {c['authority']} (the system with authority)",
        "other": f"Resolved in favour of {kept_name}: {reason}",
        "value": f"Set to {json.dumps(chosen, default=str)} by {_by(ctx)}: {reason}",
    }[choose]
    if choose == "authority" and reason:
        note += f": {reason}"
    ctx.session.execute(
        text(
            "UPDATE conflict SET status = 'resolved', closed_at = now(), closed_by = :by, note = :n, values_hash = :h "
            "WHERE id = :i"
        ),
        {"by": ctx.actor.id, "n": note, "h": store.values_hash(vals), "i": c["id"]},
    )
    if choose == "authority":
        store.drop_override(ctx.session, c["model"], c["key"], c["field"])
        store.settle(ctx.session, c["model"], c["key"], c["field"])
    else:
        store.override(ctx.session, c["model"], c["key"], c["field"], chosen, ctx.actor.id, f"{note} ({c['ref']})")
    text_ = {
        "authority": f"resolved by source authority {c['auth_name']}",
        "other": f"resolved with the value of {kept_name}",
        "value": f"resolved with a value entered by {kept_name}",
    }[choose]
    push_event(
        ctx,
        {
            "dir": "in", "type": "conflict.resolved", "caseId": None, "decisionId": None, "approval": None, "ver": None,
            "dest": f"{c['auth_name']} vs {c['other_name']}", "ack": "acknowledged", "key": "conf-" + c["ref"].lower(),
            "note": f"{c['kind']} conflict on {c['key']} {text_}",
        },
        "conflict.resolve",
    )  # fmt: skip
    out = {
        "id": c["ref"], "ref": c["ref"], "kept": kept, "field": f"{c['model']}.{c['field']}",
        "authority": c["auth_name"], "kind": c["kind"],
    }  # fmt: skip
    if choose != "authority":
        out |= {"choose": choose, "value": chosen, "keptName": kept_name}
    return out


def escalate(ctx: CallContext, cid: Any) -> dict:
    """Escalate to the authority's data owner: status 'escalated' (still active: a sync updates it, it is closed when
    the sources agree, and a person can still resolve it); dependent routes stay held."""
    c = conflict_row(ctx, cid)
    if c["status"] == "resolved":
        raise ActionError("conflict", f"Conflict {c['ref']} is already resolved.")
    if c["status"] == "escalated" or state.get(ctx.session, "conflict_escalations", c["ref"]):
        raise ActionError("duplicate", f"{c['ref']} is already escalated to the data owner")
    state.add(ctx.session, "conflict_escalations", c["ref"], {"id": c["ref"], "by": _by(ctx), "byId": ctx.actor.id, "at": NOW})
    ctx.session.execute(
        text("UPDATE conflict SET status = 'escalated', note = :n WHERE id = :i"),
        {"n": f"Escalated to the {c['auth_name']} data owner by {_by(ctx)}", "i": c["id"]},
    )
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
