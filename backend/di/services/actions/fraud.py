# ruff: noqa: E501 - long lines in the docstring, the SQL and the action texts
"""Fraud actions (plan 9, P9-2.11; stories X-15 and DV-02; registry entries I-1, I-10 and I-20): a returned asset whose fraud
score reaches the pack's threshold is held for a person, who releases it or rejects the return.

    fraud.hold      act     {case_id, score, signals, rule_version, threshold?}   marks the case held and opens a "Fraud and
                                                        compliance" exception for the Approver; an agent may run it (it only adds caution)
    fraud.release   commit  {case_id, reason}           approve.decisions: clears the hold and keeps who released it and why
    fraud.reject    commit  {case_id, reason}           approve.decisions: declines the return through `decision.decline`, as the person
    fraud.simulate  read    {pack, org_unit_id, threshold?, rules?}   manageFlows: the triage over the org's open cases with a
                                                        threshold or rule set, against what is in force now

`fraud.release` and `fraud.reject` are in `FORBIDDEN_ACTIONS` (di.services.agents.forbidden): no agent clears a hold or declines a
return, however the call arrives (golden rule 10). The record on the case is `case["fraud"]`: `{status, score, threshold,
signals, rule_version, held_at, by, item}` (`status` is `held`, then `released` or `rejected`, with `resolved_by`, `resolved_at`
and `reason`). A case whose `fraud.status` is `held` blocks a standing policy (di.services.actions.standing_policy) and keeps the
chain's intake stage held (di.services.agents.stages.intake). `triage_case` is what the chain runs on intake: the computed score
of `di.services.modeler.fraud.triage` with the case's repeat-return counts. The model's review of fraud is P9-2.19.

Needs review by Kinective's Legal team before a customer relies on it.
"""

from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from di.core import orgs
from di.repositories.fraud_history import repeat_counts
from di.repositories.live_rules import live_pack
from di.repositories.orgs import units
from di.repositories.packs import active_pack
from di.services.actions.modeler import _boundary, _org_ok
from di.services.actions.pipeline import CallContext, after, invoke
from di.services.actions.registry import ACTIONS, ActionDef, ActionError, guard, implement
from di.services.cases import process, store
from di.services.modeler.fraud import THRESHOLD_PARAM, FraudResult, FraudRules, repeat_windows, triage
from di.services.modeler.pack import Pack, pack_keys

TYPE = "fraud_hold"
TITLE = "Fraud and compliance: held for fraud review"
_STR = {"req": True, "t": "string"}
_WHY = {"req": True, "t": "string", "min": 10, "minText": "Add a reason of at least 10 characters."}


def _declare(
    action_id: str, title: str, verb: str, desc: str, risk: Any, inp: dict[str, dict[str, Any]], perm: str | None, scope: Any
) -> None:
    ACTIONS.setdefault(
        action_id, ActionDef(id=action_id, title=title, desc=desc, risk=risk, perm=perm, scope=scope, input=inp, verb=verb)
    )


_declare("fraud.hold", "Hold a case for fraud review", "hold cases for fraud review",
         "Hold a returned asset whose fraud score reaches the threshold, so a person releases or rejects it.", "act",
         {"case_id": _STR, "score": {"req": True, "t": "number"}, "signals": {"req": True, "t": "array"},
          "rule_version": _STR, "threshold": {"t": "number"}}, None, "case")  # fmt: skip
_declare("fraud.release", "Release a fraud hold", "release fraud holds",
         "Clear the fraud hold on a case, with a reason that stays on the record.", "commit",
         {"case_id": _STR, "reason": _WHY}, "approve.decisions", "case")  # fmt: skip
_declare("fraud.reject", "Reject a held return", "reject held returns",
         "Decline the return of a case held for fraud review, with a reason that stays on the record.", "commit",
         {"case_id": _STR, "reason": _WHY}, "approve.decisions", "case")  # fmt: skip
_declare("fraud.simulate", "Simulate fraud rules", "simulate fraud rules",
         "Run the fraud triage over an org's open cases with a threshold or rule set, and see which cases would change.", "read",
         {"pack": _STR, "org_unit_id": _STR, "threshold": {"t": "number"}, "rules": {"t": "array"}}, "manageFlows", "none")  # fmt: skip


