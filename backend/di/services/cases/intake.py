"""Opening a case from data (plan 8, MVP-8.1): a return, lease end, trade-in, contract end or IoT alarm arrives, and a
case opens for it, beside the demo's 128 book cases (di.services.cases.store).

    open_case(s, {org_unit_id, template_key, asset_key, reason, facts?, by?}, actor) -> Case

- **Id.** The next RT-<n> above the highest, under a transaction lock so two intakes never take the same number.
- **Owner and template.** The case belongs to the org unit (`owner`, what the tenant boundary reads) and keeps its
  template key (`template`; the book's cases have none and are `industrial`).
- **Base fields.** `facts` first, then the canonical store for the asset key (asset and condition models): class,
  grade, age, quantity, spec, demand, location. The stage is the first of di.services.cases.lifecycle ("none")
  until it is valued; with a recommendation it is `awaiting_approval`, as a re-evaluation leaves it.
- **Routes.** `industrial`: the engine's seven routes (`build_routes`) valued by the formulas on a random source
  seeded from the case id (a stable hash: sha256, never Python's per-process `hash()`), calibrated by the template's
  active model if one was promoted (di.services.actions.models.intake_predictor, MVP-12.2); when the asset's bom_ref
  names an assembly PLM holds, its parts are valued from that BOM and the demand for them (BomPartsPredictor,
  MVP-9.4). Other templates: the
  template's valuer (tool fleet, device) through `to_routes`. Then the business rules of the owner's published flow
  (di.repositories.live_rules), and `rank_routes` gives the recommendation.
- **Dedupe** (Review Focus 5). The same asset key and reason open one case: a second intake (a webhook replay, a
  re-sync, an import read twice) is refused with `duplicate`. The action's idempotency key is the same pair.
- **Record.** A stage log row "Case opened from <reason>" and a domain event `case.opened`.

The case reads (live rules, the active model, PLM) sit above the case store; this is the one place a case is opened from
data, so it reads them here (backend/.importlinter names these imports).
"""

import copy
import dataclasses
import hashlib
import json
from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from di.core import clock, jobs
from di.core.config import get_settings
from di.repositories import plm
from di.repositories.live_rules import live_rules
from di.services.actions.models import intake_predictor
from di.services.actions.registry import ActionError
from di.services.canonical import store as canonical
from di.services.cases import store
from di.services.cases.lifecycle import STAGES
from di.services.engine.evaluate import apply_business, build_routes
from di.services.engine.predictor import CLASSES, GRADE_F, BomPartsPredictor, FormulaPredictor, Predictor
from di.services.engine.routes import Route, rank_routes
from di.services.modeler.templates import TEMPLATE_KEYS, Template
from di.services.modeler.valuers import device, tool_fleet
from di.services.modeler.valuers.rng import mulberry32
from di.services.modeler.valuers.routes_adapter import to_routes

REASONS = ("rma", "lease_end", "trade_in", "contract_end", "iot_alarm", "manual")
LOCATION = "Warehouse 1"  # where a returned asset is received when no source says otherwise
# the sources' asset types (asset.asset_type, any case) that name an engine class otherwise than by its key
_CLASS_OF = {"tool": "drill", "iteq": "it", "toolflt": "batch", "battery": "batch"}
_EMPTY_DEMAND = {"confirmed": False, "internal": False, "lease": None, "parts": False, "site": None}


def intake_key(asset_key: str, reason: str) -> str:
    """The dedupe key: one case per asset and reason (also the action's idempotency key)."""
    return f"{asset_key}:{reason}"


def seed_of(case_id: str) -> int:
    """The case's random seed: the first 32 bits of the id's sha256 (the same in every process)."""
    return int(hashlib.sha256(case_id.encode()).hexdigest()[:8], 16)


