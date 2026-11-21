"""Connection Fabric actions (docs/backend-steps.md, B9): sync a source now, resolve or escalate a conflict.
The source lifecycle (source.update, source.delete, credentials.rotate, source.reconnect, and source.pause, resume,
disconnect and test) is in di.actions.fabric_sources (B17). tables.update, import.commit and the conflict handlers' bodies are in
di.actions.fabric_records."""

from typing import Any

from sqlalchemy import text

from di.actions import (
    fabric_records,  # also registers tables.update and import.commit
    fabric_sources,  # noqa: F401 - registers the source lifecycle (update, delete, reconnect ...)
)
from di.actions.pipeline import CallContext
from di.actions.registry import ActionError, implement
from di.connectors import lifecycle
from di.connectors.registry import ADAPTERS
from di.connectors.sync import enqueue_sync, provisioned


@implement("source.sync")
def source_sync(i: dict[str, Any], ctx: CallContext):
    sid = i["source_id"]
    status = ctx.session.execute(text("SELECT status FROM source_system WHERE id = :i"), {"i": sid}).scalar()
    if status is not None and lifecycle.is_deleted(ctx.session, sid):
        raise ActionError("not_found", f"No source {sid}.")
    if status is not None and sid not in ADAPTERS and status not in ("paused", "disconnected", "unavailable"):
        # connected from the catalogue or set up by hand (di.actions.fabric_sources): nothing simulated behind it
        raise ActionError(
            "conflict", f"No simulated system is behind {sid}, so there is nothing to sync. Its first sync was synthetic."
        )
    # a connector that is not provisioned yet (AWS IoT at start, B5c) counts as no connector, as in the demo
    if sid not in ADAPTERS or (status == "unavailable" and not provisioned(sid)):
        raise ActionError("not_found", f"No connector for {sid}.")
    if status in ("paused", "disconnected", "unavailable"):
        raise ActionError("conflict", f"{sid} is {status}. Resume or reconnect it first.")
    job = enqueue_sync(ctx.session, sid, "manual")
    return {
        "source_id": sid,
        "ref": f"JOB-{job}" if job else None,
        "queued": job is not None,
        "note": "Sync queued." if job else "A sync of this source is already queued.",
    }


@implement("conflict.resolve")
def conflict_resolve(i: dict[str, Any], ctx: CallContext):
    """Accept the authority's value, also after an escalation (an escalated conflict stays open, as in the demo)."""
    return fabric_records.resolve(ctx, i["id"])


@implement("conflict.escalate")
def conflict_escalate(i: dict[str, Any], ctx: CallContext):
    """Escalate to the authority's data owner; the conflict stays open and dependent routes stay held."""
    return fabric_records.escalate(ctx, i["id"])
