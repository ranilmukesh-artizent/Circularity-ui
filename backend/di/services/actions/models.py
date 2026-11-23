"""Calibration model actions (plan 8, MVP-12.2; story M): fit a candidate on the confirmed outcomes, promote it.

    model.fit      act     {template?}  a candidate model of the template (default industrial): the calibration factors
                                        (di.services.engine.calibration.fit) and, as metrics, the mean absolute error
                                        of the active model vs the candidate on the template's outcome rows
    model.promote  commit  {id}         candidate -> active; the active model it replaces is retired

Maker-checker as for decision flows (Domain spec D7): the person who fitted a model cannot promote it, and an agent
never promotes one (di.mcp.policy.FORBIDDEN_ACTIONS). An active model calibrates the predictor of new intake cases only
(`intake_predictor`); the cases opened from the engine's book keep their routes.
"""

import json
from collections.abc import Mapping, Sequence
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from di.repositories import model_versions as repo
from di.repositories.model_versions import ModelRow
from di.repositories.outcomes import outcome_rows
from di.services.actions.pipeline import CallContext
from di.services.actions.registry import ACTIONS, ActionDef, ActionError, guard, implement
from di.services.engine.calibration import CalibratedPredictor, Key, OutcomeRow, fit
from di.services.engine.predictor import Predictor
from di.services.modeler.templates import TEMPLATE_KEYS

MAKER_CHECKER = "Maker-checker: you created this model, so you cannot promote it."

ACTIONS.setdefault(
    "model.fit",
    ActionDef(
        id="model.fit", title="Fit a model candidate", risk="act", perm="manageFlows", scope="none",
        verb="fit models", desc="Fit a candidate calibration model on the confirmed outcomes. It is used only once "
        "a different person promotes it.", input={"template": {"req": False, "t": "string"}},
    ),
)  # fmt: skip
ACTIONS.setdefault(
    "model.promote",
    ActionDef(
        id="model.promote", title="Promote a model", risk="commit", perm="approve.flows", scope="none",
        verb="promote models", desc="Make a candidate calibration model the active one for new intake cases.",
        input={"id": {"req": True, "t": "string"}},
    ),
)  # fmt: skip


def _mae(rows: Sequence[OutcomeRow], factors: Mapping[Key, float]) -> float | None:
    """Mean absolute error of the predicted net scaled by the factors (1 without one) against the actual net."""
    if not rows:
        return None
    errs = [abs(r["actual_net"] - r["predicted_net"] * factors.get((r["template"], r["route"], r["cls"]), 1.0)) for r in rows]
    return sum(errs) / len(errs)


def model_json(m: ModelRow) -> dict[str, Any]:
    return {
        "id": m.id, "template": m.template, "factors": m.factors, "status": m.status, "created_by": m.created_by,
        "approved_by": m.approved_by, "metrics": m.metrics, "created_at": m.created_at.isoformat(),
    }  # fmt: skip


# ---------------------------------------------------------------- fit
@guard("model.fit")
def fit_guard(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | None:  # noqa: ARG001 - the guard signature
    t = i.get("template") or "industrial"
    return None if t in TEMPLATE_KEYS else ("validation_error", f"The template is one of {', '.join(TEMPLATE_KEYS)}.")


@implement("model.fit")
def fit_model(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    t = i.get("template") or "industrial"
    rows = [r for r in outcome_rows(ctx.session) if r["template"] == t]
    factors = fit(rows)
    act = repo.active(ctx.session, t)
    metrics = {
        "n": len(rows),
        "active_id": act.id if act else None,
        "mae_active": _mae(rows, act.as_factors() if act else {}),
        "mae_candidate": _mae(rows, factors),
    }
    stored = [{"route": route, "cls": cls, "factor": f} for (_, route, cls), f in sorted(factors.items())]
    mid = repo.next_id(ctx.session)
    ctx.session.execute(
        text(
            "INSERT INTO model_version (id, template, factors, status, created_by, metrics, created_at) "
            "VALUES (:i, :t, CAST(:f AS jsonb), 'candidate', :by, CAST(:m AS jsonb), :now)"
        ),
        {"i": mid, "t": t, "f": json.dumps(stored), "by": ctx.actor.id, "m": json.dumps(metrics), "now": ctx.now},
    )
    m = repo.get(ctx.session, mid)
    if m is None:  # not reached: inserted above
        raise ActionError("not_found", f"No model {mid}.")
    return model_json(m)


# ---------------------------------------------------------------- promote
@guard("model.promote")
def promote_guard(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | None:
    m = repo.get(ctx.session, i["id"])
    if m is None:
        return "not_found", f"No model {i['id']}."
    if ctx.preparer:
        return "approval_required", "Models are promoted only by a person."
    if m.status != "candidate":
        return "conflict", f"{m.id} is not a candidate."
    return ("conflict", MAKER_CHECKER) if m.created_by == ctx.actor.id else None


@implement("model.promote")
def promote(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    m = repo.get(ctx.session, i["id"], for_update=True)
    if m is None:  # not reached: the guard found it
        raise ActionError("not_found", f"No model {i['id']}.")
    old = repo.active(ctx.session, m.template)
    if old is not None:
        ctx.session.execute(text("UPDATE model_version SET status = 'retired' WHERE id = :i"), {"i": old.id})
    ctx.session.execute(
        text("UPDATE model_version SET status = 'active', approved_by = :by WHERE id = :i"), {"i": m.id, "by": ctx.actor.id}
    )
    retired = f"; {old.id} retired" if old else ""
    return {"id": m.id, "status": "active", "retired": old.id if old else None, "log": f"Promoted {m.id}{retired}"}


# ---------------------------------------------------------------- intake
def intake_predictor(s: Session, base: Predictor, cls: str, template: str = "industrial") -> Predictor:
    """The predictor a new intake case is valued with: `base`, calibrated by the template's active model if any."""
    act = repo.active(s, template)
    return CalibratedPredictor(base, act.as_factors(), cls, template) if act else base