# ---------------------------------------------------------------- the triage the chain runs
def triage_case(s: Session, case: dict[str, Any], pack: Pack) -> FraudResult:
    """The computed score of the case under the pack in force: the pure triage with the repeat-return counts it reads."""
    return triage(case, pack, repeat_counts(s, case, repeat_windows(pack)))


def active_hold(case: dict[str, Any]) -> dict[str, Any] | None:
    """The case's fraud record while it is held (not yet released or rejected)."""
    f = case.get("fraud")
    return f if isinstance(f, dict) and f.get("status") == "held" else None


def _item(s: Session, case_id: str) -> int | None:
    got = s.execute(
        text("SELECT id FROM work_item WHERE case_id = :c AND type = :t AND status = 'open' ORDER BY id DESC LIMIT 1"),
        {"c": case_id, "t": TYPE},
    ).scalar()
    return int(got) if got is not None else None


# ---------------------------------------------------------------- hold
@guard("fraud.hold")
def hold_guard(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | None:
    case = store.get(ctx.session, i["case_id"])
    if case is not None and active_hold(case):
        return "conflict", f"{i['case_id']} is already held for fraud review."
    if not all(isinstance(x, dict) for x in i["signals"]):
        return "validation_error", '"signals" is a list of signals.'
    return None


def _hold_idem(i: dict[str, Any], ctx: CallContext) -> str:  # noqa: ARG001 - the IdemKey signature
    return f"{i['case_id']}:fraud:{i['rule_version']}"


@implement("fraud.hold", idem=_hold_idem)
def hold(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    c = store.get(ctx.session, i["case_id"], for_update=True)
    if c is None:
        raise ActionError("not_found", f"No live case {i['case_id']}.")
    threshold = i.get("threshold")
    reach = f"{i['score']:g} reaches {threshold:g}" if isinstance(threshold, int | float) else f"{i['score']:g}"
    item = process.open_item(
        ctx.session, kind="exception", case_id=c["id"], org_unit_id=c["owner"], type=TYPE, title=TITLE,
        cause=f"Fraud score {reach} (rule set {i['rule_version']}); signals: "
        + (", ".join(str(s.get("id")) for s in i["signals"]) or "none"),
        action="Release or reject the return", owner_role="Approver", due_hours=process.sla_hours(ctx.session, c["id"], TYPE),
        by=ctx.actor.id,
    )  # fmt: skip
    c["fraud"] = {
        "status": "held", "score": i["score"], "threshold": threshold, "signals": i["signals"],
        "rule_version": i["rule_version"], "held_at": ctx.now.isoformat(), "by": ctx.preparer or ctx.actor.id, "item": item,
    }  # fmt: skip
    store.save(ctx.session, c)
    return {"case_id": c["id"], "item": item, "log": f"Held {c['id']} for fraud review (score {i['score']:g})"}


# ---------------------------------------------------------------- release, reject
def _held(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | None:
    case = store.get(ctx.session, i["case_id"])
    if case is None or not active_hold(case):
        return "conflict", f"{i['case_id']} is not held for fraud review."
    return None


def _close(c: dict[str, Any], status: str, i: dict[str, Any], ctx: CallContext) -> None:
    c["fraud"] |= {
        "status": status,
        "resolved_by": ctx.actor.id,
        "resolved_at": ctx.now.isoformat(),
        "reason": i["reason"].strip(),
    }
    store.save(ctx.session, c)
    if item := _item(ctx.session, c["id"]):
        process.close_item(ctx.session, item, status, ctx.actor.id)


guard("fraud.release")(_held)
guard("fraud.reject")(_held)


@implement("fraud.release")
def release(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    c = store.get(ctx.session, i["case_id"], for_update=True)
    if c is None or not active_hold(c):
        raise ActionError("conflict", f"{i['case_id']} is not held for fraud review.")
    _close(c, "released", i, ctx)
    return {"case_id": c["id"], "status": "released", "log": f"Released {c['id']} from fraud review: {i['reason'].strip()}"}


@implement("fraud.reject")
def reject(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    """The existing decline path, as the person: it moves the case to re-evaluation and sends the decision on."""
    done = invoke("decision.decline", {"case_id": i["case_id"], "reason": f"Fraud review: {i['reason'].strip()}"}, ctx)
    if not done["ok"]:
        raise ActionError(done["error"]["code"], done["error"]["message"])
    c = store.get(ctx.session, i["case_id"], for_update=True)
    if c is None or not active_hold(c):
        raise ActionError("conflict", f"{i['case_id']} is not held for fraud review.")
    _close(c, "rejected", i, ctx)
    return {"case_id": c["id"], "status": "rejected", "log": f"Rejected the return of {c['id']}: {i['reason'].strip()}"}


@after("fraud.release")
def _release_wakes_the_chain(i: dict[str, Any], out: dict[str, Any], ctx: CallContext) -> None:  # noqa: ARG001 - hooks take (input, output, ctx)
    """A run whose intake stage waits on the hold runs on (di.services.agents.runtime)."""
    from di.services.agents.runtime import resume_waiting

    resume_waiting(ctx.session, str(i["case_id"]), "fraud")


# ---------------------------------------------------------------- simulate
@guard("fraud.simulate")
def simulate_guard(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | None:
    if i["pack"] not in pack_keys():
        return "not_found", f"No pack {i['pack']}."
    if i["org_unit_id"] not in units(ctx.session):
        return "not_found", f"No org unit {i['org_unit_id']}."
    if not _org_ok(ctx, i["org_unit_id"]):
        return _boundary(i["org_unit_id"])
    if i.get("rules") is not None:
        try:
            FraudRules.model_validate({"version": "sim", "threshold": i.get("threshold") or 1, "rules": i["rules"]})
        except ValueError as e:
            return "validation_error", f"The rules do not check out: {e}"
    if i.get("threshold") is not None and not i["threshold"] > 0:
        return "validation_error", "The threshold is above 0."
    return None


def _candidate(pack: Pack, i: dict[str, Any]) -> Pack:
    """The pack with the threshold and rules the simulation asks for (the customer's own threshold parameter no longer applies)."""
    base = pack.fraud
    if base is None and i.get("rules") is None:
        return pack
    rules = FraudRules.model_validate(
        {
            "version": base.version if base else "sim",
            "threshold": i["threshold"] if i.get("threshold") is not None else (base.threshold if base else 1),
            "rules": i["rules"] if i.get("rules") is not None else [r.model_dump() for r in (base.rules if base else [])],
        }
    )
    params = (
        {k: v for k, v in pack.customer_layer.params.items() if k != THRESHOLD_PARAM} if i.get("threshold") is not None else None
    )
    layer = pack.customer_layer if params is None else pack.customer_layer.model_copy(update={"params": params})
    return pack.model_copy(update={"fraud": rules, "customer_layer": layer})


@implement("fraud.simulate")
def simulate(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    """Held counts, per-rule counts and the cases whose answer changes, over the org's open cases of the pack. (Replay batches
    join in P9-7.1.)"""
    s = ctx.session
    owners = sorted(orgs.subtree(units(s), i["org_unit_id"]))
    rows = s.execute(
        text(
            "SELECT id FROM case_record WHERE owner = ANY(:o) AND stage <> 'closed' AND coalesce(data ->> 'template', 'industrial') = :p ORDER BY id"
        ),
        {"o": owners, "p": i["pack"]},
    ).scalars()
    held_now = held_then = 0
    by_rule: dict[str, int] = {}
    changes: list[dict[str, Any]] = []
    total = 0
    for cid in list(rows):
        case = store.get(s, cid)
        if case is None:
            continue
        total += 1
        pack = live_pack(s, case)
        now = triage_case(s, case, pack)
        then = triage_case(s, case, _candidate(pack, i))
        held_now, held_then = held_now + now.held, held_then + then.held
        for sig in then.fired():
            by_rule[sig.id] = by_rule.get(sig.id, 0) + 1
        if now.held != then.held:
            changes.append({"case_id": cid, "was": now.held, "now": then.held, "score": then.score})
    return {
        "pack": i["pack"], "org_unit_id": i["org_unit_id"], "cases": total, "held_now": held_now, "held": held_then,
        "by_signal": by_rule, "would_change": changes, "pack_in_force": active_pack(s, i["pack"], i["org_unit_id"]).version,
    }  # fmt: skip
