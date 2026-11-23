"""An org's configuration pack (plan 8, MVP-10.2): export what an org unit runs on, and set it up for another one.

    org.exportPack  read    {org_unit_id}               perm manageOrgs
        {version: 1, org: {id, parent_id, kind, name},
         sources:   the sources bound to the unit's subtree: {id, name, vendor, type, interval_min, owner, authority,
                    connection: {base_url, protocol, auth_kind, auth_params, resources, paging}, config: {...}},
         mappings:  {source id: the Data Mapping tab's rows},
         workflows: the published workflows that read or write those sources, each its published version in the
                    workflow export's JSON (frontend/src/api/workflows.ts exportJson; workflow.import reads it),
         flows:     {template key: the published graph of the flow the unit uses}}
    org.importPack  commit  {pack, target_org_unit_id}  perm manageOrgs
        {created: {org_unit_id, sources, mappings, workflows, flows}, needs: ["credentials for <source>", ...]}

**Secrets never travel.** A source's secret is in source_secret (di.connectors.secrets), never in its connection or
settings; the export reads neither the secret nor its last four characters, and drops any setting whose name says it is
a secret, password or token. An imported source is created `disconnected`, bound to the target unit, with no secret
and no sync queued: a person enters its credentials and reconnects it (edge case: credentials are re-entered).

**Drafts only.** Each source gets a new id (the pack's id, then `_2`, `_3` ...), and the workflows' steps are pointed at
the new ids. Workflows are imported as drafts (workflow.import); the flows become the target's own (flow.fork when it
has none yet) with the pack's graph as a draft (flow.saveDraft), so nothing imported is published or decides a case
until people take it through the usual review. Agents never import (di.mcp.policy.FORBIDDEN_ACTIONS).
"""

import copy
from typing import Any

from sqlalchemy import text

from di.connectors import connection, lifecycle, mapping
from di.core import orgs, policy
from di.repositories import flows as flow_repo
from di.repositories.common import ms
from di.repositories.constants import MAPPINGS
from di.repositories.orgs import units
from di.repositories.workflows import all_workflows
from di.services.actions import modeler, workflows
from di.services.actions.pipeline import CallContext
from di.services.actions.registry import ACTIONS, ActionDef, ActionError, guard, implement
from di.services.modeler.templates import TEMPLATE_KEYS

VERSION = 1
SECRET_WORDS = ("secret", "password", "token", "credential")
CONFIG_KEYS = (
    "name", "short", "cat", "vendor", "ver", "env", "url", "mode", "auth", "rw", "inputs", "read", "write", "step",
    "authority", "method", "cfg", "interval", "owner", "scopes", "created",
)  # fmt: skip
SOURCE_REFS = ("conn", "wconn", "map")  # workflow steps that name a source
FLOW_BUSY = ("review", "shadow")
_STR = {"req": True, "t": "string"}

ACTIONS.setdefault(
    "org.exportPack",
    ActionDef(
        id="org.exportPack", title="Export an org's configuration", verb="export org configurations", risk="read",
        perm="manageOrgs", scope="none",
        desc="What an org unit runs on, as a pack another org can import: its sources' connection settings (never "
        "their secrets), their mappings, the published workflows that use them and its published decision flows. "
        "Changes nothing.",
        input={"org_unit_id": _STR},
    ),
)  # fmt: skip
ACTIONS.setdefault(
    "org.importPack",
    ActionDef(
        id="org.importPack", title="Import an org's configuration", verb="import org configurations", risk="commit",
        perm="manageOrgs", scope="none",
        desc="Set up an org unit from another org's pack: its sources (disconnected, credentials to be entered), "
        "mappings, workflows as drafts and decision flows as drafts. Nothing is published.",
        input={"pack": {"req": True, "t": "object"}, "target_org_unit_id": _STR},
    ),
)  # fmt: skip


def _no_secrets(d: Any) -> Any:
    """A copy without the keys that name a secret (at any depth)."""
    if isinstance(d, dict):
        return {k: _no_secrets(v) for k, v in d.items() if not any(w in str(k).lower() for w in SECRET_WORDS)}
    if isinstance(d, list):
        return [_no_secrets(v) for v in d]
    return copy.deepcopy(d)


def _by(ctx: CallContext) -> str:
    return ctx.actor.account.label if ctx.actor.account else "Enterprise system adapter"


def _unit_problem(ctx: CallContext, uid: str) -> tuple[str, str] | None:
    if uid not in units(ctx.session):
        return "not_found", f"No org unit {uid}."
    a = ctx.actor.person
    if policy.policy(a).get("tenantScoped") and not policy.tenant_ok(a, uid, ctx.actor.ctx):
        return "tenant_boundary", f"{uid} is an org unit you cannot see. Request tenant access first."
    return None


