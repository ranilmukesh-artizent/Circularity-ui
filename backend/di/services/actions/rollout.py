# ruff: noqa: E501 - long lines in the docstring table and the action declarations
"""Publishing a flow in steps (plan 9, P9-7.3; registry entry I-17; story X-06): a canary by region and share, then full.

A flow approved into `shadow` (flow.approve) has a candidate version, its draft. Instead of publishing it for everyone at once
(`flow.publish` still does, for a person with approve.flows), the candidate is released to a share of one region's cases:

    rollout.startCanary {flow_id, region_key?, region, share}  commit  the flow is in shadow and a replay of the candidate is done;
                                                               share 1-99; `region_key` is a case fact (default `market`)
    rollout.widen       {flow_id, share?, region?}             commit  the share only rises; a new region adds a row; widening a
                                                               paused canary resumes it
    rollout.pause       {flow_id, reason}                      commit  new cases go back to the base version (no maker-checker:
                                                               it moves towards the known-good version)
    rollout.full        {flow_id}                              commit  the `flow.publish` path for the candidate; the base version
                                                               goes to history
    rollout.rollback    {flow_id, reason}                      commit  the canary ends; assignments of cases not yet approved are
                                                               deleted (they use the base version next), approved ones keep theirs
    rollout.get         {flow_id}                              read    stage, rows, counts per arm, the replay, what is refused and why
    rollout.report      {flow_id}                              read    canary against control: cases, override, exception and hold
                                                               rates, mean net with the band of the difference, the sample note
    rollout.autoPause   {rollout_id, reason}                   system  the worker pauses a canary whose stop rule is breached

Which version decides a case is `di.repositories.rollouts.version_for`, used by di.repositories.live_rules.flow_version; a stored
assignment is kept through approval, execution and close. Starting, widening and going full are refused for anyone who made the
flow's changes (maker-checker, the same journal rule as flow.approve). Every write is journaled. No agent may run any of them
(`rollout.` in di.services.agents.forbidden); `rollout.get` and `rollout.report` are reads.

Canary report and automatic pause (P9-7.4): `rollout.report` is computed by di.services.modeler.canary_stats from the arms' cases
(no model, no free text: every figure is code). After a `decision.submit` or `decision.override` on a case in a running canary,
a `rollout.watch` job (deduped per rollout) checks the stop rules stored at canary start; a breach runs `rollout.autoPause` as
SYSTEM: the canary pauses (new cases use the base version, the way `rollout.pause` does), the journal row is by `system`, a
`rollout.paused` event is written and a My work task opens for each role with approve.flows. That is the only thing the system
does on its own, because a pause moves towards the known-good version. Widening, adding a region and going full stay a person's.
"""

import hashlib
from typing import Any, cast

from sqlalchemy import text

from di.core import jobs, policy
from di.repositories import flows as flow_repo
from di.repositories import market_tables as tables_repo
from di.repositories import rollouts as repo
from di.repositories.flows import FlowRow
from di.services.actions import modeler as flows
from di.services.actions.modeler import _boundary, _org_ok, _reach, makers
from di.services.actions.pipeline import SYSTEM, CallContext, after, invoke
from di.services.actions.registry import ACTIONS, ActionDef, ActionError, Risk, guard, implement
from di.services.cases import process
from di.services.modeler import canary_stats as stats
from di.services.modeler.rollout import Rollout, Stage, can_move
from di.services.modeler.tables import market_spec
from di.services.service_desk import inputs as sd_inputs

_APPROVE = "approve.flows"
MAKER = "Maker-checker: you made these changes, so you cannot widen their rollout."
NEEDS_REPLAY = "Run a replay of v{v} before a canary (Modeler, Replay)."
STALE_REPLAY = "Replay again: the draft changed since the last replay."
_NEED_REASON = {"req": True, "t": "string", "min": 15, "minText": "Add a reason of at least 15 characters."}
# A flow, or (P9-7.7) the service-desk tables of the org's tool-fleet flow: `subject_kind` "table" with `subject_id` the flow id.
_ID = {"flow_id": {"t": "number"}, "subject_kind": {"t": "string"}, "subject_id": {"t": "string"}}
NEEDS_TABLE_REPLAY = "Run a replay of the service desk flow before a table canary (Modeler, Replay)."
TABLES_FULL = "The market's tables go live through their own approval (Modeler, Tables); end this canary with Roll back."