# ---------------------------------------------------------------- checks
def problem(s: Session, i: dict[str, Any]) -> tuple[str, str] | None:
    """Why the intake cannot open a case (code, message), or None."""
    if i.get("reason") not in REASONS:
        return "validation_error", f"The reason is one of {', '.join(REASONS)}."
    if i.get("template_key") not in TEMPLATE_KEYS:
        return "validation_error", f"The template is one of {', '.join(TEMPLATE_KEYS)}."
    if not str(i.get("asset_key") or "").strip():
        return "validation_error", "Give the asset key the case is opened for."
    if s.execute(text("SELECT 1 FROM org_unit WHERE id = :i"), {"i": i.get("org_unit_id")}).first() is None:
        return "not_found", f"No org unit {i.get('org_unit_id')}."
    return None


def existing(s: Session, asset_key: str, reason: str) -> str | None:
    """The case already opened for this asset and reason, if any."""
    row = s.execute(
        text("SELECT id FROM case_record WHERE data->'intake'->>'key' = :k ORDER BY id LIMIT 1"),
        {"k": intake_key(asset_key, reason)},
    ).first()
    return row[0] if row else None


# ---------------------------------------------------------------- base fields
def _canonical(s: Session, asset_key: str) -> dict[str, Any]:
    """What the canonical store holds for the asset: its asset and condition fields, mapped to the case's."""
    asset = (canonical.get(s, "asset", asset_key) or {}).get("data") or {}
    cond = (canonical.get(s, "condition", asset_key) or {}).get("data") or {}
    out: dict[str, Any] = {}
    kind = str(asset.get("asset_type") or "").lower()
    if (cls := _CLASS_OF.get(kind, kind)) in CLASSES:
        out["cls"] = cls
    if cond.get("grade") in GRADE_F:
        out["grade"] = cond["grade"]
    if isinstance(asset.get("qty"), int | float) and asset["qty"] > 0:
        out["qty"] = int(asset["qty"])
    if asset.get("location"):
        out["location"] = asset["location"]
    if asset.get("manufacturer"):
        out["mfr"] = asset["manufacturer"]
    if asset.get("model"):
        out["product"] = asset["model"]
    if asset.get("bom_ref"):
        out["bom_ref"] = asset["bom_ref"]
    if isinstance(asset.get("nameplate"), dict):
        out["spec"] = asset["nameplate"]
    if isinstance(asset.get("install_date"), str):
        try:
            installed = date.fromisoformat(asset["install_date"][:10])
            out["age"] = round((clock.now().date() - installed).days / 365.25, 1)
        except ValueError:
            pass
    return out


def _received(now: datetime) -> str:
    return now.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _base(case_id: str, i: dict[str, Any], known: dict[str, Any], by: str) -> store.Case:
    """The case record before valuation, in the book's shape (the fields every case page reads)."""
    now = clock.now()
    return {
        "id": case_id, "owner": i["org_unit_id"], "location": known.get("location") or LOCATION, "stage": STAGES[0],
        "template": i["template_key"], "assetId": i["asset_key"], "cls": known.get("cls"), "grade": known.get("grade"),
        "age": known.get("age", 0), "qty": known.get("qty", 1), "spec": known.get("spec") or {},
        "demand": known.get("demand") or dict(_EMPTY_DEMAND), "product": known.get("product") or "",
        "mfr": known.get("mfr") or "", "received": known.get("received") or _received(now), "kind": "standard",
        "hero": False, "readiness": "ready", "evidence": [], "notes": [], "approval": None, "exec": None,
        "override": None, "blocked": None, "facts": None, "predictions": None, "timeline": None,
        "condition": known.get("condition") or "", "assessment": None, "engLife": "Not assessed",
        "nextInspection": "—", "model": FormulaPredictor.model_version, "bomRef": known.get("bom_ref"),
        "snapshot": {"id": "EVS-" + hashlib.sha256(case_id.encode()).hexdigest()[:8].upper(), "items": 0,
                     "takenAt": _received(now)},
        "intake": {"key": intake_key(i["asset_key"], i["reason"]), "reason": i["reason"], "by": by,
                   "at": now.astimezone(UTC).isoformat()},
    }  # fmt: skip