# ---------------------------------------------------------------- export
def _sources(ctx: CallContext, within: set[str]) -> list[dict[str, Any]]:
    s = ctx.session
    rows = s.execute(
        text(
            "SELECT id, vendor, type, interval_min, owner, authority FROM source_system "
            "WHERE org_unit_id = ANY(:o) ORDER BY id"
        ),
        {"o": sorted(within)},
    ).mappings()
    gone = lifecycle.deleted(s)
    out = []
    for r in rows:
        if r["id"] in gone:
            continue
        cfg = lifecycle.config(s, r["id"])
        conn = connection.connection_for(s, r["id"])
        out.append(
            {
                "id": r["id"], "name": cfg.get("name") or r["id"], "vendor": r["vendor"], "type": r["type"],
                "interval_min": r["interval_min"], "owner": r["owner"], "authority": list(r["authority"] or []),
                "connection": _no_secrets(conn.public()) if conn else None,
                "config": _no_secrets({k: cfg[k] for k in CONFIG_KEYS if k in cfg}),
            }
        )  # fmt: skip
    return out


def _maps(ctx: CallContext, sid: str) -> list[list[str]]:
    """The Data Mapping tab's rows (as fabric_sources._current reads them)."""
    cfg = lifecycle.config(ctx.session, sid)
    return copy.deepcopy(cfg["maps"]) if "maps" in cfg else copy.deepcopy(MAPPINGS.get(sid, []))


def _workflow_export(w: dict[str, Any]) -> dict[str, Any]:
    """The published version of a workflow in the workflow export's JSON."""
    g = workflows.graph_for_run(w)
    return {
        "name": w["name"], "version": w.get("ver"), "type": w.get("cat"), "owner": w.get("owner"), "trigger": w.get("trig"),
        "source_id": w.get("src"), "description": w.get("desc"),
        "steps": [{"id": n["id"], "kind": n["k"], "ref": n["ref"], "x": n["x"], "y": n["y"]}
                  | ({"cfg": _no_secrets(n["cfg"])} if n.get("cfg") else {}) for n in g["nodes"]],
        "links": [{"from": e["a"], "to": e["b"], "fixed": bool(e.get("locked"))} for e in g["edges"]],
    }  # fmt: skip


def _uses(w: dict[str, Any], ids: set[str]) -> bool:
    g = workflows.graph_for_run(w)
    return w.get("src") in ids or any(n["k"] in SOURCE_REFS and n["ref"] in ids for n in g["nodes"])


