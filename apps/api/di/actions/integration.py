"""Connection Fabric actions (docs/backend-steps.md, B9): sync a source now, resolve or escalate a conflict.
The other Connection Fabric actions (source.update, source.delete, credentials.rotate, source.reconnect,
import.commit, tables.update) follow with the Connection Fabric switch-over (B17)."""

from sqlalchemy import text

from di.actions.registry import ActionError, implement
from di.connectors.registry import ADAPTERS
from di.connectors.sync import enqueue_sync, provisioned


@implement("source.sync")
def source_sync(i, ctx):
    sid = i["source_id"]
    status = ctx.session.execute(text("SELECT status FROM source_system WHERE id = :i"), {"i": sid}).scalar()
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


def _conflict(ctx, cid) -> dict:
    try:
        n = int(str(cid).removeprefix("CF-"))
    except ValueError as e:
        raise ActionError("not_found", f"No conflict {cid}.") from e
    row = ctx.session.execute(text("SELECT * FROM conflict WHERE id = :i"), {"i": n}).mappings().first()
    if row is None:
        raise ActionError("not_found", f"No conflict {cid}.")
    if row["status"] != "open":
        raise ActionError("conflict", f"Conflict CF-{n} is already {row['status']}.")
    return dict(row)


@implement("conflict.resolve")
def conflict_resolve(i, ctx):
    c = _conflict(ctx, i["id"])
    ctx.session.execute(
        text("UPDATE conflict SET status = 'resolved', closed_at = now(), closed_by = :by, note = :n WHERE id = :i"),
        {"by": ctx.actor.id, "n": f"Resolved in favour of {c['authority']} (the system with authority)", "i": c["id"]},
    )
    return {"id": f"CF-{c['id']}", "ref": f"CF-{c['id']}", "kept": c["authority"], "field": f"{c['model']}.{c['field']}"}


@implement("conflict.escalate")
def conflict_escalate(i, ctx):
    c = _conflict(ctx, i["id"])
    ctx.session.execute(
        text("UPDATE conflict SET status = 'escalated', closed_at = now(), closed_by = :by, note = :n WHERE id = :i"),
        {"by": ctx.actor.id, "n": f"Escalated to the owner of {c['authority']}", "i": c["id"]},
    )
    return {"id": f"CF-{c['id']}", "ref": f"CF-{c['id']}", "escalated_to": c["authority"]}
