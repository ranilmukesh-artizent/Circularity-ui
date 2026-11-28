# ruff: noqa: E501 - long lines in the docstring, the SQL and the action texts
"""Standing policy actions (plan 9, P9-2.5; registry entry I-11; story X-05): a person-owned approval policy below thresholds, with its own
maker-checker, and the hook that lets it approve a submitted decision.

    standingPolicy.save     act     {pack, org_unit_id, name, rules, owner, id?}   a draft (checked against the pack, the owner's
                                                        approval limit and the flow's confidence); an agent's save is held for a person
    standingPolicy.submit   act     {id}                draft -> review
    standingPolicy.approve  commit  {id}                review -> active, a new version (not by anyone who saved or submitted it)
    standingPolicy.retire   commit  {id, reason}        out of force (a draft or review policy is withdrawn)
    standingPolicy.list     read    {pack, org_unit_id} the org's policies, and the one in force there (own or inherited)

`standingPolicy.approve` and `.retire` are in `FORBIDDEN_ACTIONS`, `.save` in `HELD_FOR_PERSON`: no agent approves a policy, and the policy
itself approves, never an agent. The org scope is the policy's org unit, checked as the flow actions check it.

The hook `@after("decision.submit")` asks `decision_covered` whether the active policy of the case's pack and owner covers the submitted
decision; if so it invokes `decision.approveByPolicy` (di.services.actions.decisions) as SYSTEM in the same transaction. With no active
policy nothing happens, so the demo, RT-1048 and the golden cases are unchanged. `decision_covered` reuses the hold policy
(di.services.actions.hold.evaluate_hold) so a decision is judged the same way for a policy, a simulation and a back-test.

Needs review by Kinective's Legal team before a customer relies on it.
"""

import json
from decimal import Decimal
from typing import Any

from sqlalchemy import text

from di.core import policy
from di.core.auth import load_context
from di.repositories import standing_policies as repo
from di.repositories.live_rules import live_pack
from di.repositories.orgs import units
from di.repositories.packs import active_pack
from di.repositories.standing_policies import PolicyRow
from di.services.actions import hold
from di.services.actions.modeler import _boundary, _org_ok
from di.services.actions.pipeline import SYSTEM, CallContext, after, invoke
from di.services.actions.registry import ACTIONS, ActionDef, ActionError, Risk, guard, implement
from di.services.modeler.pack import Pack, pack_keys
from di.services.policy_standing import (
    StandingRules,
    covers,
    decide_threshold,
    pack_value_limit,
    parse_rules,
    rules_json,
    rules_problem,
)

_MANAGE, _APPROVE = "manageStandingPolicy", "approve.standingPolicy"
_STR = {"req": True, "t": "string"}
_ID = {"id": _STR}
ABOVE = "Above the policy's threshold: a person approves this decision."
_MAKES = ("standingPolicy.save", "standingPolicy.submit")


def _declare(
    action_id: str, title: str, verb: str, desc: str, risk: Risk, inp: dict[str, dict[str, Any]], perm: str | None
) -> None:
    ACTIONS.setdefault(
        action_id,
        ActionDef(id=action_id, title=title, desc=desc, risk=risk, perm=perm, scope="none", input=inp, verb=verb),
    )


_declare("standingPolicy.save", "Save a standing policy", "draft standing policies",
         "Draft a policy that approves decisions below set limits, owned by a named person.", "act",
         {"pack": _STR, "org_unit_id": _STR, "name": _STR, "rules": {"req": True, "t": "object"}, "owner": _STR, "id": {"t": "string"}},
         _MANAGE)  # fmt: skip
_declare("standingPolicy.submit", "Submit a standing policy", "submit standing policies",
         "Send a draft standing policy to a different person for approval.", "act", _ID, _MANAGE)  # fmt: skip
_declare("standingPolicy.approve", "Approve a standing policy", "approve standing policies",
         "Approve a submitted standing policy; decisions under its limits are approved by it from then on.", "commit", _ID,
         _APPROVE)  # fmt: skip