@guard("org.exportPack")
def export_guard(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | None:
    return _unit_problem(ctx, i["org_unit_id"])


@implement("org.exportPack")
def export_pack(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    s, uid = ctx.session, i["org_unit_id"]
    us = units(s)
    sources = _sources(ctx, orgs.subtree(us, uid))
    ids = {x["id"] for x in sources}
    flows: dict[str, Any] = {}
    for key in TEMPLATE_KEYS:
        f = flow_repo.flow_for(s, key, uid)
        if f is not None:
            flows[key] = copy.deepcopy(f.published)
    return {
        "version": VERSION,
        "org": dict(us[uid].__dict__),
        "sources": sources,
        "mappings": {sid: _maps(ctx, sid) for sid in sorted(ids)},
        "workflows": [_workflow_export(w) for w in all_workflows(s) if w.get("status") == "published" and _uses(w, ids)],
        "flows": flows,
    }


# ---------------------------------------------------------------- import
def _pack_problem(p: dict[str, Any]) -> str | None:
    if p.get("version") != VERSION:
        return f"This is not an org configuration pack (version {VERSION})."
    if not all(isinstance(p.get(k), t) for k, t in (("sources", list), ("mappings", dict), ("workflows", list),
                                                     ("flows", dict))):  # fmt: skip
        return "The pack needs its sources, mappings, workflows and flows."
    for x in p["sources"]:
        if not isinstance(x, dict) or not all(isinstance(x.get(k), str) and x[k] for k in ("id", "type", "vendor")):
            return "Every source in the pack needs its id, type and vendor."
        conn = x.get("connection")
        if conn is not None and not (isinstance(conn, dict) and conn.get("base_url")):
            return f"The connection of source {x['id']} needs a base URL."
    bad = [k for k in p["flows"] if k not in TEMPLATE_KEYS]
    if bad:
        return f"Unknown template {bad[0]} in the pack's flows."
    return None


@guard("org.importPack")
def import_guard(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | None:
    target = i["target_org_unit_id"]
    if bad := _unit_problem(ctx, target):
        return bad
    if msg := _pack_problem(i["pack"]):
        return "validation_error", msg
    for key in i["pack"]["flows"]:
        f = flow_repo.flow_for(ctx.session, key, target)
        if f is not None and f.org_unit_id == target and f.status in FLOW_BUSY:
            return "conflict", f"{target}'s {f.name} flow is in {f.status}; finish that review first."
    return None


def _free_id(ctx: CallContext, base: str) -> str:
    taken = set(ctx.session.execute(text("SELECT id FROM source_system")).scalars())
    sid, n = base, 2
    while sid in taken:
        sid, n = f"{base}_{n}", n + 1
    return sid


def _import_source(ctx: CallContext, x: dict[str, Any], maps: list[list[str]], target: str, note: str) -> str:
    """The source, disconnected and bound to `target`, with its connection settings and mapping but no secret."""
    s, by = ctx.session, _by(ctx)
    sid = _free_id(ctx, x["id"])
    s.execute(
        text(
            "INSERT INTO source_system (id, vendor, type, status, interval_min, authority, owner, completeness, confidence, "
            "org_unit_id) VALUES (:id, :v, :t, 'disconnected', :iv, :a, :o, 0, 0, :org)"
        ),
        {"id": sid, "v": x["vendor"], "t": x["type"], "iv": int(x.get("interval_min") or 0),
         "a": [str(a) for a in x.get("authority") or []], "o": x.get("owner"), "org": target},
    )  # fmt: skip
    conn = x.get("connection")
    if conn:
        fields = _no_secrets({k: conn[k] for k in ("base_url", "protocol", "auth_kind", "auth_params", "resources", "paging")
                              if k in conn})  # fmt: skip
        try:
            connection.save_connection(s, sid, by, **fields)
        except ValueError as e:
            raise ActionError("validation_error", f"Source {x['id']}: {e}") from e
    now = ms(ctx.now.isoformat())
    cfg = _no_secrets(x.get("config") or {})
    item = cfg | {
        "id": sid, "name": x.get("name") or cfg.get("name") or sid, "cfgVer": "1.0", "updatedBy": by, "prev": "live",
        "discBy": by, "maps": maps, "audit": [{"ver": "1.0", "who": by, "ts": now, "change": note, "prep": ctx.preparer}],
    }  # fmt: skip
    lifecycle.save(s, item)
    if maps:
        mapping.save_version(s, sid, maps, by, note, ctx.now, strict=False)
    return sid


def _rows(raw: Any) -> list[list[str]]:
    return [[str(c) for c in m] for m in raw or [] if isinstance(m, list)]


def _workflow_data(w: dict[str, Any], new_ids: dict[str, str]) -> dict[str, Any]:
    """The exported workflow with its sources renamed to the imported ones."""
    d = copy.deepcopy(w)
    for st in d.get("steps") or []:
        if isinstance(st, dict) and st.get("kind") in SOURCE_REFS and st.get("ref") in new_ids:
            st["ref"] = new_ids[st["ref"]]
    if d.get("source_id") in new_ids:
        d["source_id"] = new_ids[d["source_id"]]
    d.pop("source", None)  # the vendor name would match the exporting org's source
    return d


def _import_flow(ctx: CallContext, key: str, graph: Any, target: str) -> int:
    """The target's own flow of the template (forked when it has none) with `graph` as its draft."""
    base = flow_repo.flow_for(ctx.session, key, target)
    if base is not None and base.org_unit_id == target:
        fid = base.id
    else:
        fork = {"template_key": key, "org_unit_id": target}
        if bad := modeler.fork_guard(fork, ctx):
            raise ActionError(*bad)
        fid = int(modeler.fork(fork, ctx)["flow_id"])
    draft = {"flow_id": fid, "graph": graph if isinstance(graph, dict) else {}}
    if bad := modeler.save_guard(draft, ctx):
        raise ActionError(bad[0], f"The {key} flow: {bad[1]}")
    modeler.save_draft(draft, ctx)
    return fid


@implement("org.importPack")
def import_pack(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    p, target = i["pack"], i["target_org_unit_id"]
    origin = (p.get("org") or {}).get("name") or (p.get("org") or {}).get("id") or "another org"
    note = f"Imported from {origin}'s configuration pack"
    new_ids: dict[str, str] = {}
    needs: list[str] = []
    for x in p["sources"]:
        new_ids[x["id"]] = _import_source(ctx, x, _rows(p["mappings"].get(x["id"])), target, note)
        needs.append(f"credentials for {x.get('name') or x['id']}")
    wf_ids = []
    for w in p["workflows"]:
        data = _workflow_data(w, new_ids) if isinstance(w, dict) else {}
        if bad := workflows.import_guard({"data": data}, ctx):
            raise ActionError(*bad)
        wf_ids.append(workflows.import_workflow({"data": data}, ctx)["id"])
    flow_ids = [_import_flow(ctx, key, g, target) for key, g in p["flows"].items()]
    created = {
        "org_unit_id": target,
        "sources": list(new_ids.values()),
        "mappings": [new_ids[k] for k in new_ids if _rows(p["mappings"].get(k))],
        "workflows": wf_ids,
        "flows": flow_ids,
    }
    return {"created": created, "needs": needs}
