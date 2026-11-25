"""The adapter registry and connections made from it (plan 9, P9-8.1; registry entry I-18; story X-10 enabler).

    registry.list           read    {kind?, system_type?, org_unit_id?}   the entries a person can start a connection from
    registry.saveEntry      act     {entry}                               a generic_rest or from_spec entry, saved as a draft
    registry.release        commit  {id, version}                         tested -> released, by someone who did not draft it
    connection.create       act     {registry_id, version, name, org_unit_id, system_owner, test_base_url?, auth?, secret?}
                                                                          a source in the test environment, read only
    connection.requestOwner act     {source_id, environment, access, note?}   ask the system owner (a My work item)
    connection.ownerApprove commit  {id}                                  the owner (or an Admin) approves a request
    connection.ownerDecline commit  {id, reason}                          ... or declines it, with a reason
    connection.promote      commit  {source_id, secret}                   test -> production, once the owner approved it
    connection.approvals    read    {source_id}                           where a connection stands and its requests
    connection.discover     act     {source_id}                           read up to 500 records per resource from a TEST connection into the dry raw store (P9-8.3)

A connection starts in the test environment with read access: no scheduled sync, no instruction (di.connectors.sync,
di.services.instructions.send). Production access and write-back (`rw` "Read / write") are each a request the named
system owner approves. The requester never approves their own request (maker-checker). The owner actions carry
`perm=None` because `ownSystem` alone cannot say "the named owner": their guards check that the actor is the owner or
holds `ownSystem` (Admin), and is not the requester.

`connection.` and `registry.release` are in FORBIDDEN_ACTIONS (di.services.agents.forbidden): no agent creates a
connection, asks for, grants or declines access, or releases a connector; an agent may read the registry and draft an
entry (a draft is configuration, never code). `connection.create` reuses `source.update` (di.services.actions.
fabric_sources) so a connection is a source like any other; the credential goes to the encrypted store only
(di.connectors.secrets) and is never returned, journaled or logged.

Owns: the registry and connection actions and their guards. Never does: store or return a secret outside
`secrets.put_secret`, approve for a person, or send anything to a system.
"""
# ruff: noqa: E501 - long lines in the action texts and the registry's field lists

import re
from typing import Any

from sqlalchemy import text

from di.connectors import catalog, connection, discover, lifecycle, secrets, sync
from di.connectors.http import SourceError
from di.connectors.registry import GENERIC_AUTH_METHODS, RegistryEntry, catalogue_entries
from di.core import policy
from di.repositories import adapter_registry as repo
from di.services.actions.fabric_sources import CATALOG, FR_AUTH, SRC_TYPES, source_update
from di.services.actions.pipeline import CallContext
from di.services.actions.registry import ACTIONS, ActionDef, ActionError, Risk, guard, implement
from di.services.cases import process

_MGR = "manageIntegrations"
_STR = {"req": True, "t": "string"}
_ENVIRONMENTS, _ACCESSES = ("test", "production"), ("read", "read_write")
MAKER_CHECKER = "Maker-checker: you asked for this connection, so the system owner must approve it."
NO_OWNER = "Name the system owner: a person from the directory."
_WORK_TYPE = "connection_approval"
_AUTH_LABEL = {
    "none": "None", "api_key": "API key", "bearer": "Bearer token", "basic": "Basic (password)",
    "oauth_cc": "OAuth client credentials",
}  # fmt: skip
_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{1,62}$")
_REASON = {"req": True, "t": "string", "min": 15, "minText": "Add a reason of at least 15 characters."}


def _declare(
    action_id: str, title: str, verb: str, desc: str, risk: Risk, inp: dict[str, dict[str, Any]], perm: str | None
) -> None:
    ACTIONS.setdefault(
        action_id,
        ActionDef(id=action_id, title=title, desc=desc, risk=risk, perm=perm, scope="none", input=inp, verb=verb),
    )


