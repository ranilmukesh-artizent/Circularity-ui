# ruff: noqa: E501 - long lines in the docstring table and the action declarations
"""Replay actions (plan 9, P9-7.1 and P9-7.2; registry entry I-16; story X-06): importing a batch of past decisions and
replaying it under a flow.

    replay.import   act   {pack, org_unit_id, csv, batch_id?}   check the CSV row by row (pandera, di.services.replay.history),
                                                                store the good rows and the held ones with their reasons;
                                                                answers the Batch. `batch_id` appends to a batch of the same
                                                                pack and org unit.
    replay.batches  read  {pack, org_unit_id}                   the org's batches with counts, period and the first 50 held rows

    replay.run      act   {batch_id, flow_id, flow_ver?}          queue an as-of replay of the batch under the flow (`flow_ver` is
                                                                "draft" or a version number as text; absent: the flow's draft if it
                                                                has one, else its published version); answers {run_id, status}
    replay.report   read  {run_id}                              the run's status and, once done, its ReplayReport
    replay.runs     read  {flow_id}                             the flow's runs, newest first, without their reports

The job `replay.run` (di/worker.py, `run_job` here) decides every ok item with `decide_case` as of its own date
(di.services.replay.run) and stores the report.

`runReplay` (Admin, Planner, Executive) is the permission of all; the Executive role only reads, so `replay.import` and
`replay.run` refuse it ("The Executive view reads replay reports; a Planner or Admin runs them."). An agent a planner
prepared may import or queue a replay (neither changes a decision). The org boundary is the one `flow.*` uses. A header that looks personal, a missing column or more than
25,000 rows refuses the whole import and stores nothing.
"""

import logging
from typing import Any, cast

from di.core import jobs
from di.core.db import SessionLocal
from di.repositories import flows as flow_repo
from di.repositories import replay as repo
from di.repositories.flows import FlowRow
from di.repositories.live_rules import live_pack
from di.repositories.orgs import units
from di.services.actions.modeler import _boundary, _org_ok
from di.services.actions.modeler import _reach as _flow_reach
from di.services.actions.pipeline import CallContext
from di.services.actions.registry import ACTIONS, ActionDef, ActionError, Risk, guard, implement
from di.services.modeler.compile import FlowVersion, compile_flow
from di.services.modeler.flow import Flow
from di.services.modeler.pack import Pack, load_pack, pack_keys
from di.services.modeler.templates import template_of_pack
from di.services.replay import history
from di.services.replay import run as replay_run

log = logging.getLogger(__name__)

_PERM = "runReplay"
EXECUTIVE = "The Executive view reads replay reports; a Planner or Admin runs them."


def _declare(action_id: str, title: str, verb: str, desc: str, risk: Risk, inp: dict[str, dict[str, Any]]) -> None:
    ACTIONS.setdefault(
        action_id,
        ActionDef(id=action_id, title=title, desc=desc, risk=risk, perm=_PERM, scope="none", input=inp, verb=verb),
    )


_BASE = {"pack": {"req": True, "t": "string"}, "org_unit_id": {"req": True, "t": "string"}}
_declare("replay.import", "Import a history batch", "import history",
         "Check a CSV of past decisions against a pack and store it: good rows are kept, bad rows are held with a reason.",
         "act", {**_BASE, "csv": {"req": True, "t": "string"}, "batch_id": {"t": "number"}})  # fmt: skip
_declare("replay.batches", "List history batches", "see history batches",
         "The history batches of a pack and org unit, with counts, the decision period and the first 50 held rows.",
         "read", _BASE)  # fmt: skip
_declare("replay.run", "Replay a history batch", "replay history",
         "Decide every item of a history batch as of its own date under a flow (its draft or a version) and measure the "
         "route mix, straight-through, approvals and exceptions per day, and the uplift.",
         "act", {"batch_id": {"req": True, "t": "number"}, "flow_id": {"req": True, "t": "number"}, "flow_ver": {"t": "string"}})  # fmt: skip
_declare(
    "replay.report",
    "Read a replay report",
    "read a replay",
    "The status of a replay run and, once it is done, its report.",
    "read",
    {"run_id": {"req": True, "t": "number"}},
)
_declare("replay.runs", "List replay runs", "see replays", "The replay runs of a decision flow, newest first.",
         "read", {"flow_id": {"req": True, "t": "number"}})  # fmt: skip


