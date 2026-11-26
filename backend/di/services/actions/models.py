"""Calibration model actions (plan 8, MVP-12.2; story M): fit a candidate on the confirmed outcomes, promote it.

    model.fit      act     {template?, kind?}  a candidate model of the template (default industrial): the calibration factors
                                        (di.services.engine.calibration.fit) and, as metrics, the mean absolute error
                                        of the active model vs the candidate on the template's outcome rows. `kind`
                                        `rated_life` (template tool_fleet; plan 9, P9-3.10) fits instead the components'
                                        Weibull remaining life on the teardown verdicts of the actor's org units
                                        (di.services.models.rul_fit, imported only here); `price` (template device; plan 9,
                                        P9-6.9) fits the device price model, three conformalised LightGBM quantile boosters
                                        (di.services.models.price) on the settled sales and the feed; `take_up`
                                        (template tool_fleet; P9-4.11, `market?`) fits the logistic take-up curve on the last
                                        24 months of upgrade offers (di.services.models.take_up); `calibration` is the default
    model.propose  act     {id}         a person proposes a candidate for promotion (plan 8 UI gaps): stored as
                                        metrics.proposal {by, at}; manageFlows
    model.promote  commit  {id}         a proposed candidate -> active; the active model it replaces is retired
    model.list     read    {template?}  the template's models, the newest first (for agents and API clients); for a
                                        person who may fit or promote models
    stage.fitCalibration act {pack, stage}  plan 9, P9-2.9: a candidate `<pack>.stage.<stage>` whose steps map a stage's
                                        raw confidence to the share of its proposals and decisions a person accepted
                                        (di.services.agents.calibrate); manageFlows. Propose and promote follow as above.

Maker-checker as for decision flows (Domain spec D7): the person who fitted a model, or who proposed it, cannot promote
it, and an agent never proposes or promotes one (di.services.agents.forbidden.FORBIDDEN_ACTIONS; the guards refuse a prepared call
too). `promote_block` and `propose_block` say why a person may not, for the guards and the Agents page's Models panel
(di.services.screens.agents.models). A price model is promoted only after `min_shadow` (the device pack's, 30) evaluations
were shadowed (P9-6.18, di.services.device.price_shadow). An active model calibrates the predictor of new intake cases only
(`intake_predictor`); the cases opened from the engine's book keep their routes.
"""

import dataclasses
import json
from collections.abc import Mapping, Sequence
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from di.core import policy
from di.repositories import model_versions as repo
from di.repositories import stage_outcomes
from di.repositories.model_versions import ModelRow
from di.repositories.outcomes import outcome_rows
from di.services.actions.pipeline import CallContext
from di.services.actions.registry import ACTIONS, ActionDef, ActionError, guard, implement
from di.services.agents import calibrate
from di.services.agents.stage_context import STAGE_IDS
from di.services.engine.calibration import CalibratedPredictor, Key, OutcomeRow, fit
from di.services.engine.predictor import Predictor
from di.services.modeler.templates import TEMPLATE_KEYS

MAKER_CHECKER = "Maker-checker: you created this model, so you cannot promote it."
FIT_KINDS = ("calibration", "rated_life", "price", "take_up")
PROPOSER_CHECKER = "Maker-checker: you proposed this model, so you cannot promote it."