# ---------------------------------------------------------------- valuation
def tool_fleet_case(case_id: str, facts: dict[str, Any]) -> dict[str, Any]:
    """The tool-fleet valuer's case (the prototype's mkCase shape) from the facts; what the facts leave out takes the
    prototype's defaults for a fresh return (no named orders, every part at the tool's remaining life)."""
    cls = facts.get("cls")
    if cls not in tool_fleet.CLS:
        raise ActionError("validation_error", f"A tool fleet case needs a tool class, one of {', '.join(tool_fleet.CK)}.")
    grade = facts.get("grade") or "C"
    if grade not in GRADE_F:
        raise ActionError("validation_error", "The grade is one of A, B, C, D.")
    for k, allowed in (("ft", tool_fleet.FUNCS), ("site", tool_fleet.SITES)):
        if facts.get(k) is not None and facts[k] not in allowed:
            raise ActionError("validation_error", f"A tool fleet case's {k} is one of {', '.join(allowed)}.")
    if facts.get("rul") is not None and (not isinstance(facts["rul"], int | float) or isinstance(facts["rul"], bool)):
        raise ActionError("validation_error", "A tool fleet case's remaining life (rul) is a number of months.")
    rul = facts.get("rul") or (75 if grade == "A" else 60 if grade == "B" else 46 if grade == "C" else 28)
    c: dict[str, Any] = {
        "id": case_id, "cls": cls, "ft": tool_fleet.FUNCS[0], "site": tool_fleet.SITES[0], "grade": grade,
        "estGrade": grade, "rul": rul, "serial": "", "age": 12, "days": 1,
        "partRul": [rul for _ in tool_fleet.CLS[cls]["parts"]], "status": "new", "log": [],
    }  # fmt: skip
    c |= {k: v for k, v in facts.items() if k in c and k not in ("id", "status", "log")}
    dem = dict(facts.get("dem") or {})  # named orders the facts give; a part without repair orders has none
    c["dem"] = {"lease": [], "so": [], "bid": [], "proj": None, "rcq": ""} | dem
    c["dem"]["wo"] = {pn: [] for pn, _ in tool_fleet.CLS[cls]["parts"]} | (dem.get("wo") or {})
    c["src"] = tool_fleet.SOURCES.get(c["ft"], "")
    return c


def device_lot(case_id: str, facts: dict[str, Any]) -> dict[str, Any]:
    """The device valuer's lot from the facts: brand, model, age band, grade, reference value, units, days on hand."""
    grade, band = facts.get("grade"), facts.get("band")
    if grade not in device.DST or band not in device.DST[grade]:
        raise ActionError("validation_error", "A device lot needs a grade (A-D) and an age band (0-24m, 25-48m, 49m+).")
    if not isinstance(facts.get("ref"), int | float) or not isinstance(facts.get("qty"), int) or facts["qty"] < 1:
        raise ActionError("validation_error", "A device lot needs a reference value (ref) and a number of units (qty).")
    return {
        "id": case_id, "brand": facts.get("brand") or "", "model": facts.get("model") or "", "band": band,
        "grade": grade, "ref": facts["ref"], "qty": facts["qty"], "doh": facts.get("doh") or 1,
    }  # fmt: skip


def _industrial_routes(s: Session, c: store.Case, t: Template, rules: list) -> list[Route]:
    if c["cls"] not in CLASSES:
        raise ActionError("validation_error", f"An industrial case needs an asset class, one of {', '.join(CLASSES)}.")
    if c.get("grade") is not None and c["grade"] not in GRADE_F:
        raise ActionError("validation_error", "The grade is one of A, B, C, D.")
    p = intake_predictor(s, FormulaPredictor(mulberry32(seed_of(c["id"]))), c["cls"])
    return build_routes(c, _with_bom(s, c, p), rules, t)


