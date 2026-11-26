"""The workspace state collections as resources (plan 3 task 3): notes, comments, scenarios, requests, mcp-servers.

Each is a collection in `di.core.state`; a person reads it here and changes it only through its actions:
- `notes` (Actions on me): visible to the person a note is addressed to (Admin sees all). create = `notify.send`,
  update = `notify.acknowledge`, no delete.
- `comments`: visible when the record they are on is (`src:` an Integration page, `au:` the Audit log, else a case the
  account may see) or the account wrote them; filter `key`. create = `comment.add`; never edited or deleted.
- `scenarios`: saved what-ifs of the cases the account may see (filter `case_id`). create = `scenario.save`, delete =
  `scenario.delete`; no edit (save a new one).
- `requests`: tenant-access requests and MCP server proposals the account made or may decide (filter `kind`,
  `status`). create = `access.requestTenant` (a proposal is `POST /mcp-servers`), update = `access.decideRequest`.
- `mcp-servers`: the MCP servers Circularity consumes (page mcp/client). create = `mcp.propose`, which holds for a
  person (decide it on `requests`); no edit or delete.
"""

from typing import Any

from sqlalchemy import text

from di.core import policy, state
from di.repositories.access import request_rows
from di.repositories.common import REQ_SCOPE, notes
from di.resources import Resource, register
from di.resources.support import is_admin, principal, read, require_page, visible_case_ids
from di.services.actions.pipeline import CallContext
from di.services.screens import mcp as mcp_screen


# ---------------------------------------------------------------- notes
def _my_notes(ctx: CallContext) -> list[dict[str, Any]]:
    a = ctx.actor.person
    every = is_admin(ctx)
    return [n for n in notes(ctx.session) if every or n.get("to") == a.id]


def list_notes(ctx: CallContext, q: dict[str, Any]) -> list[dict[str, Any]]:
    return [n for n in _my_notes(ctx) if not q.get("status") or n.get("status") == q["status"]]


def get_note(ctx: CallContext, nid: str) -> dict[str, Any] | None:
    return next((n for n in _my_notes(ctx) if n["id"] == nid), None)


register(
    Resource(
        name="notes", list=list_notes, get=get_note, create="notify.send", update="notify.acknowledge", delete=None,
        fields=("ex_id", "to", "title", "msg", "sev", "ids"), filters=("status",),
        why_not={"delete": "A notification is kept as the record that it was sent and who took it in hand."},
    )
)  # fmt: skip


# ---------------------------------------------------------------- comments
def _comment_visible(ctx: CallContext, c: dict[str, Any], cases: set[str]) -> bool:
    key = str(c.get("key", ""))
    a = ctx.actor.account
    if is_admin(ctx) or c.get("by") == (a.id if a else None):
        return True
    if key.startswith("src:"):
        return policy.can_page(a, "integration", "overview") or policy.can_page(a, "integration", "monitor")
    if key.startswith("au:"):
        return policy.can_page(a, "audit", "log")
    return key in cases


def _comments(ctx: CallContext) -> list[dict[str, Any]]:
    state.items(ctx.session, "comments")  # seeds the collection
    rows = ctx.session.execute(text("SELECT id, data FROM state_item WHERE collection = 'comments' ORDER BY seq")).all()
    cases = visible_case_ids(ctx)
    out = [{"id": rid, **data} for rid, data in rows]
    return [c for c in out if _comment_visible(ctx, c, cases)]


def list_comments(ctx: CallContext, q: dict[str, Any]) -> list[dict[str, Any]]:
    return [c for c in _comments(ctx) if not q.get("key") or c["key"] == q["key"]]


def get_comment(ctx: CallContext, cid: str) -> dict[str, Any] | None:
    return next((c for c in _comments(ctx) if c["id"] == cid), None)


register(
    Resource(
        name="comments", list=list_comments, get=get_comment, create="comment.add", update=None, delete=None,
        fields=("key", "text"), filters=("key",),
        why_not={
            "update": "A comment stays as it was posted; add another.",
            "delete": "Comments are part of the audit trail and are never deleted.",
        },
    )
)  # fmt: skip


# ---------------------------------------------------------------- scenarios
def _scenarios(ctx: CallContext) -> list[dict[str, Any]]:
    cases = visible_case_ids(ctx)
    return [s for s in state.items(ctx.session, "scenarios") if s.get("case_id") in cases]


def list_scenarios(ctx: CallContext, q: dict[str, Any]) -> list[dict[str, Any]]:
    return [s for s in _scenarios(ctx) if not q.get("case_id") or s["case_id"] == q["case_id"]]


def get_scenario(ctx: CallContext, sid: str) -> dict[str, Any] | None:
    mine = next((s for s in _scenarios(ctx) if s["id"] == sid), None)
    if mine is None:  # one of a case this account may not see answers as that case does: 403 tenant_boundary
        other = next((s for s in state.items(ctx.session, "scenarios") if s["id"] == sid), None)
        if other:
            read(ctx, "case.get", {"case_id": other["case_id"]})
    return mine


register(
    Resource(
        name="scenarios", list=list_scenarios, get=get_scenario, create="scenario.save", update=None,
        delete="scenario.delete", from_row={"case_id": "case_id"}, fields=("case_id", "name", "scen", "top", "w"),
        filters=("case_id",), why_not={"update": "A saved what-if is not edited; save a new one and delete the old."},
    )
)  # fmt: skip


# ---------------------------------------------------------------- requests
def _requests(ctx: CallContext) -> list[dict[str, Any]]:
    p = principal(ctx)
    every = is_admin(ctx)
    return [
        r for r in request_rows(ctx.session, p)
        if every or r.get("byId") == p.account.id or p.can("approve." + REQ_SCOPE[r["kind"]])
    ]  # fmt: skip


def list_requests(ctx: CallContext, q: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        r for r in _requests(ctx)
        if (not q.get("kind") or r["kind"] == q["kind"]) and (not q.get("status") or r["status"] == q["status"])
    ]  # fmt: skip


def get_request(ctx: CallContext, rid: str) -> dict[str, Any] | None:
    return next((r for r in _requests(ctx) if r["id"] == rid), None)


register(
    Resource(
        name="requests", list=list_requests, get=get_request, create="access.requestTenant", update="access.decideRequest",
        delete=None, fields=("decision", "note", "reason", "tenant"), filters=("kind", "status"),
        why_not={"delete": "A request is kept with its decision; the journal records who decided it."},
    )
)  # fmt: skip


# ---------------------------------------------------------------- mcp-servers
def list_servers(ctx: CallContext, q: dict[str, Any]) -> list[dict[str, Any]]:  # noqa: ARG001 - no filters
    require_page(ctx, "mcp", "client")
    return mcp_screen.client_servers(ctx.session)["servers"]


def get_server(ctx: CallContext, sid: str) -> dict[str, Any] | None:
    return next((s for s in list_servers(ctx, {}) if s.get("id") == sid), None)


register(
    Resource(
        name="mcp-servers", list=list_servers, get=get_server, create="mcp.propose", update=None, delete=None,
        fields=("name", "owner", "purpose", "tools", "access", "data"),
        why_not={
            "update": "A server changes only through its proposal: decide it with PATCH /api/v1/requests/{id}.",
            "delete": "A server is retired by a new proposal that a person approves, not deleted here.",
        },
    )
)  # fmt: skip
