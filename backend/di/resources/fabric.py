"""The Connection Fabric resources (plan 3 task 3): sources, conflicts, instructions.

`sources`: read through the Integration screen's own functions (`di.services.screens.integration`), for a role that
sees an Integration page. create = `source.connect`, update = `source.update`, delete = `source.delete`;
`PATCH {action: sync|pause|resume|reconnect|rotate}` runs the source's other actions.
`conflicts`: the Conflict Queue (page integration/conflicts); `PATCH {action: resolve|escalate}`. No create (a conflict
arises when two sources disagree) and no delete (resolved ones stay as the record).
`instructions`: the outbound instructions to the enterprise systems, only those of cases the account may see;
`PATCH {action: resend}`. No create (approving a decision queues them) and no delete.
"""

from typing import Any

from sqlalchemy import text

from di.core.errors import ApiError
from di.resources import Resource, register
from di.resources.support import BIG, principal, read, require_page, visible_case_ids
from di.services.actions.pipeline import CallContext
from di.services.screens import integration as screen

SOURCE_SECTIONS = ("overview", "map", "tables", "models", "monitor")


# ---------------------------------------------------------------- sources
def list_sources(ctx: CallContext, q: dict[str, Any]) -> list[dict[str, Any]]:
    require_page(ctx, "integration", *SOURCE_SECTIONS)
    out = screen.sources(ctx.session, principal(ctx), q.get("cat"), q.get("status"), q.get("method"), q.get("q"))
    return out["sources"]


def get_source(ctx: CallContext, source_id: str) -> dict[str, Any] | None:
    require_page(ctx, "integration", *SOURCE_SECTIONS)
    detail = screen.source_detail(ctx.session, principal(ctx), source_id, 30)
    return None if detail is None else {"id": source_id, **detail}


register(
    Resource(
        name="sources", list=list_sources, get=get_source, create="source.connect", update="source.update",
        delete="source.delete", id_field="source_id", id_keys={"source.update": "id"},
        filters=("cat", "status", "method", "q"),  # no `fields`: the action's own inputs are the check (the router)
        update_actions={
            "sync": "source.sync", "pause": "source.pause", "resume": "source.resume", "reconnect": "source.reconnect",
            "rotate": "credentials.rotate",
        },
    )
)  # fmt: skip


# ---------------------------------------------------------------- conflicts
def _conflicts(ctx: CallContext, status: str, source: str | None) -> list[dict[str, Any]]:
    require_page(ctx, "integration", "conflicts")
    if status not in ("open", "resolved", "all"):
        raise ApiError("validation_error", "status is open, resolved or all.", 422)
    return screen.conflicts(ctx.session, principal(ctx), status, source, BIG)["conflicts"]  # type: ignore[arg-type]


def list_conflicts(ctx: CallContext, q: dict[str, Any]) -> list[dict[str, Any]]:
    return _conflicts(ctx, q.get("status") or "open", q.get("source"))


def get_conflict(ctx: CallContext, conflict_id: str) -> dict[str, Any] | None:
    return next((c for c in _conflicts(ctx, "all", None) if c["id"] == conflict_id), None)


register(
    Resource(
        name="conflicts", list=list_conflicts, get=get_conflict, create=None, update=None, delete=None,
        filters=("status", "source"), update_actions={"resolve": "conflict.resolve", "escalate": "conflict.escalate"},
        why_not={
            "create": "A conflict is raised when two sources disagree about a field; it is not created by hand.",
            "update": "Say what to do: PATCH with an action (resolve or escalate).",
            "delete": "A resolved conflict stays as the record of how the sources were reconciled.",
        },
    )
)  # fmt: skip


# ---------------------------------------------------------------- instructions
INSTRUCTION_COLUMNS = (
    "id, case_id, approval_ref, step, kind, system, doc_ref, status, simulated, waiting_for, attempts, last_error, "
    "queued_at, sent_at, acknowledged_at"
)


def list_instructions(ctx: CallContext, q: dict[str, Any]) -> list[dict[str, Any]]:
    rows = ctx.session.execute(
        text(
            f"SELECT {INSTRUCTION_COLUMNS} FROM instruction "  # noqa: S608 - fixed column list; values are bound
            "WHERE (CAST(:c AS text) IS NULL OR case_id = :c) AND (CAST(:s AS text) IS NULL OR status = :s) "
            "AND (CAST(:y AS text) IS NULL OR system = :y) ORDER BY id"
        ),
        {"c": q.get("case_id"), "s": q.get("status"), "y": q.get("system")},
    ).mappings()
    seen = visible_case_ids(ctx)
    return [dict(r) for r in rows if r["case_id"] in seen]


def get_instruction(ctx: CallContext, instruction_id: str) -> dict[str, Any] | None:
    if not instruction_id.isdigit():
        return None
    row = (
        ctx.session.execute(
            text(f"SELECT {INSTRUCTION_COLUMNS} FROM instruction WHERE id = :i"),  # noqa: S608 - fixed column list
            {"i": int(instruction_id)},
        )
        .mappings()
        .first()
    )
    if row is None:
        return None
    read(ctx, "case.get", {"case_id": row["case_id"]})  # the tenant boundary and warehouse lock of its case: 403
    return dict(row)


register(
    Resource(
        name="instructions", list=list_instructions, get=get_instruction, create=None, update=None, delete=None,
        filters=("case_id", "status", "system"), update_actions={"resend": "instruction.resend"},
        id_keys={"instruction.resend": ""}, from_row={"case_id": "case_id"},
        why_not={
            "create": "Instructions are queued when a decision is approved; they are not created by hand.",
            "update": "Say what to do: PATCH with action resend.",
            "delete": "An instruction is part of the audit trail and is never deleted.",
        },
    )
)  # fmt: skip