def _with_bom(s: Session, c: store.Case, p: Predictor) -> Predictor:
    """The parts value from the asset's BOM (plan 8, MVP-9.4) when PLM holds the assembly its bom_ref names: the
    owner's PLM data first, else the shared; otherwise the predictor as it is."""
    ref = str(c.get("bomRef") or "")
    for org in (c["owner"], None) if ref else ():
        if lines := plm.bom_lines(s, org, ref):
            return BomPartsPredictor(p, lines, plm.demand(s, org, [x.part for x in lines]))
    return p


def _template_routes(c: store.Case, facts: dict[str, Any], t: Template, rules: list) -> tuple[list[Route], str | None]:
    if t.key == "tool_fleet":
        vc = tool_fleet_case(c["id"], facts)
        c |= {k: vc[k] for k in ("cls", "ft", "site", "grade", "rul", "partRul", "dem")} | {"valuer": vc}
        c["product"] = c["product"] or tool_fleet.CLS[vc["cls"]]["name"]
    else:
        lot = device_lot(c["id"], facts)
        c |= {k: lot[k] for k in ("brand", "band", "grade", "ref", "doh")} | {"qty": lot["qty"], "cls": "device"}
        c |= {"valuer": lot}
        c["product"] = c["product"] or f"{lot['brand']} {lot['model']}".strip()
    return template_routes(c, t, rules)


def valuer_input(c: Mapping[str, Any], template_key: str) -> dict[str, Any]:
    """What the template's valuer decides a case on: the snapshot taken when it opened (`valuer`), else rebuilt from
    the case's own fields (a case opened before the snapshot was kept)."""
    if isinstance(c.get("valuer"), dict):
        return copy.deepcopy(c["valuer"])
    facts = dict(c)
    return tool_fleet_case(c["id"], facts) if template_key == "tool_fleet" else device_lot(c["id"], facts | {"model": ""})


def template_decide(template_key: str, v: dict[str, Any], rules: Sequence[Any]) -> dict[str, Any]:
    """The template's valuer on one case, with the flow's compiled rules (audit F1, F6): the tool fleet decides the
    return in a queue of its own (no sample orders), the device lot alone. The simulation ranks open cases the same way
    (di.services.actions.modeler_sim), so a case's recommendation is what the Modeler predicts for it."""
    rd = [dataclasses.asdict(r) if dataclasses.is_dataclass(r) and not isinstance(r, type) else dict(r) for r in rules]
    if template_key == "tool_fleet":
        return dict(tool_fleet.decide(dict(v), rules=rd, queue=[v]))
    return dict(device.decide(dict(v), rd))


def template_routes(c: store.Case, t: Template, rules: list) -> tuple[list[Route], str | None]:
    """The case's routes from its template's valuer, with the business rules recorded on the case, and the path the
    valuer chose (it ranks first; the device valuer's "prefer" wins only within 15% of the best). The routes keep only
    the valuer's own exclusions: the business rules are applied to them as to an industrial case, so an excluded path
    says which rule excluded it and `rulesApplied` lists the rule (the valuer's run with the rules gives the values and
    the chosen path)."""
    v = valuer_input(c, t.key)
    dec = template_decide(t.key, v, rules)
    own = {x["k"]: x for x in template_decide(t.key, v, [])["all"]}  # what the valuer alone leaves out, and why
    routes = to_routes(t, [x | {"ok": own[x["k"]]["ok"], "why": own[x["k"]]["why"]} for x in dec["all"]])
    for r in routes:  # what the case pages read of a route: who takes it, through which application
        p = t.path(r["id"])
        r |= {"demandLabel": f"{p.owner} · {p.app}" if p else r["plan"], "demandStatus": "forecast", "unc": ""}
    apply_business(c, routes, rules, t)
    best = dec.get("best")
    return routes, best["k"] if best else None


def _rank(c: store.Case, routes: list[Route], best: str | None) -> Route | None:
    """The recommendation: the valuer's chosen path when it is still eligible, else the ranking (a rule's preference
    first)."""
    eligible = {r["id"] for r in routes if not r["excluded"]}
    return rank_routes(routes, c.get("blocked"), best if best in eligible else c.get("preferred"))