def _declare(
    action_id: str, title: str, verb: str, desc: str, risk: Risk, inp: dict[str, dict[str, Any]], perm: str | None
) -> None:
    ACTIONS.setdefault(
        action_id, ActionDef(id=action_id, title=title, desc=desc, risk=risk, perm=perm, scope="none", input=inp, verb=verb)
    )


_declare("rollout.startCanary", "Start a canary", "publish decision flows in steps",
         "Release the approved candidate of a flow to a share of one region's cases (after a replay of it).", "commit",
         {**_ID, "region_key": {"t": "string"}, "region": {"req": True, "t": "string"},
          "share": {"req": True, "t": "number", "min": 1, "max": 99}}, _APPROVE)  # fmt: skip
_declare("rollout.widen", "Widen a canary", "publish decision flows in steps",
         "Raise the share of a canary, or add a region. The share only rises.", "commit",
         {**_ID, "share": {"t": "number", "min": 1, "max": 99}, "region": {"t": "string"}}, _APPROVE)  # fmt: skip
_declare("rollout.pause", "Pause a canary", "publish decision flows in steps",
         "New cases go back to the base version; cases already in the canary keep theirs.", "commit",
         {**_ID, "reason": _NEED_REASON}, _APPROVE)  # fmt: skip
_declare("rollout.full", "Publish a canary in full", "publish decision flows in steps",
         "Publish the candidate for every case (the flow.publish path).", "commit", _ID, _APPROVE)  # fmt: skip
_declare("rollout.rollback", "Roll back a canary", "publish decision flows in steps",
         "End the canary: cases not yet approved use the base version again.", "commit",
         {**_ID, "reason": _NEED_REASON}, _APPROVE)  # fmt: skip
_declare("rollout.report", "Read a canary report", "see how a canary compares with its control",
         "Canary against control: cases, override, exception and hold rates, mean net with the band of the difference. Changes nothing.",
         "read", _ID, None)  # fmt: skip
ACTIONS.setdefault(
    "rollout.autoPause",
    ActionDef(id="rollout.autoPause", title="Pause a canary automatically", verb="pause a canary automatically", risk="system",
              desc="The worker pauses a canary whose stop rule is breached: new cases use the base version again.", perm=None,
              scope="none", input={"rollout_id": {"req": True, "t": "number"}, "reason": {"req": True, "t": "string"}}),
)  # fmt: skip
_declare("rollout.get", "Read a rollout", "see how a flow is published",
         "The stage of a flow's publish steps, its canary rows and counts per arm. Changes nothing.", "read", _ID, None)  # fmt: skip


# ---------------------------------------------------------------- helpers
def current_stage(s: Any, f: FlowRow) -> Stage | None:
    """Where the flow is in the publish steps: a running or paused canary, else shadow (approved), replay (a draft), or a
    ended rollout; None for a published flow that never had one."""
    rows = repo.active_rollout(s, f.id)
    if rows:
        return "paused" if all(r.stage == "paused" for r in rows) else "canary"
    last = repo.latest_stage(s, f.id)
    if f.status == "shadow":
        return "rolled_back" if last == "rolled_back" else "shadow"
    if f.status in ("draft", "review"):
        return "replay"
    return "full" if last == "full" else None


def _kind(i: dict[str, Any]) -> str:
    return str(i.get("subject_kind") or "flow")


def _norm(i: dict[str, Any]) -> dict[str, Any]:
    """The input with `flow_id` filled from `subject_id` (a table rollout hangs on the flow of the tool-fleet pack)."""
    raw = i.get("flow_id") if i.get("flow_id") is not None else i.get("subject_id")
    try:
        fid: int | None = int(raw) if raw is not None else None
    except (TypeError, ValueError):
        fid = None
    return {**i, "flow_id": fid}