ACTIONS.setdefault(
    "model.fit",
    ActionDef(
        id="model.fit", title="Fit a model candidate", risk="act", perm="manageFlows", scope="none",
        verb="fit models", desc="Fit a candidate calibration model on the confirmed outcomes. It is used only once "
        "a different person promotes it.",
        input={
            "template": {"req": False, "t": "string"}, "kind": {"req": False, "t": "string"},
            "market": {"req": False, "t": "string"},
        },
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
ACTIONS.setdefault(
    "model.propose",
    ActionDef(
        id="model.propose", title="Propose a model for promotion", risk="act", perm="manageFlows", scope="none",
        verb="propose models", desc="Ask a different person to promote a candidate calibration model.",
        input={"id": {"req": True, "t": "string"}},
    ),
)  # fmt: skip


def proposal_of(m: ModelRow) -> dict[str, Any] | None:
    """Who proposed the model for promotion, and when ({by, at}), or None."""
    p = (m.metrics or {}).get("proposal")
    return p if isinstance(p, dict) else None


def propose_block(m: ModelRow) -> str | None:
    """Why the model cannot be proposed (the person's permission aside), or None."""
    if m.status != "candidate":
        return f"{m.id} is not a candidate."
    return f"{m.id} is already proposed." if proposal_of(m) else None


def promote_block(m: ModelRow, actor: str, s: Session | None = None) -> str | None:
    """Why `actor` cannot promote the model (the permission aside), or None: maker-checker, then the proposal, then, for a
    price model (with a session to count in), the shadowed evaluations it needs first (P9-6.18, `price_shadow`)."""
    if m.status != "candidate":
        return f"{m.id} is not a candidate."
    if m.created_by == actor:
        return MAKER_CHECKER
    p = proposal_of(m)
    if p is None:
        return f"Propose {m.id} for promotion first."
    if p.get("by") == actor:
        return PROPOSER_CHECKER
    if m.kind == "price" and s is not None:
        from di.services.device import price_shadow

        n, need = price_shadow.shadow_count(s, m.id), price_shadow.min_shadow()
        if n < need:
            return price_shadow.block_text(n, need)
    return None


ACTIONS.setdefault(
    "model.list",
    ActionDef(
        id="model.list", title="List calibration models", risk="read", perm=None, scope="none", verb="read models",
        desc="The calibration models of a template, the newest first. Changes nothing.",
        input={"template": {"req": False, "t": "string"}},
    ),
)  # fmt: skip


def _mae(rows: Sequence[OutcomeRow], factors: Mapping[Key, float]) -> float | None:
    """Mean absolute error of the predicted net scaled by the factors (1 without one) against the actual net."""
    if not rows:
        return None
    errs = [abs(r["actual_net"] - r["predicted_net"] * factors.get((r["template"], r["route"], r["cls"]), 1.0)) for r in rows]
    return sum(errs) / len(errs)


def model_json(m: ModelRow) -> dict[str, Any]:
    # a price model's artefact (its boosters as text) stays in the table: the screens and actions send its metrics
    factors = [] if m.kind == "price" else m.factors
    return {
        "id": m.id, "template": m.template, "factors": factors, "status": m.status, "created_by": m.created_by,
        "approved_by": m.approved_by, "metrics": m.metrics, "created_at": m.created_at.isoformat(), "kind": m.kind,
    }  # fmt: skip


# ---------------------------------------------------------------- fit
@guard("model.fit")
def fit_guard(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | None:  # noqa: ARG001 - the guard signature
    t = i.get("template") or "industrial"
    kind = i.get("kind") or "calibration"
    if kind not in FIT_KINDS:
        return "validation_error", f"The kind is one of {', '.join(FIT_KINDS)}."
    if kind == "rated_life" and t != "tool_fleet":
        return "validation_error", "A rated-life model is fitted for the tool_fleet template."
    if kind == "price" and t != "device":
        return "validation_error", "A price model is fitted for the device template."
    if kind == "take_up" and t != "tool_fleet":
        return "validation_error", "A take-up model is fitted for the tool_fleet template."
    return None if t in TEMPLATE_KEYS else ("validation_error", f"The template is one of {', '.join(TEMPLATE_KEYS)}.")


def _insert_candidate(
    ctx: CallContext, template: str, kind: str, factors: list[dict[str, Any]], metrics: dict[str, Any]
) -> dict[str, Any]:
    mid = repo.next_id(ctx.session)
    ctx.session.execute(
        text(
            "INSERT INTO model_version (id, template, factors, status, created_by, metrics, created_at, kind) "
            "VALUES (:i, :t, CAST(:f AS jsonb), 'candidate', :by, CAST(:m AS jsonb), :now, :k)"
        ),
        {
            "i": mid,
            "t": template,
            "f": json.dumps(factors),
            "by": ctx.actor.id,
            "m": json.dumps(metrics),
            "now": ctx.now,
            "k": kind,
        },  # fmt: skip
    )
    m = repo.get(ctx.session, mid)
    if m is None:  # not reached: inserted above
        raise ActionError("not_found", f"No model {mid}.")
    return model_json(m)


def _fit_rated_life(ctx: CallContext) -> dict[str, Any]:
    """The remaining-life candidate (P9-3.10): a Weibull per component and class on the teardown verdicts of the org units the
    actor may see (a serial no contract names is depot-wide history, visible to all). Components whose repair-log name the pack
    maps (`repair_aliases`) are stored under the pack's name. lifelines loads here only."""
    from di.repositories import teardowns
    from di.services.modeler.valuers import tool_inputs
    from di.services.models.rul import TeardownRow
    from di.services.models.rul_fit import fit_rated_life

    params = tool_inputs.LIFE_PARAMS
    acct = ctx.actor.account
    by_cls: dict[str, list[TeardownRow]] = {}
    for cls, r in teardowns.rows(ctx.session):
        if cls not in params["classes"]:
            continue
        if r.org is not None and (acct is None or not policy.tenant_ok(acct, r.org, ctx.actor.ctx)):
            continue  # a contract of an org the actor may not see
        alias = (params.get("repair_aliases") or {}).get(cls) or {}
        by_cls.setdefault(cls, []).append(dataclasses.replace(r, component=alias.get(r.component, r.component)))
    factors: list[dict[str, Any]] = []
    classes: dict[str, Any] = {}
    errs: list[tuple[float, int]] = []
    conc: list[tuple[float, int]] = []
    for cls, rows in sorted(by_cls.items()):
        c = fit_rated_life(rows, cls)
        factors += [{"cls": cls, **f} for f in c.components]
        classes[cls] = {
            "n": c.n, "held_out": c.held_out, "mae": c.mae, "concordance": c.concordance, "skipped": c.skipped, "notes": c.notes,
        }  # fmt: skip
        if c.mae is not None:
            errs.append((c.mae, c.held_out))
        if c.concordance is not None:
            conc.append((c.concordance, c.held_out))

    def mean(xs: list[tuple[float, int]]) -> float | None:
        return sum(x * w for x, w in xs) / sum(w for _, w in xs) if xs else None

    act = repo.active(ctx.session, "tool_fleet", "rated_life")
    mae = mean(errs)
    metrics = {
        "n": sum(len(v) for v in by_cls.values()), "active_id": act.id if act else None, "mae_active": None, "mae_candidate": mae,
        "kind": "rated_life", "mae": mae, "concordance": mean(conc), "held_out": sum(w for _, w in errs), "by_class": classes,
    }  # fmt: skip
    return _insert_candidate(ctx, "tool_fleet", "rated_life", factors, metrics)


def _fit_price(ctx: CallContext) -> dict[str, Any]:
    """The device price candidate (P9-6.9): the settled sales and the feed as of today, fitted and conformalised. The artefact
    is stored as `factors[0]["artefact"]`; the metrics are what the Models panel shows. LightGBM and MAPIE load here only."""
    from di.services.models import price_rows
    from di.services.models.price import MIN_ROWS, TOO_FEW, PriceModel

    rows = price_rows.training_rows(ctx.session, ctx.now.date())
    if len(rows) < MIN_ROWS:
        raise ActionError("validation_error", TOO_FEW)
    model = PriceModel.fit(rows)
    act = repo.active(ctx.session, "device", "price")
    mae = model.metrics["mae"]
    metrics = {
        "n": len(rows), "active_id": act.id if act else None, "mae_active": (act.metrics or {}).get("mae") if act else None,
        "mae_candidate": mae, "kind": "price", **model.metrics,
    }  # fmt: skip
    return _insert_candidate(ctx, "device", "price", [{"artefact": model.save()}], metrics)


def _fit_take_up(ctx: CallContext, market: str | None) -> dict[str, Any]:
    """The take-up candidate (P9-4.11): a logistic curve of acceptance on the credit share, on the offers of the last 24 months
    (of one market, or all) in the org units the actor may see. The metrics carry the pack's prior on the same rows as the
    baseline. `factors` is `[{a, b}]`; the candidate replaces the prior in `service_desk.inputs` once promoted."""
    from di.repositories import upgrade_offers
    from di.services.models import take_up
    from di.services.service_desk.inputs import take_up_prior

    acct, until = ctx.actor.account, ctx.now.date()
    since = upgrade_offers.window_start(until)
    rows = [
        r
        for r in upgrade_offers.window(ctx.session, since, until, market)
        if r.org is None or (acct is not None and policy.tenant_ok(acct, r.org, ctx.actor.ctx))
    ]
    if len(take_up.points_of(rows)) < take_up.MIN_OFFERS:
        raise ActionError("validation_error", take_up.TOO_FEW)
    f = take_up.fit_curve(rows)
    prior = take_up_prior()
    base_ll, base_br = take_up.score(prior["a"], prior["b"], take_up.points_of(rows))
    act = repo.active(ctx.session, "tool_fleet", "take_up")
    metrics = {
        "n": f.n, "active_id": act.id if act else None, "mae_active": None, "mae_candidate": None, "kind": "take_up",
        "market": market, "window": {"from": since.isoformat(), "to": until.isoformat()},
        "log_loss": f.log_loss, "brier": f.brier, "baseline_log_loss": base_ll, "baseline_brier": base_br,
        "prior": {"a": prior["a"], "b": prior["b"]}, "bands": f.bands,
    }  # fmt: skip
    return _insert_candidate(ctx, "tool_fleet", "take_up", [{"a": f.a, "b": f.b}], metrics)


def price_predictor(s: Session, base: Predictor) -> Predictor:
    """`base`, with the active device price model's band for `channel_price` if a person has promoted one (P9-6.9)."""
    act = repo.active(s, "device", "price")
    if act is None or not act.factors:
        return base
    from di.services.models.price import ModelPredictor, PriceModel

    return ModelPredictor(base, PriceModel.load(act.factors[0]["artefact"]), act.id)


@implement("model.fit")
def fit_model(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    t = i.get("template") or "industrial"
    if i.get("kind") == "rated_life":
        return _fit_rated_life(ctx)
    if i.get("kind") == "price":
        return _fit_price(ctx)
    if i.get("kind") == "take_up":
        return _fit_take_up(ctx, i.get("market") or None)
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


# ---------------------------------------------------------------- stage calibration (plan 9, P9-2.9)
ACTIONS.setdefault(
    "stage.fitCalibration",
    ActionDef(
        id="stage.fitCalibration", title="Fit a stage calibration", risk="act", perm="manageFlows", scope="none",
        verb="fit stage calibrations", desc="Fit a candidate that maps a chain stage's raw confidence to the share of its "
        "proposals and decisions a person accepted. It is used only once a different person promotes it.",
        input={"pack": {"req": True, "t": "string"}, "stage": {"req": True, "t": "string"}},
    ),
)  # fmt: skip


@guard("stage.fitCalibration")
def fit_calibration_guard(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | None:
    if i["pack"] not in TEMPLATE_KEYS:
        return "validation_error", f"The pack is one of {', '.join(TEMPLATE_KEYS)}."
    if i["stage"] not in STAGE_IDS:
        return "validation_error", f"The stage is one of {', '.join(STAGE_IDS)}."
    n = len(stage_outcomes.rows(ctx.session, i["pack"], i["stage"]))
    if n < calibrate.MIN_POINTS:
        return "conflict", f"The {i['stage']} stage has {n} decided outcomes; {calibrate.MIN_POINTS} are needed to calibrate it."
    return None


@implement("stage.fitCalibration")
def fit_stage_calibration(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    pack, stage = i["pack"], i["stage"]
    points = stage_outcomes.rows(ctx.session, pack, stage)
    steps = calibrate.fit(points) or []  # not empty: the guard counted the points
    template = stage_outcomes.template_key(pack, stage)
    act = repo.active(ctx.session, template)
    metrics = {
        "n": len(points), "active_id": act.id if act else None, "mae_active": None, "mae_candidate": None,
        "kind": "stage_calibration", "pack": pack, "stage": stage,
    }  # fmt: skip
    mid = repo.next_id(ctx.session)
    ctx.session.execute(
        text(
            "INSERT INTO model_version (id, template, factors, status, created_by, metrics, created_at) "
            "VALUES (:i, :t, CAST(:f AS jsonb), 'candidate', :by, CAST(:m AS jsonb), :now)"
        ),
        {
            "i": mid, "t": template, "f": json.dumps([{"raw": raw, "cal": cal} for raw, cal in steps]), "by": ctx.actor.id,
            "m": json.dumps(metrics), "now": ctx.now,
        },
    )  # fmt: skip
    m = repo.get(ctx.session, mid)
    if m is None:  # not reached: inserted above
        raise ActionError("not_found", f"No model {mid}.")
    return model_json(m)


# ---------------------------------------------------------------- propose
@guard("model.propose")
def propose_guard(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | None:
    m = repo.get(ctx.session, i["id"])
    if m is None:
        return "not_found", f"No model {i['id']}."
    if ctx.preparer:
        return "approval_required", "Models are proposed for promotion only by a person."
    block = propose_block(m)
    return ("conflict", block) if block else None


@implement("model.propose")
def propose(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    p = {"by": ctx.actor.id, "at": ctx.now.isoformat()}
    ctx.session.execute(
        text("UPDATE model_version SET metrics = metrics || jsonb_build_object('proposal', CAST(:p AS jsonb)) WHERE id = :i"),
        {"i": i["id"], "p": json.dumps(p)},
    )
    m = repo.get(ctx.session, i["id"])
    if m is None:  # not reached: the guard found it
        raise ActionError("not_found", f"No model {i['id']}.")
    return {**model_json(m), "proposal": p, "log": f"Proposed {m.id} for promotion"}


# ---------------------------------------------------------------- list
@guard("model.list")
def list_guard(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | None:
    acct = ctx.actor.account
    if acct is None or not any(policy.can(acct, p, ctx.actor.ctx) for p in ("manageFlows", "approve.flows")):
        return "out_of_scope", f"The {ctx.actor.role} view cannot read models."
    return fit_guard(i, ctx)


@implement("model.list")
def list_models(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    t = i.get("template") or "industrial"
    return {"template": t, "models": [model_json(m) for m in repo.of_template(ctx.session, t)]}


# ---------------------------------------------------------------- promote
@guard("model.promote")
def promote_guard(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | None:
    m = repo.get(ctx.session, i["id"])
    if m is None:
        return "not_found", f"No model {i['id']}."
    if ctx.preparer:
        return "approval_required", "Models are promoted only by a person."
    block = promote_block(m, ctx.actor.id, ctx.session)
    return ("conflict", block) if block else None


@implement("model.promote")
def promote(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    m = repo.get(ctx.session, i["id"], for_update=True)
    if m is None:  # not reached: the guard found it
        raise ActionError("not_found", f"No model {i['id']}.")
    old = repo.active(ctx.session, m.template, m.kind)
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