def recommend(s: Session, c: store.Case, rules: list) -> Route | None:
    """What a template case would be recommended under other rules (a flow's draft in shadow, MVP-3.5), from the
    snapshot it opened with, on a copy: the case itself is unchanged."""
    t = live_rules(s, c)[0]
    probe = copy.deepcopy(c)
    routes, best = template_routes(probe, t, rules)
    return _rank(probe, routes, best)


def revalue(s: Session, c: store.Case) -> None:
    """A template case valued again (case.reevaluate): its valuer and the owner's published rules, as at opening. The
    stage is the caller's to move."""
    stage = c["stage"]
    _value(s, c, {})
    c["stage"] = stage


def _value(s: Session, c: store.Case, facts: dict[str, Any]) -> None:
    """Routes, recommendation and the flow version they were evaluated with (as a re-evaluation records them)."""
    t, rules, ver = live_rules(s, c)
    if t.key == "industrial":
        routes, best = _industrial_routes(s, c, t, rules), None
    elif facts or not c.get("routes"):
        routes, best = _template_routes(c, facts, t, rules)
    else:  # a re-evaluation: the snapshot the case opened with
        routes, best = template_routes(c, t, rules)
    c["routes"] = routes
    c["recommendation"] = _rank(c, routes, best)
    c["flowVer"] = ver
    # a recommendation waits for approval, as after a re-evaluation (decision.reevaluate); none: no decision yet
    c["stage"] = "awaiting_approval" if c["recommendation"] else STAGES[0]
    if not (c.get("rulesApplied") or c.get("rulesWaived") or c.get("preferred")):
        for k in ("rulesApplied", "rulesWaived", "preferred"):
            c.pop(k, None)


# ---------------------------------------------------------------- open
def _next_id(s: Session) -> str:
    top = s.execute(text("SELECT max(CAST(substring(id FROM 4) AS integer)) FROM case_record WHERE id ~ '^RT-[0-9]+$'")).scalar()
    return f"RT-{(top or 1000) + 1}"


def open_case(s: Session, i: dict[str, Any], actor: str, *, account_id: str | None = None) -> store.Case:
    """Open a case for the input (see the module docstring) and return it; ActionError when refused (a duplicate
    included). `actor` is who opens it (a person's name, or "system" for a workflow or an import, whose `by` names
    who set that up). `account_id` is the person's account when one opens it (P9-0.9): with DI_AUTOPILOT_ON_OPEN the case
    autopilot then starts for it (an `agent.autostart` job). In the caller's transaction."""
    store.ensure(s)
    if bad := problem(s, i):
        raise ActionError(*bad)
    s.execute(text("SELECT pg_advisory_xact_lock(1049)"))  # one intake at a time (api, worker): one case, one number
    if dup := existing(s, i["asset_key"], i["reason"]):
        raise ActionError("duplicate", f"{dup} is already open for {i['asset_key']} ({i['reason']}).")
    facts = dict(i.get("facts") or {})
    known = _canonical(s, i["asset_key"]) | facts
    case_id = _next_id(s)
    c = _base(case_id, i, known, i.get("by") or actor)
    _value(s, c, facts)
    store.insert_new(s, c, f"Case opened from {i['reason']}", actor)
    payload = {"case_id": case_id, "owner": c["owner"], "template": c["template"], "asset_key": i["asset_key"],
               "reason": i["reason"], "by": c["intake"]["by"]}  # fmt: skip
    s.execute(
        text("INSERT INTO domain_event (type, case_id, payload) VALUES ('case.opened', :c, CAST(:p AS jsonb))"),
        {"c": case_id, "p": json.dumps(payload)},
    )
    if get_settings().autopilot_on_open:
        jobs.enqueue(s, "agent.autostart", {"case_id": case_id, "account": account_id}, dedupe_key=f"agent.autostart:{case_id}")
    return c