_declare("registry.list", "List the adapter registry", "see the adapter registry",
         "The connectors a connection can be made from: the catalogue, generic REST and saved API specs.", "read",
         {"kind": {"t": "string"}, "system_type": {"t": "string"}, "org_unit_id": {"t": "string"}}, _MGR)  # fmt: skip
_declare("registry.saveEntry", "Save a connector entry", "save connector entries",
         "Save a generic REST or API-spec connector as a draft (a new version when the id exists).", "act",
         {"entry": {"req": True, "t": "object"}}, _MGR)  # fmt: skip
_declare("registry.release", "Release a connector", "release connectors",
         "Release a tested connector so every org can connect from it. Not by the person who drafted it.", "commit",
         {"id": _STR, "version": {"req": True, "t": "number"}}, _MGR)  # fmt: skip
_declare("connection.create", "Create a test connection", "create connections",
         "Create a connection from a registry entry in the test environment, read only, with a named system owner.", "act",
         {"registry_id": _STR, "version": {"t": "number"}, "name": _STR, "org_unit_id": _STR, "system_owner": {"t": "string"},
          "test_base_url": {"t": "string"}, "auth": {"t": "string"}, "secret": {"t": "string"}}, _MGR)  # fmt: skip
_declare("connection.requestOwner", "Ask the system owner to approve", "ask system owners to approve",
         "Ask the named system owner to approve production access or write-back for a connection.", "act",
         {"source_id": _STR, "environment": _STR, "access": _STR, "note": {"t": "string"}}, _MGR)  # fmt: skip
_declare("connection.ownerApprove", "Approve a connection request", "approve connection requests",
         "The system owner approves a request for production access or write-back.", "commit",
         {"id": {"req": True, "t": "number"}}, None)  # fmt: skip
_declare("connection.ownerDecline", "Decline a connection request", "decline connection requests",
         "The system owner declines a request, with a reason.", "commit", {"id": {"req": True, "t": "number"}, "reason": _REASON},
         None)  # fmt: skip
_declare("connection.promote", "Promote a connection to production", "promote connections",
         "Move an approved connection from test to production with its production credential; its first sync is queued.",
         "commit", {"source_id": _STR, "secret": _STR}, _MGR)  # fmt: skip
_declare("connection.approvals", "Where a connection stands", "see a connection's approvals",
         "The connection's environment, access, system owner and the owner's approvals.", "read", {"source_id": _STR}, None)  # fmt: skip
_declare("connection.discover", "Read a sample from the test connection", "read samples from test connections",
         "Read up to 500 records per resource from the test connection into the quarantined sample store; writes no canonical fact.",
         "act", {"source_id": _STR}, _MGR)  # fmt: skip


# ---------------------------------------------------------------- helpers
def _by(ctx: CallContext) -> str:
    return ctx.actor.account.label if ctx.actor.account else "system"


def _tenant_refusal(ctx: CallContext, org: str | None) -> tuple[str, str] | None:
    """A tenant-scoped actor reaches only the org units of their tenant."""
    a = ctx.actor.account
    if org is None or a is None or not policy.policy(a).get("tenantScoped") or policy.tenant_ok(a, org, ctx.actor.ctx):
        return None
    return "tenant_boundary", f"{org} is a tenant you cannot see. Request tenant access first."


def _is_http(url: Any) -> bool:
    return isinstance(url, str) and bool(re.match(r"^https?://[^/\s]+", url))


def _source(ctx: CallContext, source_id: str) -> dict[str, Any] | None:
    """The source's row with its connection and saved name, or None when there is none (or it was deleted)."""
    s = ctx.session
    r = s.execute(
        text("SELECT id, vendor, org_unit_id FROM source_system WHERE id = :i"), {"i": source_id}
    ).mappings().first()  # fmt: skip
    conn = connection.connection_for(s, source_id)
    if r is None or conn is None or lifecycle.is_deleted(s, source_id):
        return None
    return {
        "id": r["id"],
        "org": r["org_unit_id"],
        "conn": conn,
        "name": lifecycle.config(s, source_id).get("name") or r["vendor"],
    }


