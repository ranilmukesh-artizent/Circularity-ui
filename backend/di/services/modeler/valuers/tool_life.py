"""The wear index and the remaining life of a tool, component by component (plan 9, P9-3.9, story TF-06). Pure.

    components(cls, params, plm=(), replacements=None) -> list[Component]   the wear components and their rated life
    replacements_for(cls, raw, params) -> {component: run hours}             the repair log's replacements by component name
    evaluate(inp, params) -> LifeResult                                      the computation below (research A 1.5)

For component i of a tool that has run `h` hours, with high-load share `s_hi` and the events `n_e` the telematics counted:

    k_i   = 1 + alpha_i * s_hi                      load sensitivity: hours under high load wear it faster
    U_i   = max(0, h - h0_i) * k_i + sum(n_e * p_e) used life in equivalent hours (`h0_i`: hours at its last replacement)
    c_i   = min(1, U_i / L_i)                       consumed share of the rated life `L_i`
    RUL_i = round(100 * (1 - c_i))                  remaining life of the component, in percent
    WTI   = round(100 * sum(w_i * c_i))             wear index of the tool (weights are shares of the tool's life)
    RUL_tool = min RUL_i over the critical components, and in hours (L_i - U_i) / k_i for the weakest.

Without telematics `h = months_on_contract * duty P50` (hours a month), `s_hi` is the class default, and `range` is RUL_tool
at duty P90 (low) and P10 (high). **Confidence**: High with coverage >= 90, telemetry under 7 days old and a complete repair
history; Low with no telematics or a reading 7 days old or more (GR-13 failed); Medium otherwise.

`params` is the pack's `valuer.params.life` (rated life per component, weights, load sensitivity, event penalties, duty hours,
confidence limits, `table_version`, `rule_version`): illustrative numbers owned by Quality, changed only through the overlay.
The result records its inputs, so a replay (phase 7) runs the same numbers.

`disagreement(grade, life, damage_code)` (P9-3.11, TF-11) compares the wear index with the workbench grade: grade A or B
with WTI >= 60, or grade D with WTI <= 20 and no damage code, is a disagreement naming each component whose
consumed share is >= 60% (A or B) or <= 20% (D).
An estimated grade never triggers it. The text is computed from those numbers, never written by a model.

Never does: read the database or the clock (the caller passes the facts and the age of the reading), learn (P9-3.10 adds the
model behind it) or write text: no model step, so no AgentLoop. Implements no registry entry.
"""

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from di.services.modeler.valuers.tool_inputs import GradeView

Confidence = Literal["High", "Medium", "Low"]


@dataclass(frozen=True)
class Component:
    name: str
    rated_hours: float
    weight: float
    critical: bool
    alpha: float
    h0: float  # run hours at its last replacement (0: never replaced)
    source: str  # where the rated life came from: "plm" or "pack"


@dataclass(frozen=True)
class LifeInputs:
    cls: str
    hours: float | None  # telematics run hours; None: none on file
    high_load_share: float | None
    events: Mapping[str, int]
    months_on_contract: int | None
    coverage_pct: float | None
    telemetry_age_days: float | None
    repair_history_complete: bool
    components: Sequence[Component]


@dataclass(frozen=True)
class ComponentLife:
    name: str
    used_hours: float
    consumed_pct: int
    rul_pct: int
    source: str


@dataclass(frozen=True)
class LifeResult:
    wti: int
    rul_tool: int
    rul_tool_hours: float
    weakest: str
    per_component: list[ComponentLife]
    confidence: Confidence
    range: tuple[int, int] | None
    inputs: dict[str, Any]
    table_version: str
    rule_version: str


def _round(x: float) -> int:
    """Half up, as the prototype's Math.round does (Python's round goes to even)."""
    return int(math.floor(x + 0.5))


