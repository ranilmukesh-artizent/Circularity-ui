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

Which version decides a case is `di.repositories.rollouts.version_for`, used by di.repositories.live_rules.flow_version; a stored
assignment is kept through approval, execution and close. Starting, widening and going full are refused for anyone who made the
flow's changes (maker-checker, the same journal rule as flow.approve). Every write is journaled. No agent may run any of them
(`rollout.` in di.services.agents.forbidden); `rollout.get` is a read.
"""

import hashlib
from typing import Any, cast

from di.core import policy
from di.repositories import flows as flow_repo
from di.repositories import rollouts as repo
from di.repositories.flows import FlowRow
from di.services.actions import modeler as flows
from di.services.actions.modeler import _boundary, _org_ok, _reach, makers
from di.services.actions.pipeline import CallContext
from di.services.actions.registry import ACTIONS, ActionDef, ActionError, Risk, guard, implement
from di.services.modeler.rollout import Rollout, Stage, can_move

_APPROVE = "approve.flows"
MAKER = "Maker-checker: you made these changes, so you cannot widen their rollout."
NEEDS_REPLAY = "Run a replay of v{v} before a canary (Modeler, Replay)."
_NEED_REASON = {"req": True, "t": "string", "min": 15, "minText": "Add a reason of at least 15 characters."}
_ID = {"flow_id": {"req": True, "t": "number"}}


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


def _gate(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | FlowRow:
    """The flow, or the refusal: unknown, outside the actor's orgs, or prepared by an agent."""
    f = _reach(i, ctx)
    if isinstance(f, tuple):
        return f
    return ("approval_required", "A flow is published, widened or rolled back only by a person.") if ctx.preparer else f


def _maker(ctx: CallContext, f: FlowRow) -> tuple[str, str] | None:
    return ("conflict", MAKER) if ctx.actor.id in makers(ctx, f) else None


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
    stage = current_stage(ctx.session, f)
    if not can_move("shadow" if stage == "rolled_back" else stage, "canary"):
        if repo.active_rollout(ctx.session, f.id):
            return "conflict", f"A canary of {f.name} is already running; widen it instead."
        return "conflict", f"{f.name} must be approved into shadow before a canary."
    if bad := _maker(ctx, f):
        return bad
    if repo.done_replay(ctx.session, f.id, f.dver) is None:
        return "conflict", NEEDS_REPLAY.format(v=f.dver)
    return None