def _view(src: dict[str, Any]) -> dict[str, Any]:
    conn: connection.Connection = src["conn"]
    return {"source_id": src["id"], "name": src["name"], "environment": conn.environment, "system_owner": conn.system_owner}


# ---------------------------------------------------------------- registry.list, saveEntry, release
@guard("registry.list")
def list_guard(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | None:
    return _tenant_refusal(ctx, i.get("org_unit_id"))


@implement("registry.list")
def list_entries(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    found = [
        e for e in repo.entries(ctx.session, i.get("org_unit_id"))
        if (not i.get("kind") or e.kind == i["kind"]) and (not i.get("system_type") or e.system_type == i["system_type"])
    ]  # fmt: skip
    return {"entries": [e.public() for e in found]}


def _entry_problem(e: dict[str, Any]) -> tuple[str, str] | None:
    if e.get("kind") == "catalogue":
        return "validation_error", "Catalogue connectors are maintained by Circularity."
    if e.get("kind") not in ("generic_rest", "from_spec"):
        return "validation_error", 'An entry\'s "kind" is generic_rest or from_spec.'
    if not _ID.match(str(e.get("id") or "")):
        return "validation_error", "Give the entry an id of lower-case letters, digits, - and _."
    if not str(e.get("system_type") or "").strip() or not str(e.get("vendor_family") or "").strip():
        return "validation_error", "Name the entry's system type and vendor family."
    auth = e.get("auth_methods") or []
    if not isinstance(auth, list) or any(a not in GENERIC_AUTH_METHODS for a in auth):
        return "validation_error", f"Authentication methods are among {', '.join(GENERIC_AUTH_METHODS)}."
    if not isinstance(e.get("resources") or [], list) or not isinstance(e.get("spec") or {}, dict):
        return "validation_error", '"resources" is a list and "spec" an object.'
    return None


@guard("registry.saveEntry")
def save_guard(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | None:
    e = i["entry"]
    if bad := _entry_problem(e):
        return bad
    if e["id"] in {c.id for c in catalogue_entries()}:
        return "conflict", f"{e['id']} is a Circularity connector: choose another id."
    if (org := e.get("org_unit_id")) is not None:
        if ctx.session.execute(text("SELECT 1 FROM org_unit WHERE id = :i"), {"i": org}).first() is None:
            return "validation_error", f"No org unit {org}."
        if bad := _tenant_refusal(ctx, org):
            return bad
    known = ctx.session.execute(text("SELECT kind FROM adapter_registry WHERE id = :i LIMIT 1"), {"i": e["id"]}).scalar()
    return ("conflict", f"{e['id']} is a {known} entry: keep its kind.") if known not in (None, e["kind"]) else None


@implement("registry.saveEntry")
def save_entry(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    import json

    e = i["entry"]
    ver = repo.next_version(ctx.session, e["id"])
    ctx.session.execute(
        text(
            "INSERT INTO adapter_registry (id, version, kind, system_type, vendor_family, auth_methods, resources, "
            "canonical_entities, write_actions, mapping_templates, status, maintainer, source_licence, spec, org_unit_id, "
            "created_by) VALUES (:i, :v, :k, :t, :f, :am, CAST(:rs AS jsonb), :ce, :wa, CAST(:mt AS jsonb), 'draft', :m, :sl, "
            "CAST(:sp AS jsonb), :o, :by)"
        ),
        {"i": e["id"], "v": ver, "k": e["kind"], "t": str(e["system_type"]).strip(), "f": str(e["vendor_family"]).strip(),
         "am": [str(a) for a in e.get("auth_methods") or []], "rs": json.dumps(e.get("resources") or []),
         "ce": [str(a) for a in e.get("canonical_entities") or []], "wa": [str(a) for a in e.get("write_actions") or []],
         "mt": json.dumps(e.get("mapping_templates") or {}), "m": e.get("maintainer") or ctx.actor.id,
         "sl": e.get("source_licence"), "sp": json.dumps(e.get("spec") or {}), "o": e.get("org_unit_id"), "by": ctx.actor.id},
    )  # fmt: skip
    return {"id": e["id"], "version": ver, "status": "draft", "log": f"Saved the draft of connector {e['id']} v{ver}"}


@guard("registry.release")
def release_guard(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | None:
    row = repo.row(ctx.session, i["id"], int(i["version"]))
    if row is None:
        return "not_found", f"No saved connector {i['id']} v{int(i['version'])}."
    if row.created_by == ctx.actor.id:
        return "conflict", "Maker-checker: you drafted this connector, so another person must release it."
    return (
        None
        if row.status == "tested"
        else ("conflict", f"{i['id']} v{int(i['version'])} is {row.status}: only a tested connector is released.")
    )


@implement("registry.release")
def release(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    row = repo.row(ctx.session, i["id"], int(i["version"]), for_update=True)
    if row is None or row.status != "tested":  # changed between the guard and this lock
        raise ActionError("conflict", f"{i['id']} can no longer be released.")
    ctx.session.execute(
        text("UPDATE adapter_registry SET status = 'released', released_by = :by WHERE id = :i AND version = :v"),
        {"by": ctx.actor.id, "i": row.id, "v": row.version},
    )
    return {"id": row.id, "version": row.version, "status": "released", "log": f"Released connector {row.id} v{row.version}"}


# ---------------------------------------------------------------- connection.create
def _entry_of(i: dict[str, Any], ctx: CallContext) -> RegistryEntry | None:
    return repo.entry(ctx.session, i["org_unit_id"], i["registry_id"], int(i.get("version") or 1))


@guard("connection.create")
def create_guard(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | None:
    s, org = ctx.session, i["org_unit_id"]
    if s.execute(text("SELECT 1 FROM org_unit WHERE id = :i"), {"i": org}).first() is None:
        return "validation_error", f"No org unit {org}."
    if bad := _tenant_refusal(ctx, org):
        return bad
    entry = _entry_of(i, ctx)
    if entry is None:
        return "not_found", f"No connector {i['registry_id']} v{int(i.get('version') or 1)} in the registry."
    if entry.status == "deprecated":
        return "conflict", f"{entry.id} is deprecated: connect from a newer version."
    owner = policy.account(str(i.get("system_owner") or ""), ctx.actor.ctx)
    if owner is None:
        return "validation_error", NO_OWNER
    if policy.policy(owner).get("tenantScoped") and not policy.tenant_ok(owner, org, ctx.actor.ctx):
        return "tenant_boundary", f"{org} is a tenant {owner.id} cannot see: name a system owner who can."
    if i.get("secret") and len(str(i["secret"])) < 8:
        return "validation_error", "Enter at least 8 characters."
    url = i.get("test_base_url")
    if entry.kind != "catalogue" and not _is_http(url):
        return "validation_error", "Enter the base URL of the test system (http or https)."
    if url and not _is_http(url):
        return "validation_error", "The test base URL starts with http:// or https://."
    if entry.kind != "catalogue" and (a := i.get("auth")) and a not in entry.auth_methods:
        return "validation_error", f"{entry.id} signs in with: {', '.join(entry.auth_methods) or 'nothing'}."
    return None


def _catalogue_call(entry: RegistryEntry, i: dict[str, Any]) -> dict[str, Any]:
    labels = CATALOG[entry.id]["auth"]
    auth = next((a[0] for a in FR_AUTH if a[1] in labels), "key")  # the id of the first sign-in the system offers
    rows = [[r["src"], "", f"{r['model']}.{r['field']}", "", "", r["resource"]] for r in catalog.maps(entry.id)]
    return {"mode": "catalog", "id": None, "d": {"catalog": entry.id, "auth": auth, "scopes": []},
            "maps": rows, "ops": {"read": [], "write": []}, "note": "", "org_unit_id": i["org_unit_id"], "secret": i.get("secret")}  # fmt: skip


def _new_call(entry: RegistryEntry, i: dict[str, Any], owner_label: str) -> dict[str, Any]:
    kind = str(i.get("auth") or (entry.auth_methods[0] if entry.auth_methods else "none"))
    d = {
        "method": "api", "name": str(i["name"]).strip(), "vendor": entry.vendor_family, "ver": "", "env": "Test",
        "type": entry.system_type if entry.system_type in SRC_TYPES else "erp", "url": i["test_base_url"],
        "auth": _AUTH_LABEL.get(kind, "None"), "interval": 30, "owner": owner_label, "cfg": {},
    }  # fmt: skip
    return {"mode": "new", "id": None, "d": d, "maps": [], "ops": {"read": [], "write": []}, "note": "",
            "org_unit_id": i["org_unit_id"], "secret": i.get("secret")}  # fmt: skip


def _apply_spec(ctx: CallContext, sid: str, entry: RegistryEntry, url: str | None) -> None:
    """What an entry's spec says about the connection (resources, paging, how it signs in), and the test URL when sent."""
    fields: dict[str, Any] = {}
    if entry.kind != "catalogue":  # a catalogue connection already has its template's
        fields = {k: entry.spec[k] for k in ("resources", "paging", "auth_kind", "auth_params") if entry.spec.get(k)}
        if entry.resources and "resources" not in fields:
            fields["resources"] = list(entry.resources)
    if url:
        fields["base_url"] = url
    if fields:
        try:
            connection.save_connection(ctx.session, sid, _by(ctx), **fields)
        except ValueError as e:
            raise ActionError("validation_error", str(e)) from e


@implement("connection.create")
def create(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    entry = _entry_of(i, ctx)
    owner = policy.account(str(i.get("system_owner") or ""), ctx.actor.ctx)
    if entry is None or owner is None:  # not reached: the guard refused it
        raise ActionError("validation_error", NO_OWNER)
    call = _catalogue_call(entry, i) if entry.kind == "catalogue" else _new_call(entry, i, owner.label)
    sid = str(source_update(call, ctx)["source_id"])
    s = ctx.session
    _apply_spec(ctx, sid, entry, i.get("test_base_url"))
    connection.tag(s, sid, environment="test", system_owner=owner.id, registry_id=entry.id, registry_version=entry.version)
    sync.drop_queued(s, sid)  # source.update queued the first sync before the connection was marked test
    cfg = lifecycle.config(s, sid)
    lifecycle.save(s, cfg | {"name": str(i["name"]).strip(), "env": "Test", "rw": "Read"})
    return {
        "source_id": sid, "environment": "test", "access": "read", "system_owner": owner.id, "registry_id": entry.id,
        "version": entry.version, "name": str(i["name"]).strip(), "log": f"Created the test connection {i['name']} from {entry.id}",
    }  # fmt: skip


# ---------------------------------------------------------------- connection.requestOwner
@guard("connection.requestOwner")
def request_guard(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | None:
    if i["environment"] not in _ENVIRONMENTS or i["access"] not in _ACCESSES:
        return "validation_error", "The environment is test or production; the access is read or read_write."
    src = _source(ctx, i["source_id"])
    if src is None:
        return "not_found", f"No source {i['source_id']}."
    if bad := _tenant_refusal(ctx, src["org"]):
        return bad
    owner = src["conn"].system_owner
    if not owner or policy.account(owner, ctx.actor.ctx) is None:
        return "validation_error", f"{src['name']} has no system owner in the directory: name one first."
    if repo.pending_like(ctx.session, i["source_id"], i["environment"], i["access"]):
        return "conflict", f"The system owner has this request already: {src['name']}, {i['environment']}, {i['access']}."
    return None


@implement("connection.requestOwner")
def request_owner(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    src = _source(ctx, i["source_id"])
    assert src is not None  # noqa: S101 - the guard found it
    owner = policy.account(src["conn"].system_owner or "", ctx.actor.ctx)
    assert owner is not None  # noqa: S101 - the guard found it
    s = ctx.session
    rid = s.execute(
        text(
            "INSERT INTO connection_approval (source_id, environment, access, requested_by, owner, status) "
            "VALUES (:i, :e, :a, :by, :o, 'pending') RETURNING id"
        ),
        {"i": i["source_id"], "e": i["environment"], "a": i["access"], "by": ctx.actor.id, "o": owner.id},
    ).scalar_one()
    what = "write-back (read and write)" if i["access"] == "read_write" else f"{i['environment']} access (read)"
    process.open_item(
        s, kind="step", case_id=None, org_unit_id=src["org"], type=f"{_WORK_TYPE}:{rid}",
        title=f"Approve {what} for {src['name']}", cause=(i.get("note") or f"{_by(ctx)} asks for {what}.").strip(),
        action="Approve or decline", owner_role=owner.role, owner_account=owner.id, due_hours=None, by=ctx.actor.id,
    )  # fmt: skip
    return {
        "id": int(rid),
        "status": "pending",
        "owner": owner.id,
        "log": f"Asked {owner.id} to approve {what} for {src['name']}",
    }


# ---------------------------------------------------------------- connection.ownerApprove, ownerDecline
def _decide_refusal(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | None:
    row = repo.approval(ctx.session, i["id"])
    if row is None:
        return "not_found", f"No request {int(i['id'])}."
    if row["status"] != "pending":
        return "conflict", f"Request {int(i['id'])} was already {row['status']}."
    if ctx.actor.id == row["requested_by"]:
        return "conflict", MAKER_CHECKER
    if ctx.actor.id != row["owner"] and not policy.can(ctx.actor.account, "ownSystem", ctx.actor.ctx):
        return "out_of_scope", "Only the system owner, or an Admin, decides this request."
    src = _source(ctx, row["source_id"])
    return _tenant_refusal(ctx, src["org"] if src else None)


guard("connection.ownerApprove")(_decide_refusal)
guard("connection.ownerDecline")(_decide_refusal)


def _decide(i: dict[str, Any], ctx: CallContext, status: str, reason: str | None) -> dict[str, Any]:
    row = repo.approval(ctx.session, i["id"], for_update=True)
    if row is None or row["status"] != "pending":  # decided between the guard and this lock
        raise ActionError("conflict", f"Request {int(i['id'])} can no longer be decided.")
    ctx.session.execute(
        text("UPDATE connection_approval SET status = :st, reason = :r, decided_by = :by, decided_at = :now WHERE id = :i"),
        {"st": status, "r": reason, "by": ctx.actor.id, "now": ctx.now, "i": row["id"]},
    )
    items = ctx.session.execute(
        text("SELECT id FROM work_item WHERE type = :t AND status = 'open'"), {"t": f"{_WORK_TYPE}:{row['id']}"}
    ).scalars()
    for item in items:
        process.close_item(ctx.session, item, status, ctx.actor.id)
    return row


@implement("connection.ownerApprove")
def owner_approve(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    row = _decide(i, ctx, "approved", None)
    if row["access"] == "read_write":  # write-back: the source's `rw` label is the access (registry.access_of)
        lifecycle.save(ctx.session, lifecycle.config(ctx.session, row["source_id"]) | {"rw": "Read / write"})
    return {"id": row["id"], "source_id": row["source_id"], "status": "approved", "environment": row["environment"],
            "access": row["access"], "log": f"Approved {row['environment']} {row['access']} access for {row['source_id']}"}  # fmt: skip


@implement("connection.ownerDecline")
def owner_decline(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    row = _decide(i, ctx, "declined", str(i["reason"]).strip())
    return {"id": row["id"], "source_id": row["source_id"], "status": "declined", "reason": str(i["reason"]).strip(),
            "log": f"Declined {row['environment']} {row['access']} access for {row['source_id']}"}  # fmt: skip


# ---------------------------------------------------------------- connection.promote
@guard("connection.promote")
def promote_guard(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | None:
    src = _source(ctx, i["source_id"])
    if src is None:
        return "not_found", f"No source {i['source_id']}."
    if bad := _tenant_refusal(ctx, src["org"]):
        return bad
    if src["conn"].environment != "test":
        return "conflict", f"{src['name']} is in production already."
    if not repo.approved(ctx.session, i["source_id"], "production", lifecycle.access_of(ctx.session, i["source_id"])):
        return "conflict", f"The system owner has not approved production access for {src['name']}."
    return None if len(str(i["secret"])) >= 8 else ("validation_error", "Enter at least 8 characters.")


@implement("connection.promote")
def promote(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    s, sid = ctx.session, i["source_id"]
    secrets.put_secret(s, sid, "auth", str(i["secret"]), 180, _by(ctx), ctx.now)
    connection.set_environment(s, sid, "production")
    lifecycle.save(s, lifecycle.config(s, sid) | {"env": "Production"})
    job = sync.enqueue_sync(s, sid, "initial", full=True)  # the first sync of the production connection
    return {"source_id": sid, "environment": "production", "queued": job is not None, "log": f"Promoted {sid} to production"}


# ---------------------------------------------------------------- connection.approvals
@guard("connection.approvals")
def approvals_guard(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | None:
    src = _source(ctx, i["source_id"])
    if src is None:
        return "not_found", f"No source {i['source_id']}."
    if not (policy.can(ctx.actor.account, _MGR, ctx.actor.ctx) or ctx.actor.id == src["conn"].system_owner):
        return "out_of_scope", f"The {ctx.actor.role} view cannot see this connection's approvals."
    return _tenant_refusal(ctx, src["org"])


@implement("connection.approvals")
def approvals(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    src = _source(ctx, i["source_id"])
    assert src is not None  # noqa: S101 - the guard found it
    conn: connection.Connection = src["conn"]
    return _view(src) | {
        "access": lifecycle.access_of(ctx.session, i["source_id"]),
        "registry_id": conn.registry_id,
        "registry_version": conn.registry_version,
        "approvals": repo.approvals_of(ctx.session, i["source_id"]),
    }


# ---------------------------------------------------------------- connection.discover (P9-8.3)
@guard("connection.discover")
def discover_guard(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | None:
    src = _source(ctx, i["source_id"])
    if src is None:
        return "not_found", f"No source {i['source_id']}."
    if bad := _tenant_refusal(ctx, src["org"]):
        return bad
    if src["conn"].environment != "test":
        return "conflict", discover.TEST_ONLY
    return None if src["conn"].resources else ("conflict", f"{src['name']} has no resources to read a sample from.")


@implement("connection.discover")
def discover_sample(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    """Counts per resource and whether the spread over the window was used. The records are stored dry (di.connectors.
    discover.DRY): Suggest mappings and Source Tables read them; no canonical fact exists until a sync."""
    sid = i["source_id"]
    try:
        report = discover.sample_report(ctx.session, sid)
    except SourceError as e:
        raise ActionError("conflict", f"The test system did not give a sample: {e}") from e
    except ValueError as e:
        raise ActionError("conflict", str(e)) from e
    total = sum(v["read"] for v in report.values())
    return {
        "source_id": sid,
        "counts": {r: v["read"] for r, v in report.items()},
        "spread": {r: v["spread"] for r, v in report.items()},
        "log": f"Read a sample of {total} records from the test connection {sid}",
    }
