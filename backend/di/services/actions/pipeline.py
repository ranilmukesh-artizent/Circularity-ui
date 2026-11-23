"""invoke(): every action goes through the same checks, in the demo's order (index.html, `function invoke`).

    1 validate the input        2 someone is signed in        3 system-only actions refuse people
    4 the permission            5 case scope: exists, tenant boundary, warehouse lock
    6 the agent gate (when an agent prepared it)              7 the action's own guard
    8 policy limits (approval limits, B12; an agent's kill switch, autonomy and run limits, MVP-11.1)
    9 idempotency                (then: an agent with autonomy "propose" holds a write for a person, MVP-11.4)
    10 run the handler           11 journal it                  12 emit events
Read actions stop after the handler: they are not journaled.
Every result is the demo's shape: {ok: true, output, key, action, seq} or {ok: false, error: {code, message}}.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from di.core import clock, policy
from di.services.actions.registry import ACTIONS, ActionDef, ActionError
from di.services.actions.scope import case_scope
from di.services.agents import limits, proposals

# HTTP status per error code (the body always carries the demo's code and message)
ERROR_STATUS = {
    "validation_error": 400,
    "out_of_scope": 403,
    "tenant_boundary": 403,
    "approval_required": 403,
    "limit_exceeded": 403,
    "not_found": 404,
    "conflict": 409,
    "duplicate": 409,
    "not_implemented": 501,
}
SECRET_WORDS = ("secret", "password", "token")


@dataclass
class Actor:
    """Who acts: a signed-in person (with their access state), or the enterprise-system adapter."""

    account: policy.Account | None
    ctx: policy.Context = field(default_factory=policy.Context)
    system: bool = False

    @property
    def id(self) -> str:
        return "system" if self.system else (self.account.id if self.account else "—")

    @property
    def role(self) -> str:
        return "System" if self.system else (self.account.role if self.account else "—")

    @property
    def person(self) -> policy.Account:
        """The signed-in account, for code only people reach (invoke() refuses a caller who is not signed in)."""
        if self.account is None:
            raise ActionError("out_of_scope", "Sign in first.")
        return self.account


SYSTEM = Actor(account=None, system=True)


@dataclass
class CallContext:
    actor: Actor
    session: Session
    preparer: str | None = None  # the agent that prepared this call
    confirmed: bool = False  # a person pressed the final button on the agent's plan
    run_id: str | None = None
    idem_key: str | None = None  # an Idempotency-Key from the client, for actions without their own key
    now: datetime = field(default_factory=clock.now)  # the workspace clock (di/core/clock.py)


def fail(code: str, message: str, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    """A refusal in the demo's shape; `extra` adds fields the demo puts beside code and message (e.g. escalate)."""
    return {"ok": False, "error": {"code": code, "message": message, **(extra or {})}}


def _type_ok(value: Any, t: str | None) -> bool:
    if t is None or value is None:
        return True
    if t == "array":
        return isinstance(value, list)
    if t == "object":
        return isinstance(value, dict)
    if t == "number":
        return isinstance(value, int | float) and not isinstance(value, bool)
    if t == "boolean":
        return isinstance(value, bool)
    if t == "string":
        return isinstance(value, str)
    return True


def validate(a: ActionDef, i: dict[str, Any]) -> str:
    """The demo's afValidate: required, type, minimum length. Returns the first problem, or ''."""
    for k, v in a.input.items():
        x, t = i.get(k), v.get("t")
        if v.get("req") and (x is None or x == ""):
            return f'Missing "{k}".'
        if x is not None and not _type_ok(x, t):
            kind = "a list" if t == "array" else "an object" if t == "object" else f"a {t}"
            return f'"{k}" must be {kind}.'
        if v.get("min") is not None and isinstance(x, str) and len(x.strip()) < v["min"]:
            return v.get("minText") or f'"{k}" needs at least {v["min"]} characters.'
    return ""


def _agent_gate(a: ActionDef, ctx: CallContext) -> tuple[str, str] | None:
    """The agent acts as the signed-in person and never commits on its own (the demo's afAgentGate)."""
    if a.risk == "commit" and (not ctx.confirmed or a.id.startswith("decision.")):
        if a.id.startswith("decision."):
            return "approval_required", "Decisions are approved, overridden or declined only in the approval card, by a person."
        return "approval_required", f"A person must press the final button for {a.title.lower()}. The agent can only prepare it."
    if a.risk == "system":
        return "out_of_scope", "Only an enterprise system acknowledges instructions."
    return None


def _clean(i: dict[str, Any]) -> dict[str, Any]:
    """Inputs are stored; anything that looks like a secret is never kept."""

    def walk(x: Any) -> Any:
        if isinstance(x, dict):
            return {k: walk(v) for k, v in x.items() if not any(w in k.lower() for w in SECRET_WORDS)}
        if isinstance(x, list):
            return [walk(v) for v in x]
        return x

    cleaned: dict[str, Any] = walk(i)
    return cleaned