def _bad_subject(i: dict[str, Any]) -> tuple[str, str] | None:
    if _kind(i) not in ("flow", "table"):
        return "validation_error", "The subject of a rollout is a flow or its decision tables."
    if _norm(i)["flow_id"] is None:
        return "validation_error", "Name the flow (flow_id), or the flow the tables belong to (subject_id)."
    return None


def _gate(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | FlowRow:
    """The flow, or the refusal: unknown, outside the actor's orgs, or prepared by an agent."""
    if bad := _bad_subject(i):
        return bad
    f = _reach(_norm(i), ctx)
    if isinstance(f, tuple):
        return f
    return ("approval_required", "A flow is published, widened or rolled back only by a person.") if ctx.preparer else f


def _maker(
    ctx: CallContext, f: FlowRow, i: dict[str, Any] | None = None, regions: list[str] | None = None
) -> tuple[str, str] | None:
    """Maker-checker: the flow's makers; for a table rollout the makers of the markets' tables (`regions`) and the flow's maker."""
    who = set(makers(ctx, f))
    if i is not None and _kind(i) == "table":
        who = {x for m in regions or [] for x in repo.table_makers(ctx.session, m)} | ({f.maker} if f.maker else set())
    return ("conflict", MAKER) if ctx.actor.id in who else None


def _view(r: Rollout) -> dict[str, Any]:
    return {"id": r.id, "stage": r.stage, "region_key": r.region_key, "region": r.region, "share": r.share,
            "candidate_ver": r.candidate_ver, "base_ver": r.base_ver}  # fmt: skip


def _share(i: dict[str, Any]) -> tuple[str, str] | None:
    sh = i.get("share")
    if sh is None:
        return None
    if isinstance(sh, bool) or not isinstance(sh, int | float) or int(sh) != sh or not 1 <= sh <= 99:
        return "validation_error", "The share is a whole number from 1 to 99 (use Full to release to everyone)."
    return None


def _flow_of(ctx: CallContext, i: dict[str, Any]) -> FlowRow:
    i = _norm(i)
    f = flow_repo.get_flow(ctx.session, int(i["flow_id"]), for_update=True)
    if f is None:
        raise ActionError("not_found", f"No decision flow {i['flow_id']}.")
    return f


# ---------------------------------------------------------------- start
@guard("rollout.startCanary")
def start_guard(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | None:
    f = _gate(i, ctx)
    if isinstance(f, tuple):
        return f
    if bad := _share(i):
        return bad
    if not str(i.get("region") or "").strip():
        return "validation_error", "Name the region the canary runs in."
    if _kind(i) == "table":
        return _table_start_guard(i, ctx, f)
    stage = current_stage(ctx.session, f)
    if not can_move("shadow" if stage == "rolled_back" else stage, "canary"):
        if repo.active_rollout(ctx.session, f.id):
            return "conflict", f"A canary of {f.name} is already running; widen it instead."
        return "conflict", f"{f.name} must be approved into shadow before a canary."
    if bad := _maker(ctx, f):
        return bad
    if repo.done_replay(ctx.session, f) is None:
        return "conflict", _replay_needed(ctx, f)
    return None


def _replay_needed(ctx: CallContext, f: FlowRow) -> str:
    """Why the flow's draft has no replay a canary may start from: the draft changed after one, or none ran."""
    return STALE_REPLAY if repo.stale_replay(ctx.session, f) else NEEDS_REPLAY.format(v=f.dver)


@implement("rollout.startCanary")
def start(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    f = _flow_of(ctx, i)
    if _kind(i) == "table":
        return _table_start(i, ctx, f)
    key, region, share = (i.get("region_key") or "market").strip(), str(i["region"]).strip(), int(i["share"])
    salt = hashlib.sha256(f"{f.id}:{f.dver}:{ctx.now.isoformat()}".encode()).hexdigest()[:16]
    run = repo.done_replay(ctx.session, f)
    rid = repo.insert(ctx.session, f.id, candidate=f.dver, base=f.ver, region_key=key, region=region, share=share,
                      salt=salt, by=ctx.actor.id, run_id=run)  # fmt: skip
    return {"flow_id": f.id, "rollout_id": rid, "stage": "canary", "region_key": key, "region": region, "share": share,
            "candidate_ver": f.dver, "base_ver": f.ver, "replay_run_id": run,
            "log": f"Canary of {f.name} v{f.dver}: {key} {region} at {share} % of volume (base v{f.ver})"}  # fmt: skip


# ---------------------------------------------------------------- the market canary of the service-desk tables (P9-7.7, SD-10)
def _table_start_guard(i: dict[str, Any], ctx: CallContext, f: FlowRow) -> tuple[str, str] | None:
    """The same checks as a flow canary, on the tables: the flow is the tool fleet's, the region a market of the service desk with
    approved tables, no canary runs there, the actor made none of the market's tables, and a replay of the flow is done."""
    s, market = ctx.session, str(i["region"]).strip()
    spec = market_spec(repo.TABLE_PACK)
    if f.template_key != repo.TABLE_FLOW or spec is None:
        return "conflict", "Decision tables belong to the tool fleet's service desk flow."
    if market not in spec.markets:
        return "validation_error", f"{market} is not a market of the service desk ({', '.join(sorted(spec.markets))})."
    if any(r.region == market for r in repo.active_rollout(s, f.id, "table")):
        return "conflict", f"A table canary for {market} is already running; widen it instead."
    if bad := _maker(ctx, f, i, [market]):
        return bad
    if repo.done_replay_any(s, f.id) is None:
        return "conflict", NEEDS_TABLE_REPLAY
    tables_repo.ensure_seeded(s, repo.TABLE_PACK)
    if any(
        tables_repo.effective(s, None, repo.TABLE_PACK, spec.flow, market, n, ctx.now.date()) is None for n in sd_inputs.CARDS
    ):
        return "conflict", f"{market} has no approved tables to pilot."
    return None


def _table_start(i: dict[str, Any], ctx: CallContext, f: FlowRow) -> dict[str, Any]:
    market, share = str(i["region"]).strip(), int(i["share"])
    salt = hashlib.sha256(f"{f.id}:table:{market}:{ctx.now.isoformat()}".encode()).hexdigest()[:16]
    run = repo.done_replay_any(ctx.session, f.id)
    rid = repo.insert(ctx.session, f.id, candidate=None, base=None, region_key="market", region=market, share=share, salt=salt,
                      by=ctx.actor.id, run_id=run, kind="table")  # fmt: skip
    std = repo.standard_market(market)
    return {"flow_id": f.id, "subject_kind": "table", "subject_id": str(f.id), "rollout_id": rid, "stage": "canary",
            "region_key": "market", "region": market, "share": share, "standard_market": std, "replay_run_id": run,
            "log": f"Table canary of {f.name}: {market} tables at {share} % of {market} tickets (the rest: the standard quote, {std} tables)"}  # fmt: skip


def _table_stage(s: Any, f: FlowRow) -> Stage:
    """Where the service-desk tables of the flow are: a running or paused canary, rolled back, else ready for a canary."""
    rows = repo.active_rollout(s, f.id, "table")
    if rows:
        return "paused" if all(r.stage == "paused" for r in rows) else "canary"
    return "rolled_back" if repo.latest_stage(s, f.id, "table") == "rolled_back" else "shadow"


def _table_can(ctx: CallContext, f: FlowRow, stage: Stage) -> dict[str, str | None]:
    """What this person may do with the tables' rollout now, and the reason when not (the panel shows them)."""
    s = ctx.session
    blocked = ctx.actor.id in {x for r in repo.active_rollout(s, f.id, "table") for x in repo.table_makers(s, str(r.region))}
    running = stage in ("canary", "paused")
    return {
        "startCanary": None if repo.done_replay_any(s, f.id) is not None else NEEDS_TABLE_REPLAY,
        "widen": None if running and not blocked else (MAKER if blocked else "No canary is running."),
        "pause": None if stage == "canary" else "No canary is running.",
        "full": TABLES_FULL,
        "rollback": None if running else "No canary is running.",
    }


# ---------------------------------------------------------------- widen
@guard("rollout.widen")
def widen_guard(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | None:
    f = _gate(i, ctx)
    if isinstance(f, tuple):
        return f
    if bad := _share(i):
        return bad
    if i.get("share") is None and not i.get("region"):
        return "validation_error", "Give a higher share or a region to add."
    rows = repo.active_rollout(ctx.session, f.id, _kind(i))
    if not rows:
        return "conflict", f"No canary is running for {f.name}."
    region, share = str(i.get("region") or "").strip() or None, i.get("share")
    if bad := _maker(ctx, f, i, [str(r.region) for r in rows] + ([region] if region else [])):
        return bad
    target = [r for r in rows if region is None or r.region == region]
    if share is not None and (low := next((r for r in target if int(share) < r.share), None)):
        return "conflict", f"The share only rises: {low.region} is at {low.share} %."
    return None


@implement("rollout.widen")
def widen(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    f = _flow_of(ctx, i)
    kind = _kind(i)
    rows = repo.active_rollout(ctx.session, f.id, kind)
    region = str(i.get("region") or "").strip() or None
    share = int(i["share"]) if i.get("share") is not None else None
    target = [r for r in rows if region is None or r.region == region]
    for r in target:
        if share is not None:
            repo.set_share(ctx.session, r.id, share, ctx.actor.id, ctx.now)
    if region is not None and not target:  # a new region: a row of its own on the same candidate and salt
        first = rows[0]
        base = first.base_ver if kind == "table" else (first.base_ver or f.ver)
        repo.insert(ctx.session, f.id, candidate=first.candidate_ver, base=base, region_key=first.region_key,
                    region=region, share=share if share is not None else first.share, salt=first.salt, by=ctx.actor.id,
                    run_id=None, kind=kind)  # fmt: skip
    if any(r.stage == "paused" for r in rows):  # widening a paused canary resumes it
        repo.set_stage(ctx.session, f.id, "canary", ("paused",), ctx.actor.id, ctx.now, kind=kind)
        if kind == "flow":
            _close_pause_items(ctx, f.id, "resumed")
    now = repo.active_rollout(ctx.session, f.id, kind)
    return {"flow_id": f.id, "stage": "canary", "rollouts": [_view(r) for r in now],
            "log": f"Widened the canary of {f.name}: " + ", ".join(f"{r.region} at {r.share} %" for r in now)}  # fmt: skip


# ---------------------------------------------------------------- pause, full, rollback
@guard("rollout.pause")
def pause_guard(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | None:
    f = _gate(i, ctx)
    if isinstance(f, tuple):
        return f
    stage = _table_stage(ctx.session, f) if _kind(i) == "table" else current_stage(ctx.session, f)
    return None if can_move(stage, "paused") else ("conflict", f"No canary is running for {f.name}.")


@implement("rollout.pause")
def pause(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    f = _flow_of(ctx, i)
    repo.set_stage(ctx.session, f.id, "paused", ("canary",), ctx.actor.id, ctx.now,
                   {"paused": {"reason": i["reason"], "by": ctx.actor.id, "at": ctx.now.isoformat()}}, kind=_kind(i))  # fmt: skip
    return {
        "flow_id": f.id,
        "stage": "paused",
        "log": f"Paused the canary of {f.name}: new cases use v{f.ver}",
        "reason": i["reason"],
    }


@guard("rollout.full")
def full_guard(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | None:
    f = _gate(i, ctx)
    if isinstance(f, tuple):
        return f
    if _kind(i) == "table":
        return "conflict", TABLES_FULL
    stage = current_stage(ctx.session, f)
    if not can_move(stage, "full"):
        return "conflict", (
            "Widen the paused canary to resume it before going full." if stage == "paused"
            else f"Start a canary of {f.name} before publishing it in full."
        )  # fmt: skip
    if f.status != "shadow":
        return "conflict", f"{f.name} must be approved before it is published."
    return _maker(ctx, f)


@implement("rollout.full")
def full(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    f = _flow_of(ctx, i)
    out = flows.publish({"flow_id": f.id}, ctx)  # the flow.publish path: the base version goes to history
    repo.set_stage(ctx.session, f.id, "full", ("canary", "paused"), ctx.actor.id, ctx.now)
    _close_pause_items(ctx, f.id, "published in full")
    return {**out, "stage": "full", "flow_id": f.id, "log": f"Published {f.name} v{out['ver']} in full after its canary"}


@guard("rollout.rollback")
def rollback_guard(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | None:
    f = _gate(i, ctx)
    if isinstance(f, tuple):
        return f
    return None if repo.active_rollout(ctx.session, f.id, _kind(i)) else ("conflict", f"No canary is running for {f.name}.")


@implement("rollout.rollback")
def rollback(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    f = _flow_of(ctx, i)
    kind = _kind(i)
    repo.set_stage(ctx.session, f.id, "rolled_back", ("canary", "paused"), ctx.actor.id, ctx.now,
                   {"rolled_back": {"reason": i["reason"], "by": ctx.actor.id, "at": ctx.now.isoformat()}}, kind=kind)  # fmt: skip
    cleared = repo.clear_undecided(ctx.session, f.id, kind)
    if kind == "table":
        return {"flow_id": f.id, "stage": "rolled_back", "cleared": cleared, "reason": i["reason"],
                "log": f"Rolled back the table canary of {f.name}: {cleared} undecided tickets use the standard quote again"}  # fmt: skip
    _close_pause_items(ctx, f.id, "rolled back")
    return {"flow_id": f.id, "stage": "rolled_back", "cleared": cleared, "reason": i["reason"],
            "log": f"Rolled back the canary of {f.name}: {cleared} undecided cases use v{f.ver} again"}  # fmt: skip


# ---------------------------------------------------------------- read
def _read_guard(i: dict[str, Any], ctx: CallContext, perms: tuple[str, ...]) -> tuple[str, str] | None:
    acct = ctx.actor.account
    if acct is None or not any(policy.can(acct, p, ctx.actor.ctx) for p in perms):
        return "out_of_scope", f"The {ctx.actor.role} view cannot read a flow's rollout."
    if bad := _bad_subject(i):
        return bad
    fid = _norm(i)["flow_id"]
    f = flows.repo.get_flow(ctx.session, int(fid))
    if f is None:
        return "not_found", f"No decision flow {fid}."
    return None if _org_ok(ctx, f.org_unit_id) else _boundary(f.org_unit_id)


@guard("rollout.get")
def get_guard(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | None:
    return _read_guard(i, ctx, ("manageFlows", _APPROVE))


@guard("rollout.report")
def report_guard(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | None:
    return _read_guard(i, ctx, ("manageFlows", _APPROVE, "runReplay"))


@implement("rollout.get")
def get(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    f = cast(FlowRow, flows.repo.get_flow(ctx.session, int(_norm(i)["flow_id"])))
    s = ctx.session
    if _kind(i) == "table":
        tstage = _table_stage(s, f)
        run = repo.done_replay_any(s, f.id)
        return {
            "flow_id": f.id, "subject_kind": "table", "name": f.name, "stage": tstage, "status": f.status,
            "rollouts": [_view(r) for r in repo.active_rollout(s, f.id, "table")], "counts": repo.arm_counts(s, f.id, "table"),
            "replay_run_id": run, "replay_done": run is not None, "can": _table_can(ctx, f, tstage),
            "markets": sorted(spec.markets) if (spec := market_spec(repo.TABLE_PACK)) else [],
        }  # fmt: skip
    stage = current_stage(s, f)
    eff = "shadow" if stage == "rolled_back" else stage  # a rolled-back flow may start another canary
    run = repo.done_replay(s, f)
    maker_blocked = ctx.actor.id in makers(ctx, f)
    return {
        "flow_id": f.id, "name": f.name, "stage": stage, "status": f.status, "base_ver": f.ver, "candidate_ver": f.dver,
        "rollouts": [_view(r) for r in repo.rollouts_of(s, f.id, ("canary", "paused"))], "counts": repo.arm_counts(s, f.id),
        "replay_run_id": run, "replay_done": run is not None,
        "can": {  # what this person may do now, and the reason when not (the panel shows them)
            "startCanary": None if eff == "shadow" and run is not None and not maker_blocked else (
                MAKER if maker_blocked and eff == "shadow" else _replay_needed(ctx, f) if eff == "shadow"
                else "Approve the flow into shadow first." if eff in (None, "replay") else "A canary is already running or ended."
            ),
            "widen": None if stage in ("canary", "paused") and not maker_blocked else (MAKER if maker_blocked else "No canary is running."),
            "pause": None if stage == "canary" else "No canary is running.",
            "full": None if stage == "canary" and not maker_blocked else (MAKER if maker_blocked and stage == "canary" else "Start a canary first."),
            "rollback": None if stage in ("canary", "paused") else "No canary is running.",
        },
    }  # fmt: skip


# ---------------------------------------------------------------- report (P9-7.4)
def build_report(s: Any, f: FlowRow) -> dict[str, Any]:
    """Both arms' figures, the band of the difference, the sample the comparison needs, the stop rules and any breach: all
    computed by code (di.services.modeler.canary_stats) from the cases of the flow's running or paused canary."""
    rows = repo.arm_rows(s, f.id)
    stored = repo.stop_rules_of(s, f.id)
    rules = stats.rules_of(stored)
    canary, control = stats.arm_stats(rows["canary"]), stats.arm_stats(rows["control"])
    c_nets = [r["net"] for r in rows["canary"] if r["net"] is not None]
    k_nets = [r["net"] for r in rows["control"] if r["net"] is not None]
    needed = stats.n_needed(k_nets)
    stage = current_stage(s, f)
    return {
        "flow_id": f.id, "name": f.name, "stage": stage, "canary": canary, "control": control,
        "band": stats.diff_band(c_nets, k_nets), "n_needed": needed, "rules": rules,
        "note": stats.sample_note(canary, control, needed, rules), "breach": stats.stop_check(canary, control, rules),
        "paused": stored.get("paused") if stage == "paused" else None,
    }  # fmt: skip


LABELS = {"canary": "Canary", "control": "Standard quote"}


def build_table_report(s: Any, f: FlowRow) -> dict[str, Any]:
    """The table canary's report (P9-7.7): the arms' figures as for a flow canary, with the service-desk measures of each (option
    mix, margin per ticket, upgrade take-up, days to the quoted option) and the arms named as the panel shows them: the pilot
    market's tables against the standard quote. Computed by code from the tickets' cases; no automatic pause for tables."""
    rows = repo.arm_rows(s, f.id, "table")
    stored = repo.stop_rules_of(s, f.id, "table")
    rules = stats.rules_of(stored)
    arms = {k: stats.arm_stats(v) | {"sd": stats.sd_measures([_ticket(r["sd"]) for r in v])} for k, v in rows.items()}
    nets = {k: [r["net"] for r in v if r["net"] is not None] for k, v in rows.items()}
    needed = stats.n_needed(nets["control"])
    stage = _table_stage(s, f)
    return {
        "flow_id": f.id, "subject_kind": "table", "name": f.name, "stage": stage, "canary": arms["canary"],
        "control": arms["control"], "labels": LABELS, "band": stats.diff_band(nets["canary"], nets["control"]),
        "n_needed": needed, "rules": rules, "note": stats.sample_note(arms["canary"], arms["control"], needed, rules),
        "breach": None, "paused": stored.get("paused") if stage == "paused" else None,
        "regions": [{"region": r.region, "share": r.share, "stage": r.stage} for r in repo.rollouts_of(s, f.id, kind="table")],
    }  # fmt: skip


def _ticket(sd: Any) -> dict[str, Any]:
    """A ticket's lines as `canary_stats.sd_measures` reads them: the best option of each line with its margin, take-up, days."""
    out: list[dict[str, Any]] = []
    for ln in (sd or {}).get("lines") or []:
        best = ln.get("best")
        opt = next((o for o in ln.get("options") or [] if o.get("k") == best), None) if best else None
        out.append({"best": best if opt else None, "margin": (opt or {}).get("expected_margin"),
                    "take_up": (opt or {}).get("take_up"), "days": (opt or {}).get("days")})  # fmt: skip
    return {"lines": out}


@implement("rollout.report")
def report(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    f = cast(FlowRow, flows.repo.get_flow(ctx.session, int(_norm(i)["flow_id"])))
    return build_table_report(ctx.session, f) if _kind(i) == "table" else build_report(ctx.session, f)


# ---------------------------------------------------------------- the automatic pause (P9-7.4)
WATCH_JOB = "rollout.watch"
PAUSE_TYPE = "canary_paused"  # work item type, suffixed with the flow id so one flow's items close together


@guard("rollout.autoPause")
def auto_pause_guard(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | None:
    ro = repo.get(ctx.session, int(i["rollout_id"]))
    if ro is None or ro.subject_kind != "flow":
        return "not_found", f"No rollout {i['rollout_id']}."
    return None if ro.stage == "canary" else ("conflict", f"Rollout {ro.id} is not running a canary.")


@implement("rollout.autoPause", emits=["rollout.paused"])
def auto_pause(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    ro = cast(Rollout, repo.get(ctx.session, int(i["rollout_id"])))
    f = cast(FlowRow, flow_repo.get_flow(ctx.session, int(ro.subject_id), for_update=True))
    reason = str(i["reason"])
    repo.set_stage(ctx.session, f.id, "paused", ("canary",), "system", ctx.now,
                   {"paused": {"reason": reason, "by": "system", "automatic": True, "at": ctx.now.isoformat()}})  # fmt: skip
    for role in policy.EXTRA_PERMS[_APPROVE]:  # I-20: a My work task for the people who may resume or roll back
        process.open_item(
            ctx.session, kind="step", case_id=None, org_unit_id=f.org_unit_id, type=f"{PAUSE_TYPE}:{f.id}",
            title=f"Canary of {f.name} paused automatically", cause=reason,
            action="Resume the canary (Modeler, Rollout) or roll it back", owner_role=role, due_hours=None, by="system",
        )  # fmt: skip
    return {"flow_id": f.id, "rollout_id": ro.id, "stage": "paused", "reason": reason, "automatic": True,
            "log": f"Paused the canary of {f.name} automatically: {reason}"}  # fmt: skip


def _close_pause_items(ctx: CallContext, flow_id: int, outcome: str) -> None:
    """A resumed, published or rolled-back canary no longer waits on the My work tasks its automatic pause opened."""
    ids = (
        ctx.session.execute(
            text("SELECT id FROM work_item WHERE type = :t AND status = 'open'"), {"t": f"{PAUSE_TYPE}:{flow_id}"}
        )
        .scalars()
        .all()
    )
    for n in ids:
        process.close_item(ctx.session, int(n), outcome, ctx.actor.id)


# ---------------------------------------------------------------- the watch
@after("decision.submit")
@after("decision.override")
def _watch_after_decision(i: dict[str, Any], out: dict[str, Any], ctx: CallContext) -> None:  # noqa: ARG001 - hooks take (input, output, ctx)
    """A decision on a case of a running canary queues one check of its stop rules (deduped per rollout)."""
    rid = repo.canary_of_case(ctx.session, str(i["case_id"]))
    if rid is not None:
        jobs.enqueue(ctx.session, WATCH_JOB, {"rollout_id": rid}, priority=150, dedupe_key=f"{WATCH_JOB}:{rid}")


def watch(s: Any, rollout_id: int) -> str | None:
    """The worker's check: when the canary's stop rules are breached, pause it as SYSTEM and answer the reason, else None. The
    caller commits. Never widens, adds a region or goes full."""
    ro = repo.get(s, rollout_id)
    if ro is None or ro.stage != "canary":
        return None
    f = flow_repo.get_flow(s, int(ro.subject_id))
    breach = build_report(s, f)["breach"] if f is not None else None
    if breach is None:
        return None
    done = invoke("rollout.autoPause", {"rollout_id": ro.id, "reason": breach}, CallContext(actor=SYSTEM, session=s))
    return breach if done.get("ok") else None