_declare("standingPolicy.retire", "Retire a standing policy", "retire standing policies",
         "Take a standing policy out of force, with a reason.", "commit",
         {**_ID, "reason": {"req": True, "t": "string", "min": 15, "minText": "Add a reason of at least 15 characters."}},
         _APPROVE)  # fmt: skip
_declare("standingPolicy.list", "List standing policies", "see standing policies",
         "The standing policies of a pack at an org unit, and the one in force there.", "read",
         {"pack": _STR, "org_unit_id": _STR}, None)  # fmt: skip


# ---------------------------------------------------------------- helpers
def _label(row: PolicyRow) -> str:
    return f"{row.id} v{row.ver}"


def _reach(pack: str, org: str, ctx: CallContext) -> tuple[str, str] | None:
    """The refusal for an unknown pack or org unit, or an org outside the actor's units."""
    if pack not in pack_keys():
        return "not_found", f"No pack {pack}."
    if org not in units(ctx.session):
        return "not_found", f"No org unit {org}."
    return None if _org_ok(ctx, org) else _boundary(org)


def _own(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | PolicyRow:
    """The policy named by `id`, or the refusal: unknown, or outside the actor's orgs."""
    row = repo.get(ctx.session, i["id"])
    if row is None:
        return "not_found", f"No standing policy {i['id']}."
    return _reach(row.pack, row.org_unit_id, ctx) or row


def _agent_refusal(ctx: CallContext) -> tuple[str, str] | None:
    return ("approval_required", "Standing policies are approved or retired only by a person.") if ctx.preparer else None


def owner_limit(ctx: CallContext, owner: str) -> Decimal | None:
    """The owner's approval limit in dollars (infinite: no limit), or None when there is no such account."""
    pctx = ctx.actor.ctx if ctx.actor.account else load_context(ctx.session)
    acct = policy.account(owner, pctx)
    return None if acct is None else Decimal(str(policy.limit_for(acct, pctx)))


def _problem(ctx: CallContext, pack_key: str, org: str, rules: StandingRules, owner: str) -> str | None:
    limit = owner_limit(ctx, owner)
    if limit is None:
        return f'No account "{owner}": the owner is a person who can approve.'
    return rules_problem(rules, active_pack(ctx.session, pack_key, org), limit)


def makers(ctx: CallContext, row: PolicyRow) -> set[str]:
    """Everyone who saved or submitted the policy (the journal, as `flow.approve` reads it, audit F3b), and its recorded maker."""
    rows = ctx.session.execute(
        text("SELECT actor FROM action_journal WHERE NOT undone AND action = ANY(:acts) AND input->>'id' = :i"),
        {"acts": list(_MAKES), "i": row.id},
    )
    return {r.actor for r in rows} | {row.maker}


def _view(r: PolicyRow) -> dict[str, Any]:
    return {
        "id": r.id, "pack": r.pack, "org_unit_id": r.org_unit_id, "name": r.name, "ver": r.ver, "status": r.status,
        "rules": r.rules, "owner": r.owner, "maker": r.maker, "checker": r.checker,
        "approved_at": r.approved_at.isoformat() if r.approved_at else None,
    }  # fmt: skip


# ---------------------------------------------------------------- save
@guard("standingPolicy.save")
def save_guard(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | None:
    if bad := _reach(i["pack"], i["org_unit_id"], ctx):
        return bad
    if not i["name"].strip():
        return "validation_error", 'Missing "name".'
    rules = parse_rules(i["rules"])
    if isinstance(rules, str):
        return "validation_error", rules
    if problem := _problem(ctx, i["pack"], i["org_unit_id"], rules, i["owner"]):
        return "validation_error", problem
    if i.get("id"):
        row = repo.get(ctx.session, i["id"])
        if row is None:
            return "not_found", f"No standing policy {i['id']}."
        if (row.pack, row.org_unit_id) != (i["pack"], i["org_unit_id"]):
            return "conflict", f"{row.id} belongs to {row.pack} at {row.org_unit_id}."
        if row.status not in ("draft", "review"):
            return "conflict", f"{row.id} is {row.status}: retire it and draft a new policy to change the limits."
    return None


def _next_id(ctx: CallContext) -> str:
    ctx.session.execute(text("SELECT pg_advisory_xact_lock(hashtext('standing_policy.id'))"))
    n = ctx.session.execute(
        text("SELECT coalesce(max(CAST(substring(id FROM 4) AS integer)), 0) + 1 FROM standing_policy WHERE id ~ '^SP-[0-9]+$'")
    ).scalar_one()
    return f"SP-{n}"


@implement("standingPolicy.save")
def save(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    rules = parse_rules(i["rules"])
    if isinstance(rules, str):  # not reached: the guard refused it
        raise ActionError("validation_error", rules)
    doc = json.dumps(rules_json(rules))
    if i.get("id"):
        row = repo.get(ctx.session, i["id"], for_update=True)
        if row is None or row.status not in ("draft", "review"):  # changed between the guard and this lock
            raise ActionError("conflict", f"{i['id']} can no longer be changed.")
        pid = row.id
        ctx.session.execute(
            text(
                "UPDATE standing_policy SET name = :n, rules = CAST(:r AS jsonb), owner = :o, status = 'draft', maker = :m, "
                "checker = NULL, updated_at = :now WHERE id = :i"
            ),
            {"n": i["name"].strip(), "r": doc, "o": i["owner"], "m": ctx.actor.id, "now": ctx.now, "i": pid},
        )
    else:
        pid = _next_id(ctx)
        ctx.session.execute(
            text(
                "INSERT INTO standing_policy (id, pack, org_unit_id, name, ver, status, rules, owner, maker, created_at, updated_at) "
                "VALUES (:i, :p, :u, :n, 0, 'draft', CAST(:r AS jsonb), :o, :m, :now, :now)"
            ),
            {
                "i": pid,
                "p": i["pack"],
                "u": i["org_unit_id"],
                "n": i["name"].strip(),
                "r": doc,
                "o": i["owner"],
                "m": ctx.actor.id,
                "now": ctx.now,
            },
        )
    return {"id": pid, "status": "draft", "log": f"Saved the draft of standing policy {pid}"}


# ---------------------------------------------------------------- submit, approve, retire
def _status(row: PolicyRow, want: tuple[str, ...], msg: str) -> tuple[str, str] | None:
    return None if row.status in want else ("conflict", msg)


@guard("standingPolicy.submit")
def submit_guard(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | None:
    row = _own(i, ctx)
    if isinstance(row, tuple):
        return row
    if bad := _status(row, ("draft",), f"{row.id} has no draft to submit."):
        return bad
    rules = parse_rules(row.rules)
    if isinstance(rules, str):
        return "validation_error", rules
    problem = _problem(ctx, row.pack, row.org_unit_id, rules, row.owner)
    return ("validation_error", problem) if problem else None


@implement("standingPolicy.submit")
def submit(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    ctx.session.execute(
        text("UPDATE standing_policy SET status = 'review', updated_at = :now WHERE id = :i"), {"now": ctx.now, "i": i["id"]}
    )
    return {"id": i["id"], "status": "review", "log": f"Submitted standing policy {i['id']} for approval"}


@guard("standingPolicy.approve")
def approve_guard(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | None:
    row = _own(i, ctx)
    if isinstance(row, tuple):
        return row
    if bad := _agent_refusal(ctx):
        return bad
    if bad := _status(row, ("review",), f"{row.id} is not waiting for approval."):
        return bad
    if ctx.actor.id in makers(ctx, row):
        return "conflict", "Maker-checker: you drafted this policy, so another person approves it."
    rules = parse_rules(row.rules)
    if isinstance(rules, str):
        return "validation_error", rules
    if problem := _problem(ctx, row.pack, row.org_unit_id, rules, row.owner):
        return "validation_error", problem
    other = next((p for p in repo.listed(ctx.session, row.pack, row.org_unit_id) if p.status == "active"), None)
    return ("conflict", f"{other.id} is in force for {row.pack} at {row.org_unit_id}: retire it first.") if other else None


@implement("standingPolicy.approve")
def approve(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    row = repo.get(ctx.session, i["id"], for_update=True)
    if row is None or row.status != "review":  # returned or approved by someone else between the guard and this lock
        raise ActionError("conflict", f"{i['id']} is not waiting for approval.")
    ver = row.ver + 1
    ctx.session.execute(
        text(
            "UPDATE standing_policy SET status = 'active', ver = :v, checker = :c, approved_at = :now, updated_at = :now WHERE id = :i"
        ),
        {"v": ver, "c": ctx.actor.id, "now": ctx.now, "i": row.id},
    )
    ctx.session.execute(
        text(
            "INSERT INTO standing_policy_version (policy_id, ver, rules, owner, approved_by, approved_at) "
            "VALUES (:i, :v, CAST(:r AS jsonb), :o, :c, :now)"
        ),
        {"i": row.id, "v": ver, "r": json.dumps(row.rules), "o": row.owner, "c": ctx.actor.id, "now": ctx.now},
    )
    return {
        "id": row.id,
        "status": "active",
        "ver": ver,
        "log": f"Approved standing policy {row.id} (v{ver}); it applies from the next decision",
    }


@guard("standingPolicy.retire")
def retire_guard(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | None:
    row = _own(i, ctx)
    if isinstance(row, tuple):
        return row
    if bad := _agent_refusal(ctx):
        return bad
    return _status(row, ("draft", "review", "active"), f"{row.id} is already retired.")


@implement("standingPolicy.retire")
def retire(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    ctx.session.execute(
        text("UPDATE standing_policy SET status = 'retired', updated_at = :now WHERE id = :i"), {"now": ctx.now, "i": i["id"]}
    )
    return {"id": i["id"], "status": "retired", "reason": i["reason"], "log": f"Retired standing policy {i['id']}"}


# ---------------------------------------------------------------- list
def _can(ctx: CallContext, perm: str) -> bool:
    return policy.can(ctx.actor.account, perm, ctx.actor.ctx)


@guard("standingPolicy.list")
def list_guard(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | None:
    if not (_can(ctx, _MANAGE) or _can(ctx, _APPROVE)):
        return "out_of_scope", f"The {ctx.actor.role} view cannot see standing policies."
    return _reach(i["pack"], i["org_unit_id"], ctx)


@implement("standingPolicy.list")
def list_policies(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    here = repo.listed(ctx.session, i["pack"], i["org_unit_id"])
    eff = repo.effective(ctx.session, i["pack"], i["org_unit_id"])
    pack = active_pack(ctx.session, i["pack"], i["org_unit_id"])
    return {
        "pack": i["pack"],
        "org_unit_id": i["org_unit_id"],
        "policies": [_view(r) for r in here],
        "in_force": _view(eff) if eff else None,
        "pack_limit": None if pack_value_limit(pack) is None else float(pack_value_limit(pack) or 0),
        "threshold": decide_threshold(pack),
        "can": {"edit": _can(ctx, _MANAGE), "approve": _can(ctx, _APPROVE)},
    }


# ---------------------------------------------------------------- the decision a policy covers
def _guardrail_holds(case: dict[str, Any]) -> list[str]:
    """The failed gates that hold the case, by their ids, and the approval holds of a service ticket's recommendation (P9-4.6)."""
    gates = [str(g["id"]) for g in case.get("gates") or [] if isinstance(g, dict) and not g.get("passed", True) and g.get("hold")]
    return gates + [str(h["id"]) for h in case.get("approvalHolds") or [] if isinstance(h, dict)]


def _fraud(case: dict[str, Any]) -> bool:
    """A fraud hold the case still carries (`case["fraud"]`, set by the fraud triage, P9-2.11; released: not a hold)."""
    f = case.get("fraud")
    return bool(f) and not (isinstance(f, dict) and f.get("status") == "released")


def _exception_on_choice(ctx: CallContext, case: dict[str, Any], route: str) -> bool:
    """Does an open exception of the case concern its chosen `route`? Any exception does, except a pack's approval item (type
    `AP-…`, e.g. the export approval AP-TN-EXP on resale) when no failed `require_approval` gate of the case names the route
    (its channel, the id before a colon): an approval on a route that was not chosen does not hold the decision (lead decision
    28 Nov)."""
    from di.services.cases.process import APPROVAL_PREFIX  # lazy: the case process imports the pipeline's callers

    types = ctx.session.execute(
        text("SELECT type FROM work_item WHERE case_id = :c AND kind = 'exception' AND status = 'open'"), {"c": case["id"]}
    ).scalars()
    names = {route, route.split(":", 1)[0]}
    on_route = any(
        not g.get("passed", True) and g.get("kind") == "require_approval" and (not g.get("routes") or names & set(g["routes"]))
        for g in case.get("gates") or []
        if isinstance(g, dict)
    )
    return any(not str(t).startswith(APPROVAL_PREFIX) or on_route for t in types)


def decision_covered(ctx: CallContext, case: dict[str, Any], row: PolicyRow) -> bool:
    """Does the policy approve the case's submitted decision (its recommended route)? The rules, the hold policy's reasons, an open
    exception, a conflict, a fraud hold, and the owner's approval limit as it is now."""
    from di.services.agents.chain import case_value  # lazy: the chain imports the stage modules that import the pipeline
    from di.services.agents.stages.valuation import confidence as valuation_confidence

    rules = parse_rules(row.rules)
    rec = case.get("recommendation")
    value = case_value(case)
    if isinstance(rules, str) or not rec or value is None:
        return False
    limit = owner_limit(ctx, row.owner)
    if limit is None or abs(value) > limit:
        return False
    pack: Pack = live_pack(ctx.session, case)
    conf = valuation_confidence({}, case)
    action = ACTIONS["decision.approveByPolicy"]
    inp = {"case_id": case["id"]}
    exception, conflict = hold._case_state(action, inp, ctx)
    exception = exception and _exception_on_choice(ctx, case, str(rec.get("id")))
    guardrails = _guardrail_holds(case)
    holds = hold.evaluate_hold(
        action=action, autonomy="limits", confidence=conf, value=value, bulk=1, open_exception=exception, conflict=conflict,
        guardrail_holds=guardrails, taint=False, policy=hold.HoldPolicy(pack_value_limit(pack), None, decide_threshold(pack)),
    )  # fmt: skip
    return covers(
        rules, value=value, confidence=conf, route=rec.get("id"), cls=case.get("cls"), market=case.get("market"),
        holds=holds, open_exception=exception, conflict=conflict, fraud_hold=_fraud(case),
    )  # fmt: skip


@after("decision.submit")
def _approve_when_covered(i: dict[str, Any], out: dict[str, Any], ctx: CallContext) -> None:  # noqa: ARG001 - hooks take (input, output, ctx)
    """The active policy of the case's pack and owner approves the decision it covers, as SYSTEM, in this transaction. A refusal
    leaves the case awaiting approval, as without a policy."""
    from di.services.cases import store

    case = store.get(ctx.session, str(i["case_id"]))
    if case is None or case.get("approval") or case["stage"] != "awaiting_approval":
        return
    row = repo.effective(ctx.session, case.get("template") or "industrial", case["owner"])
    if row is None or not decision_covered(ctx, case, row):
        return
    sys_ctx = CallContext(actor=SYSTEM, session=ctx.session, run_id=ctx.run_id, now=ctx.now)
    invoke("decision.approveByPolicy", {"case_id": case["id"], "policy_id": row.id, "ver": row.ver}, sys_ctx)


@after("decision.approveByPolicy")
def _approved_by_policy(i: dict[str, Any], out: dict[str, Any], ctx: CallContext) -> None:  # noqa: ARG001 - hooks take (input, output, ctx)
    """Wake a run waiting for the approval, as a person's approval does (di.services.agents.runtime)."""
    from di.services.agents.runtime import resume_waiting

    resume_waiting(ctx.session, str(i["case_id"]))