@implement("rollout.startCanary")
def start(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    f = _flow_of(ctx, i)
    key, region, share = (i.get("region_key") or "market").strip(), str(i["region"]).strip(), int(i["share"])
    salt = hashlib.sha256(f"{f.id}:{f.dver}:{ctx.now.isoformat()}".encode()).hexdigest()[:16]
    run = repo.done_replay(ctx.session, f.id, f.dver)
    rid = repo.insert(ctx.session, f.id, candidate=f.dver, base=f.ver, region_key=key, region=region, share=share,
                      salt=salt, by=ctx.actor.id, run_id=run)  # fmt: skip
    return {"flow_id": f.id, "rollout_id": rid, "stage": "canary", "region_key": key, "region": region, "share": share,
            "candidate_ver": f.dver, "base_ver": f.ver, "replay_run_id": run,
            "log": f"Canary of {f.name} v{f.dver}: {key} {region} at {share} % of volume (base v{f.ver})"}  # fmt: skip


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
    rows = repo.active_rollout(ctx.session, f.id)
    if not rows:
        return "conflict", f"No canary is running for {f.name}."
    if bad := _maker(ctx, f):
        return bad
    region, share = str(i.get("region") or "").strip() or None, i.get("share")
    target = [r for r in rows if region is None or r.region == region]
    if share is not None and (low := next((r for r in target if int(share) < r.share), None)):
        return "conflict", f"The share only rises: {low.region} is at {low.share} %."
    return None


@implement("rollout.widen")
def widen(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    f = _flow_of(ctx, i)
    rows = repo.active_rollout(ctx.session, f.id)
    region = str(i.get("region") or "").strip() or None
    share = int(i["share"]) if i.get("share") is not None else None
    target = [r for r in rows if region is None or r.region == region]
    for r in target:
        if share is not None:
            repo.set_share(ctx.session, r.id, share, ctx.actor.id, ctx.now)
    if region is not None and not target:  # a new region: a row of its own on the same candidate and salt
        first = rows[0]
        repo.insert(ctx.session, f.id, candidate=first.candidate_ver, base=first.base_ver or f.ver, region_key=first.region_key,
                    region=region, share=share if share is not None else first.share, salt=first.salt, by=ctx.actor.id,
                    run_id=None)  # fmt: skip
    if any(r.stage == "paused" for r in rows):  # widening a paused canary resumes it
        repo.set_stage(ctx.session, f.id, "canary", ("paused",), ctx.actor.id, ctx.now)
    now = repo.active_rollout(ctx.session, f.id)
    return {"flow_id": f.id, "stage": "canary", "rollouts": [_view(r) for r in now],
            "log": f"Widened the canary of {f.name}: " + ", ".join(f"{r.region} at {r.share} %" for r in now)}  # fmt: skip


# ---------------------------------------------------------------- pause, full, rollback
@guard("rollout.pause")
def pause_guard(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | None:
    f = _gate(i, ctx)
    if isinstance(f, tuple):
        return f
    return None if can_move(current_stage(ctx.session, f), "paused") else ("conflict", f"No canary is running for {f.name}.")


@implement("rollout.pause")
def pause(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    f = _flow_of(ctx, i)
    repo.set_stage(ctx.session, f.id, "paused", ("canary",), ctx.actor.id, ctx.now,
                   {"paused": {"reason": i["reason"], "by": ctx.actor.id, "at": ctx.now.isoformat()}})  # fmt: skip
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
    return {**out, "stage": "full", "flow_id": f.id, "log": f"Published {f.name} v{out['ver']} in full after its canary"}


@guard("rollout.rollback")
def rollback_guard(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | None:
    f = _gate(i, ctx)
    if isinstance(f, tuple):
        return f
    return None if repo.active_rollout(ctx.session, f.id) else ("conflict", f"No canary is running for {f.name}.")


@implement("rollout.rollback")
def rollback(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    f = _flow_of(ctx, i)
    repo.set_stage(ctx.session, f.id, "rolled_back", ("canary", "paused"), ctx.actor.id, ctx.now,
                   {"rolled_back": {"reason": i["reason"], "by": ctx.actor.id, "at": ctx.now.isoformat()}})  # fmt: skip
    cleared = repo.clear_undecided(ctx.session, f.id)
    return {"flow_id": f.id, "stage": "rolled_back", "cleared": cleared, "reason": i["reason"],
            "log": f"Rolled back the canary of {f.name}: {cleared} undecided cases use v{f.ver} again"}  # fmt: skip


# ---------------------------------------------------------------- read
@guard("rollout.get")
def get_guard(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | None:
    acct = ctx.actor.account
    if acct is None or not any(policy.can(acct, p, ctx.actor.ctx) for p in ("manageFlows", _APPROVE)):
        return "out_of_scope", f"The {ctx.actor.role} view cannot read a flow's rollout."
    f = flows.repo.get_flow(ctx.session, int(i["flow_id"]))
    if f is None:
        return "not_found", f"No decision flow {i['flow_id']}."
    return None if _org_ok(ctx, f.org_unit_id) else _boundary(f.org_unit_id)


@implement("rollout.get")
def get(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    f = cast(FlowRow, flows.repo.get_flow(ctx.session, int(i["flow_id"])))
    s = ctx.session
    stage = current_stage(s, f)
    eff = "shadow" if stage == "rolled_back" else stage  # a rolled-back flow may start another canary
    run = repo.done_replay(s, f.id, f.dver)
    maker_blocked = ctx.actor.id in makers(ctx, f)
    return {
        "flow_id": f.id, "name": f.name, "stage": stage, "status": f.status, "base_ver": f.ver, "candidate_ver": f.dver,
        "rollouts": [_view(r) for r in repo.rollouts_of(s, f.id, ("canary", "paused"))], "counts": repo.arm_counts(s, f.id),
        "replay_run_id": run, "replay_done": run is not None,
        "can": {  # what this person may do now, and the reason when not (the panel shows them)
            "startCanary": None if eff == "shadow" and run is not None and not maker_blocked else (
                MAKER if maker_blocked and eff == "shadow" else NEEDS_REPLAY.format(v=f.dver) if eff == "shadow"
                else "Approve the flow into shadow first." if eff in (None, "replay") else "A canary is already running or ended."
            ),
            "widen": None if stage in ("canary", "paused") and not maker_blocked else (MAKER if maker_blocked else "No canary is running."),
            "pause": None if stage == "canary" else "No canary is running.",
            "full": None if stage == "canary" and not maker_blocked else (MAKER if maker_blocked and stage == "canary" else "Start a canary first."),
            "rollback": None if stage in ("canary", "paused") else "No canary is running.",
        },
    }  # fmt: skip