def _reach(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | Pack:
    """The pack, or the refusal: unknown pack or org unit, or an org unit outside the actor's tenants."""
    org = i["org_unit_id"]
    if org not in units(ctx.session):
        return "not_found", f"No org unit {org}."
    if not _org_ok(ctx, org):
        return _boundary(org)
    if i["pack"] not in pack_keys():
        return "not_found", f"No pack {i['pack']}."
    return load_pack(i["pack"])


@guard("replay.import")
def import_guard(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | None:
    if ctx.actor.role == "Executive":
        return "out_of_scope", EXECUTIVE
    pack = _reach(i, ctx)
    if not isinstance(pack, Pack):
        return pack
    if i.get("batch_id") is not None:
        b = repo.get(ctx.session, int(i["batch_id"]))
        if b is None:
            return "not_found", f"No history batch {i['batch_id']}."
        if (b["pack"], b["org_unit_id"]) != (pack.key, i["org_unit_id"]):
            return "conflict", "A batch is appended to only for its own pack and org unit."
    try:
        rows = history.parse_csv(i["csv"])
        if not rows:
            raise history.HistoryRefused("The file has no rows.")
        if len(rows) > history.MAX_ROWS:
            raise history.HistoryRefused(f"At most {history.MAX_ROWS:,} rows per import.")
        history.check_header({k for r in rows for k in r}, pack)
    except history.HistoryRefused as e:
        return "validation_error", str(e)
    return None


@implement("replay.import")
def import_batch(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    pack = load_pack(i["pack"])
    s = ctx.session
    if i.get("batch_id") is not None:
        bid = int(i["batch_id"])
        repo.get(s, bid, for_update=True)
        seen = repo.item_ids(s, bid)
    else:
        bid, seen = repo.create(s, pack.key, i["org_unit_id"], ctx.actor.id), set()
    try:
        ok, held = history.import_history(history.parse_csv(i["csv"]), pack, now=ctx.now, seen=seen)
    except history.HistoryRefused as e:
        raise ActionError("validation_error", str(e)) from e
    start = repo.last_n(s, bid)
    repo.add_items(s, bid, ok, held=False, start=start)
    repo.add_items(s, bid, held, held=True, start=start)
    batch = repo.refresh(s, bid)
    return {**batch.view(), "log": f"Imported {len(ok) + len(held)} history rows for {pack.key}: {len(held)} held"}


@guard("replay.batches")
def batches_guard(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | None:
    r = _reach(i, ctx)
    return None if isinstance(r, Pack) else r


@implement("replay.batches")
def list_batches(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    out = [
        {**b.view(), "held_items": repo.held_items(ctx.session, b.id)}
        for b in repo.for_org(ctx.session, i["pack"], i["org_unit_id"])
    ]
    return {"batches": out}


# ---------------------------------------------------------------- run (P9-7.2)
def _label(ctx: CallContext, f: FlowRow, raw: Any) -> str | tuple[str, str]:
    """The flow version to replay as text, `draft` or a number, or the refusal. Absent means the draft when there is one."""
    ver = str(raw).strip().lower() if raw not in (None, "") else ("draft" if f.draft is not None else str(f.ver))
    if ver == "draft":
        return ver if f.draft is not None else ("validation_error", f"{f.name} has no draft to replay.")
    if not ver.isdigit():
        return "validation_error", 'flow_ver is "draft" or a version number.'
    n = int(ver)
    if n != f.ver and all(v.ver != n for v in flow_repo.versions(ctx.session, f.id)):
        return "not_found", f"{f.name} has no version {n}."
    return str(n)


def _batch_flow(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | tuple[dict[str, Any], FlowRow]:
    """The batch and the flow of a run, or the refusal: unknown, outside the actor's orgs, or a flow of another pack."""
    b = repo.get(ctx.session, int(i["batch_id"]))
    if b is None:
        return "not_found", f"No history batch {i['batch_id']}."
    if not _org_ok(ctx, b["org_unit_id"]):
        return _boundary(b["org_unit_id"])
    f = _flow_reach(i, ctx)
    if isinstance(f, tuple):
        return f
    if f.template_key != b["pack"]:
        return "conflict", f"The batch is history of {b['pack']}; {f.name} is a flow of {f.template_key}."
    return b, f


@guard("replay.run")
def run_guard(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | None:
    if ctx.actor.role == "Executive":
        return "out_of_scope", EXECUTIVE
    got = _batch_flow(i, ctx)
    if isinstance(got[0], str):
        return got
    label = _label(ctx, got[1], i.get("flow_ver"))
    return label if isinstance(label, tuple) else None


@implement("replay.run")
def run(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    got = _batch_flow(i, ctx)
    f = cast(FlowRow, got[1])
    label = cast(str, _label(ctx, f, i.get("flow_ver")))
    dver = (f.dver or f.ver + 1) if label == "draft" else None
    run_id = repo.create_run(ctx.session, int(i["batch_id"]), f.id, label, dver, ctx.actor.id)
    jobs.enqueue(ctx.session, "replay.run", {"run_id": run_id}, dedupe_key=f"replay.run:{run_id}")
    return {"run_id": run_id, "status": "queued", "log": f"Queued a replay of batch {i['batch_id']} under {f.name} ({label})"}


def _run_reach(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | dict[str, Any]:
    r = repo.get_run(ctx.session, int(i["run_id"]))
    if r is None:
        return "not_found", f"No replay run {i['run_id']}."
    b = repo.get(ctx.session, r["batch_id"])
    if b is not None and not _org_ok(ctx, b["org_unit_id"]):
        return _boundary(b["org_unit_id"])
    return r


@guard("replay.report")
def report_guard(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | None:
    r = _run_reach(i, ctx)
    return r if isinstance(r, tuple) else None


@implement("replay.report")
def report(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    r = cast(dict[str, Any], _run_reach(i, ctx))
    return _run_view(r) | {"report": r["report"]}


def _run_view(r: dict[str, Any]) -> dict[str, Any]:
    return {
        "run_id": r["id"], "batch_id": r["batch_id"], "flow_id": r["flow_id"], "flow_ver": r["flow_ver"], "dver": r["dver"],
        "status": r["status"], "error": r["error"], "created_by": r["created_by"], "created_at": r["created_at"].isoformat(),
        "finished_at": r["finished_at"].isoformat() if r["finished_at"] else None,
    }  # fmt: skip


@guard("replay.runs")
def runs_guard(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | None:
    f = _flow_reach(i, ctx)
    return f if isinstance(f, tuple) else None


@implement("replay.runs")
def runs(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    return {"runs": [_run_view(r) for r in repo.runs_of_flow(ctx.session, int(i["flow_id"]))]}


# ---------------------------------------------------------------- the job
def flow_version(s: Any, f: FlowRow, pack: Pack, label: str) -> FlowVersion:
    """The flow version a run replays: the draft (its next version), the published graph, or an earlier version's graph, with
    the rules it compiles to under the pack's template."""
    t = template_of_pack(pack)
    if label == "draft":
        return FlowVersion(f.id, f.dver or f.ver + 1, tuple(compile_flow(t, cast(Flow, f.draft))))
    n = int(label)
    graph = f.published if n == f.ver else next(v.graph for v in flow_repo.versions(s, f.id) if v.ver == n)
    return FlowVersion(f.id, n, tuple(compile_flow(t, cast(Flow, graph))))


def run_job(payload: dict[str, Any]) -> dict[str, Any]:
    """The worker job `replay.run`: mark the run running, replay the batch, store the report (done) or the error (failed). A
    run that is not queued is left alone (a retry of a job that already finished)."""
    run_id = int(payload["run_id"])
    with SessionLocal() as s:
        r = repo.get_run(s, run_id, for_update=True)
        if r is None or r["status"] != "queued":
            return {"run_id": run_id, "status": r["status"] if r else "missing"}
        repo.set_status(s, run_id, "running")
        s.commit()
    try:
        with SessionLocal() as s:
            r = cast(dict[str, Any], repo.get_run(s, run_id))
            batch = repo.batches(s, [r["batch_id"]])[0]
            f = cast(FlowRow, flow_repo.get_flow(s, r["flow_id"]))
            pack = live_pack(s, {"template": f.template_key, "owner": batch.org_unit_id})
            rep = replay_run.replay(
                batch, repo.ok_items(s, batch.id), flow_version(s, f, pack, r["flow_ver"]), pack=pack, run_id=run_id,
                label=r["flow_ver"],
            )  # fmt: skip
            repo.set_status(s, run_id, "done", report=rep.model_dump(mode="json"))
            s.commit()
    except Exception as e:
        log.exception("replay run %s failed", run_id)
        with SessionLocal() as s:
            repo.set_status(s, run_id, "failed", error=f"{type(e).__name__}: {e}")
            s.commit()
        return {"run_id": run_id, "status": "failed"}
    return {"run_id": run_id, "status": "done"}
