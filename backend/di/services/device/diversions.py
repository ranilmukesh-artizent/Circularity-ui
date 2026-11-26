"""The customer's diversions on a received device (plan 9, P9-6.14, story DV-10; registry entry I-4 runs them, `decide_case` I-6).

    waiting(case, diversions, session) -> Diversion | None   the matched step "Second grading check" while none is on file
    hold(case, routes, d)                                    no channel is valued; the case waits for `grading_second`
    applied(case, diversions, go) -> list[dict]              the diversions that acted, for the case page
    model_age_text(months) -> str                            "model over 3 years"

The pack offers two sample diversions (`customer_layer.sample_diversions` of device.json): a device from retail partner P02 or P04
adds the step "Second grading check" (`add_step` at the condition stage), and grade C of a model over 36 months old goes to the
wholesale lot (`shortcut` at the value stage, only `wholesale` is then valued). A customer publishes either through the overlay
(maker-checker, tenant boundary and the refusal for agents are the overlay's own); neither is a new action. They run after the
gates (R20): a held case keeps the gate's hold, and a shortcut never brings back a channel a gate blocked.
The second grading is the lab's `condition.cosmetic_grade_second` (evidence `grading_second`); when it lands the case is checked
again (`canonical.store.apply` queues `case.gateRecheck`). Partner codes are synthetic (P01-P05).
Never does: decide a route, approve, write the store or call a language model: age and partner are counted (R16).
"""

from collections.abc import Mapping, MutableMapping, Sequence
from typing import Any

from sqlalchemy.orm import Session

from di.core import clock
from di.services.canonical import store as canonical
from di.services.engine.routes import POLICY, Route, fail
from di.services.modeler.pack import Diversion

STEP = "Second grading check"
EVIDENCE = "grading_second"  # the evidence type and the hold's gate id
FIELD = "cosmetic_grade_second"  # the canonical `condition` field of the lab's second grading
REASON = "Waiting for the second grading before any channel is priced"


def _imei(case: Mapping[str, Any]) -> str | None:
    v = case.get("valuer")
    return str(v["imei"]) if isinstance(v, Mapping) and v.get("imei") else None


def second_grading(case: Mapping[str, Any], session: Session | None) -> Any:
    """The lab's second grading of the device: read from the canonical store when a session is given, else the case's snapshot."""
    imei = _imei(case)
    if session is not None and imei:
        cond = (canonical.get(session, "condition", f"IMEI:{imei}") or {}).get("data") or {}
        return cond.get(FIELD)
    return (((case.get("valuer") or {}).get("inputs") or {}).get("evidence") or {}).get(EVIDENCE)


def waiting(case: Mapping[str, Any], diversions: Sequence[Diversion], session: Session | None = None) -> Diversion | None:
    """The first matched `Second grading check` step while no second grading is on file, else None. A case a gate already holds
    keeps that hold (R20: gates first); the step still shows in its required steps."""
    d = next((x for x in diversions if x.kind == "step" and x.step == STEP), None)
    if d is None or case.get("gateHold") is not None or second_grading(case, session) not in (None, ""):
        return None
    return d


def hold(case: MutableMapping[str, Any], routes: list[Route], d: Diversion) -> None:
    """Value nothing: each open route fails with `REASON` (naming the diversion) and the case is held with no recommendation, as a
    gate hold is (the time it has been held since stays)."""
    for r in routes:
        if not r["excluded"]:
            fail(r, POLICY, f"{REASON} ({d.op_id})")
    prior = case.get("gateHold") or {}
    since = prior.get("since") or clock.now().isoformat()
    case["gateHold"] = {"gates": [EVIDENCE], "since": since, "batch": case.get("batchRef")}
    case["recommendation"] = None
    case["stage"] = "none"


def model_age_text(months: float) -> str:
    whole = int(months)
    return f"model over {whole // 12} years" if whole % 12 == 0 else f"model over {whole} months"


def _because(d: Diversion) -> list[str]:
    """The conditions of the diversion in words: "partner P02", "grade C", "model over 3 years"."""
    out: list[str] = []
    for c in d.when:
        fact, op, value = str(c.get("fact")), c.get("op"), c.get("value")
        if fact == "valuer.partner" and op == "in" and isinstance(value, list):
            out.append("partner " + " or ".join(str(v) for v in value))
        elif fact == "valuer.grade" and op == "eq":
            out.append(f"grade {value}")
        elif fact.endswith("model_age_months") and op == "gte" and isinstance(value, int | float):
            out.append(model_age_text(float(value)))
    return out


def applied(case: Mapping[str, Any], diversions: Sequence[Diversion], go: str | None) -> list[dict[str, Any]]:
    """What the matched diversions did to the case: a step (listed, it may hold the case) and a shortcut that took its route
    (`go` is the chosen route). A partner a condition names is narrowed to the device's own (`partner P02`)."""
    partner = str((case.get("valuer") or {}).get("partner") or "")
    out: list[dict[str, Any]] = []
    for d in diversions:
        if d.kind == "shortcut" and not (go and go.split(":", 1)[0] == d.to):
            continue
        why = [f"partner {partner}" if w.startswith("partner ") and partner else w for w in _because(d)]
        out.append({"op": d.op_id, "kind": d.kind, "step": d.step, "to": d.to, "because": why})
    return out
