"""A person's side of an agent's proposal (plan 8, MVP-11.4): accept it, and the held action runs as that person, or
reject it. Declared here, beside the catalog's actions; agents never run them (di.services.agents.forbidden.FORBIDDEN_ACTIONS).

    proposal.accept  commit  {id}           the held action runs through the pipeline as the person, prepared by the
                                            agent and confirmed (so the agent gate lets a commit through, never a
                                            decision.*); its result is stored. Needs the held action's own permission.
    proposal.reject  commit  {id, reason}   the proposal is closed with the person's reason
A proposal from an agent run (run_id) wakes the run when it is decided (di.services.agents.runtime.wake).

"""

from typing import Any

from di.core import policy
from di.services.actions.pipeline import CallContext, invoke
from di.services.actions.registry import ACTIONS, ActionDef, ActionError, guard, implement
from di.services.agents import proposals, runtime

ACTIONS.setdefault(
    "proposal.accept",
    ActionDef(
        id="proposal.accept", title="Accept an agent's proposal", desc="Run an action an agent prepared, as yourself.",
        risk="commit", perm=None, scope="none", input={"id": {"req": True, "t": "number"}}, verb="accept proposals",
    ),
)  # fmt: skip
ACTIONS.setdefault(
    "proposal.reject",
    ActionDef(
        id="proposal.reject", title="Reject an agent's proposal", desc="Close an agent's proposal without running it.",
        risk="commit", perm=None, scope="none", verb="reject proposals",
        input={"id": {"req": True, "t": "number"},
               "reason": {"req": True, "t": "string", "min": 5, "minText": "Add a short reason for the agent's owner."}},
    ),
)  # fmt: skip


def _pending(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | None:
    if ctx.preparer:
        return "approval_required", "Only a person accepts or rejects an agent's proposal."
    p = proposals.get(ctx.session, int(i["id"]))
    if p is None:
        return "not_found", f"No proposal {i['id']}."
    if p["status"] != "pending":
        return "conflict", f"Proposal {p['id']} is already {p['status']}."
    a = ACTIONS.get(p["action"])
    acct = ctx.actor.person
    if a is None:
        return "not_found", f"No action {p['action']}."
    if a.permission and not policy.can(acct, a.permission, ctx.actor.ctx):
        return "out_of_scope", f"The {acct.role} view cannot {a.verb or a.title.lower()}."
    if not proposals.may_decide(p, acct, ctx.actor.ctx):  # the held case is outside the person's tenants
        return "tenant_boundary", f"{p['case_id']} belongs to a tenant you cannot see. Request tenant access first."
    return None


OWN = "Maker-checker: the agent prepared this for you, so another person accepts it. You can reject it."


@guard("proposal.accept")
def accept_guard(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | None:
    if bad := _pending(i, ctx):
        return bad
    p = proposals.get(ctx.session, int(i["id"]))
    return ("conflict", OWN) if p is not None and proposals.own(p, ctx.actor.person) else None


guard("proposal.reject")(_pending)


@implement("proposal.accept")
def accept(i: dict[str, Any], ctx: CallContext):
    p = proposals.get(ctx.session, int(i["id"]), for_update=True)
    if p is None:  # not reached: the guard refused it
        raise ActionError("not_found", f"No proposal {i['id']}.")
    run = CallContext(actor=ctx.actor, session=ctx.session, preparer=p["agent"], confirmed=True, run_id=p["run_id"], now=ctx.now)
    r = invoke(p["action"], p["input"], run)
    if not r["ok"]:
        e = r["error"]
        raise ActionError(e["code"], e["message"], {k: v for k, v in e.items() if k not in ("code", "message")} or None)
    proposals.decide(ctx.session, p["id"], "accepted", ctx.actor.id, ctx.now, {"output": r["output"], "seq": r.get("seq")})
    if p["run_id"]:  # an agent run waits for this proposal: it runs on (MVP-11.5)
        runtime.wake(ctx.session, p["run_id"])
    return {"id": p["id"], "status": "accepted", "action": p["action"], "output": r["output"]}


@implement("proposal.reject")
def reject(i: dict[str, Any], ctx: CallContext):
    p = proposals.get(ctx.session, int(i["id"]), for_update=True)
    if p is None:  # not reached: the guard refused it
        raise ActionError("not_found", f"No proposal {i['id']}.")
    proposals.decide(ctx.session, p["id"], "rejected", ctx.actor.id, ctx.now, {"reason": i["reason"].strip()})
    if p["run_id"]:  # the agent run that waits for it stops
        runtime.wake(ctx.session, p["run_id"])
    return {"id": p["id"], "status": "rejected"}