def components(
    cls: str, params: Mapping[str, Any], plm: Sequence[Mapping[str, Any]] = (), replacements: Mapping[str, float] | None = None
) -> list[Component]:
    """The class's wear components: the pack's table, each with the rated life, weight and critical flag PLM gives it when PLM
    rates it (source `plm`), else the pack's own (source `pack`). A component only PLM rates is added (load sensitivity 0).
    `replacements` are the run hours at each component's last replacement (`replacements_for`)."""
    rep = replacements or {}
    rated = {str(p["name"]): p for p in plm}
    out = []
    for t in (params.get("classes", {}).get(cls) or {}).get("components") or []:
        p = rated.pop(t["name"], None)
        out.append(
            Component(
                t["name"], float(p["rated_life_hours"] if p else t["rated_hours"]), float(p["weight"] if p else t["weight"]),
                bool(p["critical"] if p else t["critical"]), float(t.get("alpha") or 0), float(rep.get(t["name"], 0)),
                "plm" if p else "pack",
            )
        )  # fmt: skip
    for name, p in rated.items():
        out.append(
            Component(name, float(p["rated_life_hours"]), float(p.get("weight") or 0), bool(p.get("critical")), 0.0,
                      float(rep.get(name, 0)), "plm")
        )  # fmt: skip
    return out


def replacements_for(cls: str, raw: Mapping[str, Any], params: Mapping[str, Any]) -> dict[str, float]:
    """The repair log's replacements (its own component names, run hours at the replacement) as `{component: hours}`: a name the
    pack maps (`repair_aliases`) or that is a component's own name; the latest replacement of a component counts."""
    alias = (params.get("repair_aliases") or {}).get(cls) or {}
    names = {t["name"] for t in (params.get("classes", {}).get(cls) or {}).get("components") or []}
    out: dict[str, float] = {}
    for name, hrs in raw.items():
        comp = alias.get(name, name)
        if comp in names and hrs is not None:
            out[comp] = max(out.get(comp, 0.0), float(hrs))
    return out


def _lives(comps: Sequence[Component], h: float, s_hi: float, penalty: float) -> list[tuple[Component, float, float, float]]:
    """(component, used hours, consumed share, load factor k) for the tool at `h` hours."""
    out = []
    for c in comps:
        k = 1 + c.alpha * s_hi
        u = max(0.0, h - c.h0) * k + penalty
        out.append((c, u, min(1.0, u / c.rated_hours) if c.rated_hours > 0 else 1.0, k))
    return out


def _weakest(rows: Sequence[tuple[Component, float, float, float]]) -> tuple[Component, float, float, float]:
    crit = [r for r in rows if r[0].critical] or list(rows)
    return min(crit, key=lambda r: (_round(100 * (1 - r[2])), (r[0].rated_hours - r[1]) / r[3]))


def _rul_tool(comps: Sequence[Component], h: float, s_hi: float, penalty: float) -> int:
    return _round(100 * (1 - _weakest(_lives(comps, h, s_hi, penalty))[2]))