def _output_ref(o: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(o, dict):
        return None
    ref = {k: o[k] for k in ("id", "ref", "case_id", "source_id") if o.get(k) is not None}
    return ref or None


def invoke(action_id: str, i: dict[str, Any] | None, ctx: CallContext) -> dict[str, Any]:
    a = ACTIONS.get(action_id)
    i = i or {}
    if a is None:
        return fail("not_found", f"No action {action_id}.")
    actor = ctx.actor
    # 1 validate
    if bad := validate(a, i):
        return fail("validation_error", bad)
    # 2 signed in
    if not actor.system and actor.account is None:
        return fail("out_of_scope", "Sign in first.")
    # 3 system-only actions
    if a.risk == "system" and not actor.system:
        return fail("out_of_scope", "Only an enterprise system acknowledges instructions.")
    # 4 permission
    if a.permission and not actor.system and not policy.can(actor.account, a.permission, actor.ctx):
        return fail("out_of_scope", f"The {actor.role} view cannot {a.verb or a.title.lower()}.")
    # 5 case scope
    case_id = i.get("case_id") if a.scope == "case" else None
    if a.scope == "case" and not actor.system:
        where = case_scope(str(i.get("case_id", "")))
        if where is None:
            return fail("not_found", f"No live case {i.get('case_id', '')}.")
        owner, location = where
        acct = actor.account
        if acct is None:  # not reached: step 2 refused a person who is not signed in
            return fail("out_of_scope", "Sign in first.")
        if not policy.tenant_ok(acct, owner, actor.ctx) or not policy.location_ok(acct, location):
            msg = (
                f"{case_id} is at {location}, outside your warehouse."
                if policy.policy(acct).get("warehouseScoped")
                else f"{case_id} belongs to {owner}, a tenant you cannot see. Request tenant access first."
            )
            return fail("tenant_boundary", msg)
    # 6 agent gate
    if ctx.preparer and (g := _agent_gate(a, ctx)):
        return fail(*g)
    # 7 the action's own guard
    if a.guard and (refusal := a.guard(i, ctx)):
        return fail(*refusal)
    # 8 policy limits: approval limits are the decision handlers' guards (B12); an agent's kill switch, autonomy and
    # run limits are checked here (plan 8 MVP-11.1, di.services.agents.limits)
    if ctx.preparer and (refusal := limits.check(a, i, ctx)):
        return fail(*refusal)
    # 9 idempotency
    key = f"{a.id}:{a.idem(i, ctx)}" if a.idem else (f"{a.id}:{ctx.idem_key}" if ctx.idem_key and a.changes_state else None)
    if key and a.changes_state:
        seen = ctx.session.execute(text("SELECT seq FROM action_journal WHERE idem_key = :k AND NOT undone"), {"k": key}).first()
        if seen:
            return fail("duplicate", f"{a.dup_text or 'Already done'}. Nothing was created twice.")
    # 9b an agent registered with autonomy "propose" does not run a write: it holds for a person (MVP-11.4)
    if ctx.preparer and a.changes_state and not ctx.confirmed and proposals.holds(ctx.session, ctx.preparer):
        pid = proposals.hold(ctx, a.id, _clean(i), case_id)
        return {"ok": True, "output": {"held": pid}, "key": None, "action": a.id}
    # 10 run
    if a.handler is None:
        return fail("not_implemented", f"{a.title} is not available on the server yet.")
    try:
        with ctx.session.begin_nested():
            out = a.handler(i, ctx) or {}
            if not a.changes_state or not a.journaled:
                return {"ok": True, "output": out, "key": None, "action": a.id}
            # 11 journal
            seq = ctx.session.execute(
                text(
                    "INSERT INTO action_journal "
                    "(action, input, actor, role, preparer, run_id, case_id, idem_key, output_ref, at) "
                    "VALUES (:a, CAST(:i AS jsonb), :actor, :role, :prep, :run, :case, :key, CAST(:ref AS jsonb), :at) "
                    "RETURNING seq"
                ),
                {
                    "a": a.id,
                    "i": _json(_clean(i)),
                    "actor": actor.id,
                    "role": actor.role,
                    "prep": ctx.preparer,
                    "run": ctx.run_id,
                    "case": case_id,
                    "key": key,
                    "ref": _json(_output_ref(out)),
                    "at": ctx.now,
                },
            ).scalar_one()
            # 12 events: one for the action, plus any the action declares
            for t in [f"action.{a.id}", *a.emits]:
                ctx.session.execute(
                    text(
                        "INSERT INTO domain_event (type, seq, case_id, payload, at) VALUES (:t, :s, :c, CAST(:p AS jsonb), :at)"
                    ),
                    {
                        "t": t,
                        "s": seq,
                        "c": case_id,
                        "p": _json({"action": a.id, "input": _clean(i), "output": out, "by": actor.id}),
                        "at": ctx.now,
                    },
                )
    except ActionError as e:
        return fail(e.code, e.message, e.extra)
    except IntegrityError:  # a concurrent call won the idempotency race
        return fail("duplicate", f"{a.dup_text or 'Already done'}. Nothing was created twice.")
    return {"ok": True, "output": out, "key": key, "action": a.id, "seq": seq}


def _json(v: Any) -> str:
    import json

    return json.dumps(v, default=str)
