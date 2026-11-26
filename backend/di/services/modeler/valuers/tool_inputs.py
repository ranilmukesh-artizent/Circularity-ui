"""The tool-fleet valuer's case from the evidence on file (plan 9, P9-3.5, story TF-03). Pure.

    grade_of(evidence, est_grade, now=None) -> GradeView        the grade a case shows and where it came from
    life_of(evidence, cls, now) -> LifeResult | None            the wear index and remaining life (P9-3.9, `tool_life`)
    valuer_case(base, evidence, now=None) -> dict               the `tool_fleet` valuer case with that grade and life set

The evidence is a mapping of evidence type to the newest record on file, or None (`workbench_grade`, from the repair log's
`condition` record of the serial, di.services.cases.regrade; `life_inputs`, di.services.cases.life_evidence). Later tasks
extend `valuer_case`.
    merge_demand(base, extra) -> dict                           a valuer `dem` with named orders added (P9-3.12)

- **Life.** With telematics hours or a contract duration on file, `rul` and `partRul` are computed (`tool_life`, the pack's
  `valuer.params.life` table, PLM's rated life first) and replace the case's input values; the result is `life`. Without
  either, the case's own `rul` and `partRul` stay (the sample world and cases with no evidence).

- **Workbench grade.** A `workbench_grade` record whose `grade` is set and whose `test_result` is not null. The valuer
  then reads `grade` as it always did.
- **Estimate.** Anything else, including a grade still in progress (no test result): `grade` is left None and `estGrade`
  keeps the valuer's own estimate, which `tool_fleet._grade()` already falls back to. The panel labels it an estimate.

Never does: compute a grade (A 1.5), read the database, the clock (the modeler is pure) or write anything. The caller
passes `now`; without it `age_hours` is None. Implements no registry entry; the evidence type is the pack's `data.mappings` row.
"""

import copy
import dataclasses
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from di.services.modeler.evidence import Evidence
from di.services.modeler.pack import load_pack
from di.services.modeler.valuers import fleet_evidence, tool_fleet, tool_life
from di.services.models.rul import RulModel

WORKBENCH = "workbench_grade"
LIFE = "life_inputs"  # the evidence type of the life facts (P9-3.9): value keys in `life_of`
LIFE_PARAMS: Mapping[str, Any] = load_pack("tool_fleet").valuer.params["life"]  # the pack's life table (never changed here)


@dataclass(frozen=True)
class GradeView:
    grade: str
    source: Literal["workbench", "estimate"]
    ref: str | None
    at: str | None
    age_hours: float | None


def _workbench(evidence: Mapping[str, Evidence | None]) -> Evidence | None:
    """The workbench grade record when it counts: a grade and a test result."""
    e = evidence.get(WORKBENCH)
    if e is None or not e.value.get("grade") or e.value.get("test_result") is None:
        return None
    return e


def grade_of(evidence: Mapping[str, Evidence | None], est_grade: str, now: datetime | None = None) -> GradeView:
    """The workbench grade with its reference and age, else the estimate."""
    e = _workbench(evidence)
    if e is None:
        return GradeView(est_grade, "estimate", None, None, None)
    age = None if now is None else round(max((now - e.at).total_seconds() / 3600, 0.0), 1)
    ref = e.value.get("inspection_ref")
    return GradeView(str(e.value["grade"]), "workbench", str(ref) if ref else None, e.at.isoformat(), age)