def evaluate(inp: LifeInputs, params: Mapping[str, Any]) -> LifeResult:
    """The wear index and remaining life (module docstring). Needs the telematics hours or the months on contract."""
    comps = list(inp.components)
    if not comps:
        raise ValueError(f"No wear components for the class {inp.cls}")
    duty = params["classes"][inp.cls]["duty"] if inp.cls in params.get("classes", {}) else params["duty"]
    s_hi = float(params["default_high_load_share"] if inp.high_load_share is None else inp.high_load_share)
    penalty = sum(int(n) * float((params.get("events") or {}).get(e, 0)) for e, n in inp.events.items())
    tel = inp.hours is not None
    if inp.hours is not None:
        h = float(inp.hours)
    elif inp.months_on_contract is not None:
        h = inp.months_on_contract * float(duty["p50"])
    else:
        raise ValueError("Life needs the telematics hours or the months on contract")
    rows = _lives(comps, h, s_hi, penalty)
    total_w = sum(c.weight for c in comps)
    wsum = sum(c.weight * share for c, _u, share, _k in rows)
    wti = _round(100 * (wsum if abs(total_w - 1) < 1e-9 or total_w <= 0 else wsum / total_w))
    weak, u, share, k = _weakest(rows)
    cl = params.get("confidence") or {}
    age = inp.telemetry_age_days
    if not tel or age is None or age >= float(cl.get("max_age_days", 7)):
        confidence: Confidence = "Low"
    elif (
        inp.coverage_pct is not None
        and inp.coverage_pct >= float(cl.get("high_coverage_pct", 90))
        and inp.repair_history_complete
    ):
        confidence = "High"
    else:
        confidence = "Medium"
    rng = None
    if not tel:
        rng = (
            _rul_tool(comps, inp.months_on_contract * float(duty["p90"]), s_hi, penalty),  # type: ignore[operator]
            _rul_tool(comps, inp.months_on_contract * float(duty["p10"]), s_hi, penalty),  # type: ignore[operator]
        )
    return LifeResult(
        wti=wti,
        rul_tool=_round(100 * (1 - share)),
        rul_tool_hours=round(max(0.0, (weak.rated_hours - u) / k), 1),
        weakest=weak.name,
        per_component=[
            ComponentLife(c.name, round(x, 1), _round(100 * sh), _round(100 * (1 - sh)), c.source) for c, x, sh, _k in rows
        ],
        confidence=confidence,
        range=rng,
        inputs={
            "hours": round(h, 1),
            "hours_source": "telematics" if tel else "contract",
            "high_load_share": s_hi,
            "high_load_source": "telematics" if inp.high_load_share is not None else "class default",
            "events": dict(inp.events),
            "months_on_contract": inp.months_on_contract,
            "coverage_pct": inp.coverage_pct,
            "telemetry_age_days": age,
            "repair_history_complete": inp.repair_history_complete,
            "components": [
                {
                    "name": c.name,
                    "rated_hours": c.rated_hours,
                    "weight": c.weight,
                    "critical": c.critical,
                    "alpha": c.alpha,
                    "h0": c.h0,
                    "source": c.source,
                }
                for c in comps
            ],
        },  # fmt: skip
        table_version=str(params.get("table_version") or ""),
        rule_version=str(params.get("rule_version") or ""),
    )


# ---------------------------------------------------------------- telematics against the workbench grade (P9-3.11)
WTI_HIGH = 60  # a grade A or B tool at or above this wear index disagrees with its telematics
WTI_LOW = 20  # a grade D tool at or below this wear index (and no damage code) disagrees
COMPONENT_HIGH = 60  # consumed share (%) that names a component in the A or B case
COMPONENT_LOW = 20  # consumed share (%) that names a component in the D case


@dataclass(frozen=True)
class Disagreement:
    text: str
    components: list[str]


def life_from_dict(d: Mapping[str, Any]) -> LifeResult:
    """A `LifeResult` from its dict form (what the case keeps in `life`: `dataclasses.asdict`, range as a list)."""
    rng = d.get("range")
    return LifeResult(
        wti=int(d["wti"]), rul_tool=int(d["rul_tool"]), rul_tool_hours=float(d["rul_tool_hours"]), weakest=str(d["weakest"]),
        per_component=[ComponentLife(**c) for c in d.get("per_component") or []], confidence=d["confidence"],
        range=(int(rng[0]), int(rng[1])) if rng else None, inputs=dict(d.get("inputs") or {}),
        table_version=str(d.get("table_version") or ""), rule_version=str(d.get("rule_version") or ""),
    )  # fmt: skip


def disagreement(grade: "GradeView", life: LifeResult, damage_code: bool) -> Disagreement | None:
    """The workbench grade and the wear index disagree (module docstring), else None. An estimated grade never does."""
    if grade.source != "workbench":
        return None
    if grade.grade in ("A", "B") and life.wti >= WTI_HIGH:
        named = [c for c in life.per_component if c.consumed_pct >= COMPONENT_HIGH]
    elif grade.grade == "D" and life.wti <= WTI_LOW and not damage_code:
        named = [c for c in life.per_component if c.consumed_pct <= COMPONENT_LOW]
    else:
        return None
    parts = ", ".join(f"{c.name} {c.consumed_pct}%" for c in named)
    text = f"Telematics and inspection disagree: grade {grade.grade}, WTI {life.wti}" + (f" ({parts})" if parts else "")
    return Disagreement(text, [c.name for c in named])