def life_of(
    evidence: Mapping[str, Evidence | None], cls: str, now: datetime | None = None, rul_model: RulModel | None = None
) -> tool_life.LifeResult | None:
    """The tool's wear index and remaining life from the `life_inputs` evidence (telematics run hours, high-load share, event
    counts, coverage, months on contract, the repair log's replacements, PLM's ratings; di.services.cases.life_evidence),
    computed by `tool_life.evaluate` with the pack's table, or with the promoted remaining-life model (`rul_model`, P9-3.10)
    for the components it covers (the life result's `table_version` is then the model id). None when the evidence has neither
    the telematics hours nor the months on contract, or the class has no components: the case's own inputs then stay."""
    e = evidence.get(LIFE)
    if e is None:
        return None
    v = e.value
    if v.get("hours") is None and v.get("months_on_contract") is None:
        return None
    comps = tool_life.components(
        cls, LIFE_PARAMS, v.get("ratings") or (), tool_life.replacements_for(cls, v.get("replacements") or {}, LIFE_PARAMS)
    )
    comps = tool_life.with_model(comps, rul_model)  # a promoted rated_life model rates what it covers (P9-3.10)
    if not comps:
        return None
    seen = v.get("telemetry_at")
    age = fleet_evidence.age_days(seen, now) if now is not None and seen else None
    inp = tool_life.LifeInputs(
        cls=cls, hours=v.get("hours"), high_load_share=v.get("high_load_share"), events=v.get("events") or {},
        months_on_contract=v.get("months_on_contract"), coverage_pct=v.get("coverage_pct"),
        telemetry_age_days=None if age is None else float(age),
        repair_history_complete=bool(v.get("repair_history_complete", True)), components=comps,
    )  # fmt: skip
    res = tool_life.evaluate(inp, LIFE_PARAMS)
    if rul_model and any(c.source == "model" for c in comps):
        return dataclasses.replace(res, table_version=rul_model.version)
    return res


def merge_demand(base: Mapping[str, Any], extra: Mapping[str, Any]) -> dict[str, Any]:
    """`base` (a valuer `dem`: lease, so, bid lists, proj one or None, wo part -> list) with the named orders of `extra` added
    (P9-3.12, the live named demand, `di.repositories.tool_demand`): one order for each id, the base's own first; a base `proj`
    stays; `rcq` stays. Neither argument is changed."""
    out = copy.deepcopy(dict(base))
    for kind in ("lease", "so", "bid"):
        have = out.setdefault(kind, [])
        seen = {d["id"] for d in have}
        have += [copy.deepcopy(d) for d in extra.get(kind) or [] if d["id"] not in seen]
    if extra.get("proj") and not out.get("proj"):
        out["proj"] = copy.deepcopy(extra["proj"])
    wo = out.setdefault("wo", {})
    for part, orders in (extra.get("wo") or {}).items():
        have = wo.setdefault(part, [])
        seen = {d["id"] for d in have}
        have += [copy.deepcopy(d) for d in orders if d["id"] not in seen]
    return out


BATTERY_SOH = "battery_soh"  # the evidence type of a pack's state of health (P9-3.19): value `soh_pct`, `read_at`, `damaged`


def battery_case(base: Mapping[str, Any], evidence: Mapping[str, Evidence | None]) -> dict[str, Any]:
    """`base` (a `BAT` case as opened) with the state of health read from the `battery_soh` evidence (the tool telematics'
    reading of the pack: percent, the date it was read, whether the pack is damaged): `soh`, `sohRead` and `damaged`. Without
    the record `soh` is None and nothing is assumed (`battery.decide` then leaves only take-back). Neither argument is changed."""
    c = copy.deepcopy(dict(base))
    e = evidence.get(BATTERY_SOH)
    v = e.value if e is not None else {}
    c["soh"] = v.get("soh_pct")
    c["sohRead"] = v.get("read_at") or (e.at.date().isoformat() if e is not None and v.get("soh_pct") is not None else None)
    c["damaged"] = bool(v.get("damaged", c.get("damaged", False)))
    return c


def valuer_case(
    base: Mapping[str, Any], evidence: Mapping[str, Evidence | None], now: datetime | None = None,
    rul_model: RulModel | None = None,
) -> dict[str, Any]:  # fmt: skip
    """`base` (the valuer case as opened) with `grade` the workbench grade, or None with `estGrade` the estimate; and, when
    the evidence gives a life result (`life_of`), `rul` and `partRul` computed (each part by its component's name, else the
    tool's remaining life) and `life` the result as a dict. `now` is the time the age of the telematics is read at."""
    c = copy.deepcopy(dict(base))
    est = str(c.get("estGrade") or c.get("grade") or "C")
    g = grade_of(evidence, est)
    c["estGrade"] = est
    c["grade"] = g.grade if g.source == "workbench" else None
    life = life_of(evidence, str(c.get("cls") or ""), now, rul_model)
    if life is not None:
        by = {x.name: x.rul_pct for x in life.per_component}
        parts = tool_fleet.CLS[c["cls"]]["parts"]
        c["rul"] = life.rul_tool
        c["partRul"] = [by.get(pn, life.rul_tool) for pn, _pv in parts]
        c["life"] = dataclasses.asdict(life) | {"range": list(life.range) if life.range else None}  # as JSON keeps it
    return c
