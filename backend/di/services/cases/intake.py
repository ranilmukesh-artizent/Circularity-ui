"""Opening a case from data (plan 8, MVP-8.1): a return, lease end, trade-in, contract end or IoT alarm arrives, and a
case opens for it, beside the demo's 128 book cases (di.services.cases.store).

    open_case(s, {org_unit_id, template_key, asset_key, reason, facts?, by?}, actor) -> Case

- **Id.** The next RT-<n> above the highest, under a transaction lock so two intakes never take the same number.
- **Owner and template.** The case belongs to the org unit (`owner`, what the tenant boundary reads) and keeps its
  template key (`template`; the book's cases have none and are `industrial`).
- **Base fields.** `facts` first, then the canonical store for the asset key (asset and condition models): class,
  grade, age, quantity, spec, demand, location. The stage is the first of di.services.cases.lifecycle ("none")
  until it is valued; with a recommendation it is `awaiting_approval`, as a re-evaluation leaves it.
- **Routes** (plan 9, P9-1.5). The one decider, `decide_case` (di.services.cases.decide, R19), decides the case with its
  pack (the template's pack and the owner's published customer overlay) and the owner's published flow
  (di.repositories.live_rules), in the order of R20; `decide.write_back` sets the result on the case. `industrial`: the
  engine's seven routes valued by the formulas on a random source seeded from the case id (a stable hash: sha256, never
  Python's per-process `hash()`), calibrated by the template's active model if one was promoted
  (di.services.actions.models.intake_predictor, MVP-12.2); when the asset's bom_ref names an assembly PLM holds, its
  parts are valued from that BOM and the demand for them (BomPartsPredictor, MVP-9.4): `industrial_predictor` builds it.
  Other templates: the template's valuer (tool fleet, device); this module keeps the valuer's input (`valuer`, from the
  facts) and the queue loading (`tool_queue`).
- **Queue plan** (plan 9, P9-1.4). A tool-fleet case is planned within its org's open tool-fleet cases (not closed;
  an approved or executing one keeps its order) with the named demand of the canonical store, through the pack's
  queue planner (di.services.engine.queue); `open_case` then queues `case.replan` so the org's other open cases are
  planned again (di.services.cases.replan). The named demand is the tagged canonical orders and, since P9-3.12 (TF-07),
  the live demand of the org's `fleet` and `parts` sources (di.repositories.tool_demand): the tool fleet no longer decides
  "in a queue of its own (no sample orders)".
- **Gates** (plan 9, P9-1.2). A template case carries the asset's compliance records (`evidenceRecords`); the pack's
  gates are evaluated and applied to the routes before the business rules (inside `decide_case`), and a gate that holds
  leaves the case at stage `none` with `gateHold` until the evidence arrives (di.services.cases.gate_hold).
  `facts.batch` is kept as `batchRef`.
- **System of record and custody** (plan 9, P9-1.10). A template case is matched to its pack's system of record when it
  opens and on every re-check (di.services.cases.record_match): `recordMatch`, an exception item when the asset is not
  there, and `custody` (received on open, matched, moved, released when a gate hold clears), append-only.
- **Dedupe** (Review Focus 5). The same asset key and reason open one case: a second intake (a webhook replay, a
  re-sync, an import read twice) is refused with `duplicate`. The action's idempotency key is the same pair.
- **Tool returns** (plan 9, P9-3.4). The contract feed's returns open tool-fleet cases with the reasons `contract_end`,
  `swap`, `service_order`, `pool_excess` (`RETURN_FT`): `tool_return_facts` gives the case `cls`, `serial`, `ft`, `flow`
  `returns`, with `contract_id` and `line_id` kept on the case. The same serial with another reason is another case.
- **Workbench grade** (plan 9, P9-3.5). A tool-fleet case's valuer reads the repair log's graded `condition` of the serial
  when it has a test result (`regrade.apply`, on opening and on every re-check); otherwise its own estimate, labelled so.
- **Received devices** (plan 9, P9-6.4). A `trade_in` device intake with an `imei` (and no `ref`) is built by
  `di.services.device.intake.device_case` from the trade-in on file: the feed price as the reference value, the cosmetic
  grade when graded; the valuer snapshot keeps the IMEI, quote, partner and the gathered inputs (`device.inputs`). The lab
  adapter's hook (`device.intake.open_from_tradein`) calls this `open_case`; a bulk batch comes as a PO-shaped lot.
- **Service ticket** (plan 9, P9-4.3). The reason `service_ticket` opens one case per service ticket or batch
  (`di.services.service_desk.intake.open_from_ticket`): `facts` the flow `service_desk` and `serviceDesk` (the ticket and its
  lines, kept as `serviceDesk`), with the class, serial and age of the worst line for the valuer.
- **Contract refresh** (plan 9, P9-5.1). The reason `contract_refresh` opens a refresh case for a contract (asset key the
  contract id, `facts` the flow `contract_refresh`, `term_end`, `market`, `lines`: kept as `refresh`); `dedupe_as` names
  the dedupe key's asset (`<contractId>@<endDate>`, once per term). It is valued by no valuer yet (no routes, stage
  `none`), has no system-of-record match and stays out of the tool queue.
- **One case per car** (plan 9, P9-9.7, UC-05, UC-09). A `used_cars` case is keyed by the car (`asset_key` is
  `schema.vin_key(org, vin)`, the reasons `lease_end` and `trade_in`). Its facts (`vin`, `mileage`, `return_date`,
  `source`) are kept as the list `vehicle.facts` ({fact, value, source, at, ageDays}), each with its source and age
  (the canonical provenance of the event's source
  when it wrote the field, else the event's own source and time). A second event for the same car, whatever its reason,
  joins the open case under the intake lock: it adds its facts with its own source and age, is listed in
  `intake.joined` (so a replay of it is a `duplicate`) and values the case again; no second case. The grade is the
  inspection read, never computed here: `condition.read_grade` (the pack's grade mapping) makes the `grade` evidence
  record, kept in `vehicle.inspection` with its source and age; without a complete inspection it is an estimate with
  confidence 0.70, which holds the decision for `confidence`.
- **One case per tag** (plan 9, P9-11.6, MR-04). The same mechanism, as the `OneCase` profile of the template (`ONE_CASE`):
  a `medical_rental` case is keyed by the device (`asset_key` is `schema.tag_key(org, tag)`, the reason `rental_return`).
  Its facts (`tag`, `hospital`, `depot`, `checked_in_at`, `source`; the canonical `asset` gives the ones the event leaves
  out, and the minimum facts `asset_tag` and `return_date` come from them) are kept as the list `rental.facts`, each with
  its source and age. A second event for the same tag joins the open case under the intake lock, as for a car. The
  The device facts the valuer prices on (`cls`, `age_years`, `book_value`, `residual_sale_value`, `repair_estimate`) come
  from the canonical `asset`, `market` and `intervention` records the same way (P9-11.10), an event's own facts winning. The
  decontamination gate G-MED-DECON reads the device's record (`di.services.cases.decon_evidence`) and holds the case.
- **One case per serial** (plan 9, P9-10.6, TN-04). A `telecom_network` case is keyed by the unit (`asset_key` is
  `schema.serial_key(org, serial)`, the reason `decommission`, one event per unit of a removal job). Its facts (`serial`,
  `model`, `site`, `removed_at`, `removal_job`, `programme`, `source`) are kept in `network.facts` with their source and
  age, as for a car; the removal `site` and `model` are also `network.site` and `network.model`, which the inventory match
  gate G-NET-INV compares with the inventory (`di.services.cases.inventory_evidence`). A second event for the serial joins
  the open case (`intake.joined`), whatever its reason.
- **Battery packs** (plan 9, P9-12.7, NS-BAT-01). A `battery` case (reason `pack_replacement`, asset key `schema.serial_key(org,
  pack id)`) keeps `battery`, the facts its G-BAT gates read (`battery_facts`: the opening facts, over which the BMS's canonical
  read wins; `gate_checks.battery.case_view`). A used car whose battery assessment result is `pack_replacement_needed` opens one
  for the pack the BMS names for its VIN (`open_battery_case`, on opening and on every re-evaluation): `linked_case` on the pack's
  case is the car's, `linked` on the car's lists it.
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
from di.repositories import plm, tool_demand
from di.repositories.live_rules import flow_version, live_pack
from di.repositories.packs import active_pack, published_keys, published_pack
from di.services.actions.models import intake_predictor
from di.services.actions.registry import ActionError
from di.services.canonical import store as canonical
from di.services.cases import (
    approval_hold,
    battery_wait,
    cpe_lot,
    decide,
    gate_hold,
    named_demand,
    record_match,
    regrade,
    store,
)
from di.services.cases.lifecycle import STAGES
from di.services.device import inputs as device_inputs
from di.services.device import intake as device_intake
from di.services.device import lock as device_lock
from di.services.device import payout as device_payout
from di.services.device import verify as device_verify
from di.services.device import wipe as device_wipe
from di.services.engine.jsmath import js_round
from di.services.engine.predictor import CLASSES, GRADE_F, BomPartsPredictor, FormulaPredictor, Predictor
from di.services.engine.queue import Capacity, Dem, planner_for
from di.services.engine.routes import Route
from di.services.modeler.compile import FlowVersion
from di.services.modeler.evidence import parse_time
from di.services.modeler.gate_checks import battery as battery_gates
from di.services.modeler.pack import Pack, load_pack
from di.services.modeler.templates import TEMPLATE_KEYS
from di.services.modeler.valuers import amount, battery, device, tool_fleet, tool_inputs
from di.services.modeler.valuers.rng import mulberry32

REASONS = ("rma", "lease_end", "trade_in", "contract_end", "iot_alarm", "manual", "swap", "service_order", "pool_excess",
           "contract_refresh", "service_ticket", "rental_return", "pack_replacement")  # fmt: skip
REFRESH_FLOW = "contract_refresh"  # the flow of a refresh case (P9-5.1): opened for a contract, not valued as a return


def is_refresh(c: Mapping[str, Any]) -> bool:
    """Whether the case is a contract refresh (P9-5.1): it has no tool class and no route yet."""
    return c.get("flow") == REFRESH_FLOW


# the tool fleet's return kinds (P9-3.4) and the function each goes to: also the reasons of the contract feed's returns
RETURN_FT = {"contract_end": "Fleet management", "swap": "Fleet management", "service_order": "Repair center",
             "pool_excess": "Tool pool"}  # fmt: skip
SERIAL_PACK = "b2c_serial"  # the pack that refuses an item without a serial (P9-12.10)
IMPORTED_VALUERS = ("tool_fleet", "device", "standard")  # valuers an imported pack (a key beyond TEMPLATE_KEYS) may use
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
    if i.get("reason") not in (*REASONS, *UNIT_REASONS):
        return "validation_error", f"The reason is one of {', '.join((*REASONS, *UNIT_REASONS))}."
    key = i.get("template_key")
    imported = published_keys(s)
    if key not in TEMPLATE_KEYS and key not in imported:
        return "validation_error", f"The template is one of {', '.join([*TEMPLATE_KEYS, *sorted(imported)])}."
    if key not in TEMPLATE_KEYS and active_pack(s, str(key), i.get("org_unit_id")).valuer.kind not in IMPORTED_VALUERS:
        return "validation_error", f"The pack {key} needs a valuer of one of these kinds: {', '.join(IMPORTED_VALUERS)}."
    if not str(i.get("asset_key") or "").strip():
        return "validation_error", "Give the asset key the case is opened for."
    if key == SERIAL_PACK and not any(str((i.get("facts") or {}).get(k) or "").strip() for k in ("serial", "imei")):
        return "not_serialised", "Only serialised items enter this pack: give the item's serial or IMEI."
    if s.execute(text("SELECT 1 FROM org_unit WHERE id = :i"), {"i": i.get("org_unit_id")}).first() is None:
        return "not_found", f"No org unit {i.get('org_unit_id')}."
    return None


def missing_fields(s: Session, i: dict[str, Any], known: Mapping[str, Any]) -> list[str]:
    """The `data.min_fields` of a standard pack that the facts (with what the canonical record knows) leave out (P9-1.9)."""
    key = str(i["template_key"])
    if key in TEMPLATE_KEYS:
        return []
    pack = active_pack(s, key, i.get("org_unit_id"))
    if pack.valuer.kind != "standard":
        return []
    return [f for f in pack.data.min_fields if amount.lookup(known, f) is None]


def tool_return_facts(facts: Mapping[str, Any], asset_key: str, reason: str) -> dict[str, Any]:
    """A tool return's facts (P9-3.4) in the case's names: `cls` from `tool_class`, the serial (the asset key), `ft` from
    the reason (what the facts give wins), and `flow` `returns`. Other reasons (manual ...) keep their facts as given."""
    f = dict(facts)
    if reason not in RETURN_FT:
        return f
    if "tool_class" in f:
        f.setdefault("cls", f.pop("tool_class"))
    return {"ft": RETURN_FT[reason], "serial": asset_key, "flow": "returns"} | f


def existing(s: Session, asset_key: str, reason: str) -> str | None:
    """The case already opened for this asset and reason, if any (or one a later event for the car joined, P9-9.7)."""
    k = intake_key(asset_key, reason)
    row = s.execute(
        text(
            "SELECT id FROM case_record WHERE data->'intake'->>'key' = :k "
            "OR data->'intake'->'joined' @> CAST(:j AS jsonb) ORDER BY id LIMIT 1"
        ),
        {"k": k, "j": json.dumps([{"key": k}])},
    ).first()
    return row[0] if row else None


# ---------------------------------------------------------------- one case per physical asset (P9-9.7, P9-11.6)
@dataclasses.dataclass(frozen=True)
class OneCase:
    """A template whose open case is keyed by the asset itself (a car by its VIN, a rental device by its tag): `group` is the
    case field that keeps the asset's id (`id_fact`) and its `facts`; `sources` the source an event's facts come from by
    reason; `fields` maps a fact to the canonical `asset` field that gives its source and age; `derived` fills facts the
    canonical record implies (the pack's minimum facts)."""

    group: str
    id_fact: str
    sources: Mapping[str, str]
    fields: Mapping[str, str]
    # fact -> the fact it is copied from (a `*date` fact keeps the first 10 characters)
    derived: Mapping[str, str] = dataclasses.field(default_factory=dict)
    # fact -> (canonical model, field) for a fact the asset's other records hold (a device's `residual_sale_value` on `market`,
    # `repair_estimate` on `intervention`; P9-11.10)
    other: Mapping[str, tuple[str, str]] = dataclasses.field(default_factory=dict)


CAR_TEMPLATE = "used_cars"
BATTERY_TEMPLATE = "battery"  # the battery pack's cases (P9-12.7)
APPROVAL_PACKS = (CAR_TEMPLATE, "telecom_network", "medical_rental")  # the packs whose decisions can hold for an approval item
RENTAL_TEMPLATE = "medical_rental"
ONE_CASE = {
    CAR_TEMPLATE: OneCase(
        "vehicle", "vin", {"lease_end": "uc_lease", "trade_in": "uc_dms"}, {"vin": "vin", "mileage": "mileage_at_return"}
    ),
    RENTAL_TEMPLATE: OneCase(
        "rental", "tag", {"rental_return": "mr_rental"},
        {"tag": "tag", "hospital": "hospital", "depot": "depot", "checked_in_at": "checked_in_at", "cls": "device_class",
         "age_years": "age_years", "book_value": "book_value"},
        {"asset_tag": "tag", "return_date": "checked_in_at"},
        {"residual_sale_value": ("market", "residual_sale_value"), "repair_estimate": ("intervention", "repair_estimate")},
    ),
}  # fmt: skip
CAR_SOURCE = ONE_CASE[CAR_TEMPLATE].sources
CAR_FIELDS = ONE_CASE[CAR_TEMPLATE].fields
OPEN_STAGES = ("none", "awaiting_approval")  # a joined event values the case again only while no one has acted on it


def _newest(rec: Mapping[str, Any] | None, field: str, source: str) -> datetime | None:
    """The time `source` last wrote the field of the canonical record, or None."""
    rows = [r for r in ((rec or {}).get("provenance") or {}).get(field) or [] if r["source_id"] == source]
    return max(r["fetched_at"] for r in rows) if rows else None


def one_known(s: Session, p: OneCase, key: str) -> dict[str, Any]:
    """The facts the canonical `asset` of the car or device holds (a car's `vin`, `mileage`; a device's `tag`, `hospital`,
    `depot`, `checked_in_at`), and the facts the profile derives from them."""
    data = (canonical.get(s, "asset", key) or {}).get("data") or {}
    out = {n: data[f] for n, f in p.fields.items() if data.get(f) is not None}
    for n, (model, f) in p.other.items():
        if (v := ((canonical.get(s, model, key) or {}).get("data") or {}).get(f)) is not None:
            out[n] = v
    for n, src in p.derived.items():
        if out.get(src) is not None:
            out[n] = str(out[src])[:10] if n.endswith("date") else out[src]
    return out


def one_event(i: Mapping[str, Any], facts: Mapping[str, Any], p: OneCase) -> tuple[str, datetime]:
    """The source and time of an event for the asset: what the input names, else the reason's source and now."""
    at = parse_time(i.get("at")) or clock.now()
    return str(i.get("source") or facts.get("source") or p.sources.get(i["reason"], "")), at


def _age_days(at: datetime) -> float:
    return round(max(0.0, (clock.now() - at).total_seconds()) / 86400, 1)


def one_facts(s: Session, p: OneCase, key: str, facts: Mapping[str, Any], source: str, at: datetime) -> list[dict[str, Any]]:
    """Each fact with its source and age (in days, at the clock): when the event's source wrote the fact's canonical field,
    that write's time; else the event's."""
    asset = canonical.get(s, "asset", key)
    out: list[dict[str, Any]] = []
    for name, value in facts.items():
        when = (_newest(asset, p.fields[name], source) if name in p.fields else None) or at
        out.append({"fact": name, "value": value, "source": source, "at": when.isoformat(), "ageDays": _age_days(when)})
    return out


def car_read(s: Session, c: store.Case, pack: Pack) -> None:
    """The inspection read of a car as the case's `grade` evidence (the stage `condition` reads it): the canonical
    `condition` record's score, status and time with the inspection source, through the pack's grade mapping
    (`condition.read_grade`). Sets `vehicle.inspection` and the case's `grade`; the case's `evidenceRecords` gain the
    record. Run on opening and on every valuation, so a late inspection reaches the case on its re-evaluation."""
    from di.services.agents.stages import condition  # the agents' stage owns the mapping; imported late (no cycle)

    rec = canonical.get(s, "condition", str(c["assetId"]))
    data = (rec or {}).get("data") or {}
    insp: dict[str, Any] | None = None
    if rec is not None and data.get("inspection_status") is not None:
        rows = rec["provenance"].get("inspection_status") or []
        src = max(rows, key=lambda r: r["fetched_at"])["source_id"] if rows else ""
        at = parse_time(data.get("inspection_at")) or (_newest(rec, "inspection_status", src) if src else None)
        insp = {"status": data["inspection_status"], "score": data.get("condition_score"),
                "at": at.isoformat() if at else None, "source": src}  # fmt: skip
    vehicle = c.setdefault("vehicle", {"vin": amount.lookup(c.get("valuer") or {}, "vin"), "facts": []})
    mileage = next((f["value"] for f in reversed(vehicle["facts"]) if f["fact"] == "mileage"), None) or amount.lookup(
        c.get("valuer") or {}, "mileage"
    )
    grade = condition.read_grade(pack.grades.map_from, insp, mileage, clock.now())
    value = grade["value"]
    c.setdefault("evidenceRecords", []).append(grade)
    at = parse_time(grade["at"])
    vehicle["inspection"] = {
        "status": (insp or {}).get("status") or "none", "score": (insp or {}).get("score"), "grade": value["grade"],
        "estimate": value["estimate"], "source": grade["source"], "at": grade["at"],
        "ageDays": _age_days(at) if at else None,
    }  # fmt: skip
    c["grade"] = value["grade"]


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
            out["age_months"] = round((clock.now().date() - installed).days / 30.4375, 1)
        except ValueError:
            pass
    if "age_months" not in out:  # no install date: the months the tool has been on its contract line
        months = ((canonical.get(s, "contract_line", asset_key) or {}).get("data") or {}).get("months_on_contract")
        if isinstance(months, int | float) and months >= 0:
            out["age_months"] = months
    return out


def _received(now: datetime) -> str:
    return now.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _base(case_id: str, i: dict[str, Any], known: dict[str, Any], by: str) -> store.Case:
    """The case record before valuation, in the book's shape (the fields every case page reads)."""
    now = clock.now()
    return {
        "id": case_id, "owner": i["org_unit_id"], "location": known.get("location") or LOCATION, "stage": STAGES[0],
        "template": i["template_key"], "assetId": i["asset_key"], "cls": known.get("cls"), "grade": known.get("grade"),
        "age": known.get("age", 0), "ageMonths": known.get("age_months"), "qty": known.get("qty", 1),
        "spec": known.get("spec") or {},
        "demand": known.get("demand") or dict(_EMPTY_DEMAND), "product": known.get("product") or "",
        "mfr": known.get("mfr") or "", "received": known.get("received") or _received(now), "kind": "standard",
        "hero": False, "readiness": "ready", "evidence": [], "notes": [], "approval": None, "exec": None,
        "override": None, "blocked": None, "facts": None, "predictions": None, "timeline": None,
        "condition": known.get("condition") or "", "assessment": None, "engLife": "Not assessed",
        "nextInspection": "—", "model": FormulaPredictor.model_version, "bomRef": known.get("bom_ref"),
        "snapshot": {"id": "EVS-" + hashlib.sha256(case_id.encode()).hexdigest()[:8].upper(), "items": 0,
                     "takenAt": _received(now)},
        "intake": {"key": intake_key(i.get("dedupe_as") or i["asset_key"], i["reason"]), "reason": i["reason"], "by": by,
                   "at": now.astimezone(UTC).isoformat()},
    } | ({"batchRef": str(known["batch"])} if known.get("batch") else {})  # fmt: skip


# ---------------------------------------------------------------- valuation
def tool_fleet_case(case_id: str, facts: dict[str, Any]) -> dict[str, Any]:
    """The tool-fleet valuer's case (the prototype's mkCase shape) from the facts; what the facts leave out takes the
    prototype's defaults for a fresh return (no named orders, every part at the tool's remaining life)."""
    cls = facts.get("cls")
    if cls == battery.CLASS:  # a battery pack (P9-3.19): valued by its own valuer, outside the tools' queue
        return battery_case(case_id, facts)
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


def battery_case(case_id: str, facts: dict[str, Any]) -> dict[str, Any]:
    """The battery valuer's case (P9-3.19): state of health with its read date, damaged or not, the site and the named orders
    the facts give. A pack has no workbench grade, parts or remaining life of its own: those fields are the neutral defaults
    the case document needs, and `tool_fleet.CLS` is not asked for them."""
    if facts.get("site") is not None and facts["site"] not in tool_fleet.SITES:
        raise ActionError("validation_error", f"A battery case's site is one of {', '.join(tool_fleet.SITES)}.")
    dem = dict(facts.get("dem") or {})
    return {
        "id": case_id, "cls": battery.CLASS, "ft": tool_fleet.FUNCS[0], "site": facts.get("site") or tool_fleet.SITES[0],
        "grade": "C", "estGrade": "C", "rul": 0, "serial": "", "age": 12, "days": 1, "partRul": [], "status": "new", "log": [],
        "soh": facts.get("soh"), "sohRead": facts.get("sohRead"), "damaged": bool(facts.get("damaged")),
        "dem": {"lease": [], "so": [], "bid": [], "proj": None, "rcq": "", "wo": {}} | dem,
        "src": tool_fleet.SOURCES.get(tool_fleet.FUNCS[0], ""),
    }  # fmt: skip


def device_lot(case_id: str, facts: dict[str, Any]) -> dict[str, Any]:
    """The device valuer's lot from the facts: brand, model, age band, grade, reference value, units, days on hand."""
    grade, band = facts.get("grade"), facts.get("band")
    if grade not in device.DST or band not in device.DST[grade]:
        raise ActionError("validation_error", "A device lot needs a grade (A-D) and an age band (0-24m, 25-48m, 49m+).")
    if not isinstance(facts.get("ref"), int | float) or not isinstance(facts.get("qty"), int) or facts["qty"] < 1:
        raise ActionError("validation_error", "A device lot needs a reference value (ref) and a number of units (qty).")
    lot = {
        "id": case_id, "brand": facts.get("brand") or "", "model": facts.get("model") or "", "band": band,
        "grade": grade, "ref": facts["ref"], "qty": facts["qty"], "doh": facts.get("doh") or 1,
    }  # fmt: skip
    return lot | {k: facts[k] for k in device_intake.EXTRA if k in facts}  # a received device keeps its IMEI, quote ... (P9-6.4)


def industrial_predictor(s: Session, c: store.Case) -> Predictor:
    """The predictor an industrial case is valued with: formulas on a random source seeded from the case id, calibrated by
    the template's active model, its parts valued from the BOM PLM holds. A class or grade the engine does not know is
    refused."""
    if c["cls"] not in CLASSES:
        raise ActionError("validation_error", f"An industrial case needs an asset class, one of {', '.join(CLASSES)}.")
    if c.get("grade") is not None and c["grade"] not in GRADE_F:
        raise ActionError("validation_error", "The grade is one of A, B, C, D.")
    return _with_bom(s, c, intake_predictor(s, FormulaPredictor(mulberry32(seed_of(c["id"]))), c["cls"]))


def _with_bom(s: Session, c: store.Case, p: Predictor) -> Predictor:
    """The parts value from the asset's BOM (plan 8, MVP-9.4) when PLM holds the assembly its bom_ref names: the
    owner's PLM data first, else the shared; otherwise the predictor as it is."""
    ref = str(c.get("bomRef") or "")
    for org in (c["owner"], None) if ref else ():
        if lines := plm.bom_lines(s, org, ref):
            return BomPartsPredictor(p, lines, plm.demand(s, org, [x.part for x in lines]))
    return p


def _snapshot(c: store.Case, facts: dict[str, Any], kind: str, s: Session | None = None) -> None:
    """The valuer's input from the facts, kept on the case (`valuer`) with the fields its pages read; `kind` is the pack's
    valuer kind."""
    if kind == "tool_fleet":
        vc = tool_fleet_case(c["id"], facts)
        c |= {k: vc[k] for k in ("cls", "ft", "site", "grade", "rul", "partRul", "dem")} | {"valuer": vc}
        c["product"] = c["product"] or (tool_fleet.CLS.get(vc["cls"]) or {"name": "Battery pack"})["name"]
    elif kind == "standard":  # the facts as given: the pack's value lines read them (and the case's own fields)
        c["valuer"] = copy.deepcopy(facts)
        c["product"] = c["product"] or str(c["assetId"])
    else:
        lot = device_lot(c["id"], facts)
        c |= {k: lot[k] for k in ("brand", "band", "grade", "ref", "doh")} | {"qty": lot["qty"], "cls": "device"}
        c |= {"valuer": lot}
        if s is not None and lot.get("imei"):  # a received device: the feed price and evidence it opened with (P9-6.4)
            lot["inputs"] = device_inputs.gather(s, lot, clock.now().date(), c.get("owner")).as_dict()
        c["product"] = c["product"] or f"{lot['brand']} {lot['model']}".strip()


def valuer_input(c: Mapping[str, Any], template_key: str) -> dict[str, Any]:
    """What the template's valuer decides a case on: the snapshot taken when it opened (`valuer`), else rebuilt from
    the case's own fields (a case opened before the snapshot was kept)."""
    if isinstance(c.get("valuer"), dict):
        out = copy.deepcopy(c["valuer"])
        if template_key == "tool_fleet" and c.get("contract_id"):
            out["contract"] = str(c["contract_id"])  # the return's own contract: its renewal is the one it takes
        return out
    facts = dict(c)
    return tool_fleet_case(c["id"], facts) if template_key == "tool_fleet" else device_lot(c["id"], facts | {"model": ""})


@dataclasses.dataclass(frozen=True)
class ToolQueue:
    """The tool-fleet queue one case is planned in (P9-1.4): the valuer inputs of its org's open cases, this one among
    them, and the named demand (canonical `demand` records) to add to each case by its id."""

    cases: list[dict[str, Any]]
    demand: dict[str, Dem]


def _recommended(doc: Mapping[str, Any]) -> Mapping[str, Any]:
    """The route a decided case takes: the one chosen (an override), else the recommended one."""
    if isinstance(doc.get("chosen"), dict) and doc["chosen"]:
        return doc["chosen"]
    i = doc.get("rec_index")
    return doc["routes"][i] if i is not None and doc.get("routes") else {}


def tool_input(doc: Mapping[str, Any]) -> dict[str, Any]:
    """A stored tool-fleet case (its document) as the queue plan reads it: an approved or executing case is `sent` and
    keeps the order its recommendation names; the others are `new`."""
    x = valuer_input(doc, "tool_fleet")
    if doc.get("stage") in ("approved", "executing"):
        rec = _recommended(doc)
        return x | {"status": "sent", "order": (rec.get("dest") or {}).get("id"), "path": rec.get("id")}
    return x | {"status": "new"}


def open_tool_cases(s: Session, org_unit_id: str) -> list[dict[str, Any]]:
    """The documents of the org's tool-fleet cases that are not closed, in case id order (a battery pack has its own valuer and
    is not in the tools' queue)."""
    rows = s.execute(
        text(
            "SELECT data FROM case_record WHERE owner = :o AND stage <> 'closed' "
            "AND data ->> 'template' = 'tool_fleet' AND COALESCE(data ->> 'flow', '') <> :f "
            "AND COALESCE(data ->> 'cls', '') <> 'BAT' ORDER BY id"
        ),
        {"o": org_unit_id, "f": REFRESH_FLOW},
    ).scalars()
    return sorted(rows, key=lambda d: str(d["id"]))


def open_unit_cases(s: Session, org_unit_id: str, template: str, except_id: str) -> list[dict[str, Any]]:
    """The documents of the org's other open cases of a unit template (telecom network), in case id order: the queue a unit
    is planned in (P9-10.10)."""
    rows = s.execute(
        text(
            "SELECT data FROM case_record WHERE owner = :o AND stage <> 'closed' AND data ->> 'template' = :t "
            "AND id <> :i ORDER BY id"
        ),
        {"o": org_unit_id, "t": template, "i": except_id},
    ).scalars()
    return list(rows)


def tool_queue(s: Session, org_unit_id: str, v: dict[str, Any]) -> ToolQueue:
    """The queue for the valuer input `v` of a case of the org: its open tool-fleet cases plus `v`, with the named
    demand of their classes: the queue's tagged orders (named_demand.for_queue) and the live named demand of the org's
    sources, in days from now (tool_demand.named_demand, P9-3.12; the orders an approved decision holds are not offered)."""
    others = [tool_input(d) for d in open_tool_cases(s, org_unit_id) if d["id"] != v["id"]]
    # in case id order, as `tool_queue.open_queue` reads them: two returns that value the same are told apart by their
    # place in the queue, so every case must see it in one order (else each of two equal returns finds itself last)
    return queue_of(s, org_unit_id, sorted([*others, v | {"status": "new"}], key=lambda c: str(c["id"])))


def queue_of(s: Session, org_unit_id: str, cases: list[dict[str, Any]]) -> ToolQueue:
    """The queue of the given valuer inputs of the org with the named demand of their classes (`tool_queue` and
    `tool_queue.open_queue`, P9-3.13)."""
    classes = sorted({c["cls"] for c in cases})
    named = named_demand.for_queue(s, org_unit_id, classes)
    now = clock.now()
    live = {k: tool_demand.named_demand(s, org_unit_id, k, now) for k in classes}
    return ToolQueue(cases, {c["id"]: tool_inputs.merge_demand(named[c["cls"]], live[c["cls"]]) for c in cases})


def case_rules(s: Session, c: Mapping[str, Any]) -> list[Any]:
    """The rules of the case's owner's published flow (what its recommendation was valued with)."""
    return list(flow_version(s, dict(c)).rules)


def _rule_dicts(rules: Sequence[Any]) -> list[dict[str, Any]]:
    return [dataclasses.asdict(r) if dataclasses.is_dataclass(r) and not isinstance(r, type) else dict(r) for r in rules]


def tool_plan(q: ToolQueue, rules: Sequence[Any], params: Mapping[str, float] | None = None) -> tool_fleet.Plan:
    """The queue planned by the tool-fleet pack's planner (engine.queue, I-5)."""
    p = tool_fleet.BASEP if params is None else tool_fleet.BASEP | dict(params)
    return planner_for(load_pack("tool_fleet")).plan(
        q.cases, q.demand, Capacity(slots=js_round(p["slots"])), rules=_rule_dicts(rules), params=p
    )


def _pack(s: Session, c: store.Case) -> Pack:
    """The pack the case is decided with: its pack file (or the one a gate recheck is given) with its owner's published
    customer overlay."""
    return live_pack(s, c, gate_hold.base_pack(c, published_pack(s, c.get("template") or "industrial", c["owner"])))


def recommend(s: Session, c: store.Case, fv: FlowVersion) -> Route | None:
    """What a template case would be recommended under another flow version (a flow's draft in shadow, MVP-3.5), from the
    snapshot it opened with: the case itself is unchanged."""
    return decide.decide_case(c, _pack(s, c), fv, session=s).recommendation


def revalue(s: Session, c: store.Case) -> None:
    """A template case valued again (case.reevaluate): its valuer and the owner's published rules, as at opening. The
    stage is the caller's to move."""
    stage = c["stage"]
    _value(s, c, {})
    if c.get("flow") != "service_desk" or stage not in OPEN_STAGES:
        c["stage"] = stage
    # else a ticket no one has acted on follows its decision (`_value` set it): a recommendation waits for approval, a held one
    # (GR-S1, GR-12) has none. Its options exist only after its estimate, so the opening valuation could not know them (F2).
    open_battery_case(s, c)  # an EV whose assessment says replace the pack opens the pack's case (P9-12.7)


def _value(s: Session, c: store.Case, facts: dict[str, Any]) -> None:
    """Routes, recommendation and the flow version they were evaluated with (as a re-evaluation records them): the one
    decider's decision (di.services.cases.decide) set on the case."""
    if is_refresh(c):  # a contract refresh is priced (P9-5.4): its priced routes are the decision a person approves (P9-5.5)
        from di.services import refresh_decision  # lazy: it imports this module

        c |= {"routes": [], "recommendation": None, "stage": STAGES[0]}
        refresh_decision.attach(s, c)  # nothing to price (no market, tools or tables): the case stays without a decision
        return
    fv = flow_version(s, c)  # also refreshes the case's scope facts
    pack = _pack(s, c)
    was_held = isinstance(c.get("gateHold"), dict)
    if pack.key != "industrial":
        gate_hold.attach_evidence(s, c)  # the gates read the asset's compliance records (plan 9, P9-1.2)
        if pack.key == cpe_lot.PACK:
            cpe_lot.refresh(s, c, pack)  # a telecom CPE lot's lines, each with its reset record or held without (P9-12.6)
        if pack.key == CAR_TEMPLATE:
            car_read(s, c, pack)  # the inspection read, or an estimate, as the grade evidence (P9-9.7)
        if facts or not c.get("routes"):
            _snapshot(c, facts, pack.valuer.kind, s)
        if pack.key == BATTERY_TEMPLATE:
            c["battery"] = battery_facts(s, c)  # the BMS's read, as the G-BAT gates and the value lines read it (P9-12.7)
        if pack.valuer.kind == "tool_fleet" and regrade.apply(s, c):  # the workbench grade, else the estimate (P9-3.5)
            fv = flow_version(s, c)  # the rules' scope reads the grade the case now shows
        if pack.key == SERIAL_PACK:  # a returned phone's wipe certificate and registry check, as a device's (P9-12.10)
            device_lock.refresh(s, c, pack)
            device_wipe.refresh(s, c)
        if pack.valuer.kind == "device":  # the quote against the lab's read, on every valuation (P9-6.5)
            device_verify.refresh(s, c)
            device_lock.refresh(s, c, pack)  # and the registry check, its date and age (P9-6.6)
            device_wipe.refresh(s, c)  # and the wipe certificate (P9-6.7)
            device_inputs.refresh_listing(s, c, clock.now().date())  # and the days the device is listed (P9-6.13)
    decide.write_back(c, decide.decide_case(c, pack, fv, session=s))
    if pack.key != "industrial":  # custody and the system of record (plan 9, P9-1.10)
        if was_held and c.get("gateHold") is None:
            record_match.released(c)
        record_match.check(s, c, pack)
        if pack.valuer.kind == "device":
            device_lock.check(s, c, pack)  # a registry hit opens the blacklist_hit exception (P9-6.6)
            device_verify.check(s, c, pack)  # a mismatch opens the quote_mismatch exception (P9-6.5)
            device_payout.assess_case(
                s, c, pack
            )  # the payout once graded: within the limit adjusted, else for Customer care (P9-6.8)
    # a recommendation waits for approval, as after a re-evaluation (decision.reevaluate); none: no decision yet
    c["stage"] = "awaiting_approval" if c["recommendation"] else STAGES[0]
    if pack.key in APPROVAL_PACKS:  # a decision over a limit waits for its manager, as an item in My work (P9-9.11)
        approval_hold.sync(s, c, pack)  # and so does a telecom resale the customer's guardrail holds (P9-10.14)
        if pack.key == CAR_TEMPLATE and battery_wait.holding(c):  # an EV waits for its battery assessment (P9-9.14)
            battery_wait.request(s, c)


def battery_facts(s: Session, c: Mapping[str, Any]) -> dict[str, Any]:
    """The `battery` facts of a pack case (P9-12.7): the facts the case opened with, over which the canonical record of the pack
    (the BMS's read: `asset.pack_*`, `condition.soh_pct` ...) wins where it has a value; damage and a thermal event are never
    cleared by a later read (either source saying so keeps the pack damaged). `gate_checks.battery.case_view` shapes them."""
    key = str(c["assetId"])
    asset = (canonical.get(s, "asset", key) or {}).get("data") or {}
    cond = (canonical.get(s, "condition", key) or {}).get("data") or {}
    snap = dict(c.get("valuer") or {})
    read = {
        "chemistry": asset.get("pack_chemistry"), "market": asset.get("pack_market"), "safety_class": asset.get("safety_class"),
        "soh_pct": cond.get("soh_pct"),
        "expected_life_years": cond.get("expected_life_years"), "read_at": cond.get("soh_read_at"),
    }  # fmt: skip
    facts = snap | {k: v for k, v in read.items() if v is not None}
    facts["damaged"] = bool(snap.get("damaged")) or bool(asset.get("pack_damaged"))
    facts["thermal_event"] = bool(snap.get("thermal_event")) or bool(asset.get("thermal_event"))
    facts.setdefault("packId", key.rpartition(":")[2])
    return battery_gates.case_view(facts)


def open_battery_case(s: Session, c: store.Case) -> bool:
    """NS-BAT-01 (P9-12.7): a used car whose battery assessment (P9-9.14) says `pack_replacement_needed` opens a
    `battery` case for
    its pack, linked both ways: the new case's `linked_case` is the car case, the car case's `linked` lists it. The pack is the
    one the BMS names for the car's VIN (`asset.vin_ref`); with none on file nothing opens. Returns True when this call linked a
    case; the caller saves `c`."""
    if c.get("template") != CAR_TEMPLATE or any(x.get("template") == BATTERY_TEMPLATE for x in c.get("linked") or []):
        return False
    cond = (canonical.get(s, "condition", str(c["assetId"])) or {}).get("data") or {}
    if cond.get("battery_assessment_result") != "pack_replacement_needed":
        return False
    vin = str((c.get("vehicle") or {}).get("vin") or str(c["assetId"]).rpartition(":")[2])
    row = s.execute(
        text("SELECT key FROM canonical WHERE model = 'asset' AND key LIKE :o AND data ->> 'vin_ref' = :v ORDER BY key LIMIT 1"),
        {"o": f"{c['owner']}:%", "v": vin},
    ).first()
    if row is None:
        return False
    ref = str(row[0]).rpartition(":")[2]
    body = {"org_unit_id": c["owner"], "template_key": BATTERY_TEMPLATE, "asset_key": row[0], "reason": "pack_replacement",
            "facts": {"packId": ref, "linked_case": c["id"]}, "by": "system"}  # fmt: skip
    try:
        opened = open_case(s, body, "system")
    except ActionError as e:
        if e.code == "duplicate":  # the pack has a case already (opened by a person): the car links to it
            opened = {"id": e.message.split(" ")[0]}
        else:
            raise
    c.setdefault("linked", []).append({"case": opened["id"], "template": BATTERY_TEMPLATE, "ref": ref})
    return True


def one_open(s: Session, template: str, asset_key: str) -> str | None:
    """The open (not closed) case of the template for the car or device, if any."""
    row = s.execute(
        text(
            "SELECT id FROM case_record WHERE stage <> 'closed' AND data ->> 'template' = :t AND data ->> 'assetId' = :a "
            "ORDER BY id LIMIT 1"
        ),
        {"t": template, "a": asset_key},
    ).first()
    return row[0] if row else None


def _join_one(
    s: Session, p: OneCase, case_id: str, i: dict[str, Any], facts: dict[str, Any], at: datetime, actor: str
) -> store.Case:
    """A second event for a car or device joins its open case (P9-9.7, P9-11.6): its facts are added with their own source
    and age, the event is listed in `intake.joined`, the case is valued again while no one has acted on it, and the stage
    log says so."""
    c = store.get(s, case_id, for_update=True)
    if c is None:  # not reached: one_open just found it under the same lock
        raise ActionError("not_found", f"No case {case_id}.")
    by = i.get("by") or actor
    c.setdefault(p.group, {p.id_fact: facts.get(p.id_fact), "facts": []})["facts"] += one_facts(
        s, p, i["asset_key"], facts, facts["source"], at
    )  # appended: the asset's facts from each source stay, the newest last
    c["intake"].setdefault("joined", []).append(
        {"key": intake_key(i.get("dedupe_as") or i["asset_key"], i["reason"]), "reason": i["reason"], "by": by,
         "source": facts["source"], "at": at.astimezone(UTC).isoformat()}
    )  # fmt: skip
    if isinstance(c.get("valuer"), dict):
        c["valuer"] |= {k: v for k, v in facts.items() if k != "source"}
    if c["stage"] in OPEN_STAGES:
        revalue(s, c)
    store.save(s, c)
    s.execute(
        text("INSERT INTO case_stage_log (case_id, from_stage, to_stage, reason, actor) VALUES (:c, :st, :st, :r, :a)"),
        {"c": case_id, "st": c["stage"], "r": f"Joined by {i['reason']} from {facts['source']}", "a": actor},
    )
    return c


# ---------------------------------------------------------------- telecom units (P9-10.6)
UNIT_TEMPLATE = "telecom_network"
UNIT_SOURCE = {"decommission": "tn_decom"}  # the source an event's facts come from unless it names one
UNIT_FIELDS = {  # a case fact -> the `asset` field that gives its source and age (the tracker's own writes)
    "serial": "serial", "model": "model", "removed_at": "removed_at", "removal_job": "removal_job", "programme": "programme",
}  # fmt: skip
UNIT_REASONS = ("decommission",)  # the removal of a unit (the pack's intake trigger), allowed beside REASONS by `problem`


def unit_facts(s: Session, key: str, facts: Mapping[str, Any], source: str, at: datetime) -> list[dict[str, Any]]:
    """Each fact of a removed unit with its source and age (in days): when the event's source wrote the fact's canonical
    `asset` field, that write's time; else the event's."""
    asset = canonical.get(s, "asset", key)
    out: list[dict[str, Any]] = []
    for name, value in facts.items():
        when = (_newest(asset, UNIT_FIELDS[name], source) if name in UNIT_FIELDS else None) or at
        out.append({"fact": name, "value": value, "source": source, "at": when.isoformat(), "ageDays": _age_days(when)})
    return out


def unit_view(facts: Mapping[str, Any], source: str, kept: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """The case's `network`: the unit's serial, model, removal `site`, `removedAt` and job, the first `source` and every
    fact with its source and age (`facts`, the newest last). The inventory match gate reads the model and the site."""
    return {
        "serial": facts.get("serial"), "model": facts.get("model"), "site": facts.get("site"),
        "removedAt": facts.get("removed_at"), "job": facts.get("removal_job"), "source": source, "facts": list(kept),
    }  # fmt: skip


def unit_case(s: Session, asset_key: str) -> str | None:
    """The open (not closed) case of the unit, if any."""
    row = s.execute(
        text(
            "SELECT id FROM case_record WHERE stage <> 'closed' AND data ->> 'template' = :t AND data ->> 'assetId' = :a "
            "ORDER BY id LIMIT 1"
        ),
        {"t": UNIT_TEMPLATE, "a": asset_key},
    ).first()
    return row[0] if row else None


def _join_unit(s: Session, case_id: str, i: dict[str, Any], facts: dict[str, Any], at: datetime, actor: str) -> store.Case:
    """A second event for a unit joins its open case: its facts are added with their own source and age, the event is listed
    in `intake.joined`, the case is valued again while no one has acted on it, and the stage log says so."""
    c = store.get(s, case_id, for_update=True)
    if c is None:  # not reached: unit_case just found it under the same lock
        raise ActionError("not_found", f"No case {case_id}.")
    by = i.get("by") or actor
    net = c.setdefault("network", unit_view(facts, facts["source"], []))
    net["facts"] += unit_facts(s, i["asset_key"], facts, facts["source"], at)
    for name, field in (("model", "model"), ("site", "site"), ("removed_at", "removedAt"), ("removal_job", "job")):
        if facts.get(name) is not None:  # the newest event's removal facts are the case's
            net[field] = facts[name]
    c["intake"].setdefault("joined", []).append(
        {"key": intake_key(i.get("dedupe_as") or i["asset_key"], i["reason"]), "reason": i["reason"], "by": by,
         "source": facts["source"], "at": at.astimezone(UTC).isoformat()}
    )  # fmt: skip
    if isinstance(c.get("valuer"), dict):
        c["valuer"] |= {k: v for k, v in facts.items() if k != "source"}
    if c["stage"] in OPEN_STAGES:
        revalue(s, c)
    store.save(s, c)
    s.execute(
        text("INSERT INTO case_stage_log (case_id, from_stage, to_stage, reason, actor) VALUES (:c, :st, :st, :r, :a)"),
        {"c": case_id, "st": c["stage"], "r": f"Joined by {i['reason']} from {facts['source']}", "a": actor},
    )
    return c


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
    if dup := existing(s, i.get("dedupe_as") or i["asset_key"], i["reason"]):
        raise ActionError("duplicate", f"{dup} is already open for {i['asset_key']} ({i['reason']}).")
    facts = dict(i.get("facts") or {})
    one = ONE_CASE.get(i["template_key"])  # a car or a rental device: one case for the asset (P9-9.7, P9-11.6)
    if one is not None:
        source, at = one_event(i, facts, one)
        if joined := one_open(s, i["template_key"], i["asset_key"]):
            return _join_one(s, one, joined, i, facts | {"source": source}, at, actor)
        facts = one_known(s, one, i["asset_key"]) | facts | {"source": source}
    unit = i["template_key"] == UNIT_TEMPLATE
    if unit:  # one case per serial (P9-10.6): a second event for the unit joins the open case
        source = str(i.get("source") or facts.get("source") or UNIT_SOURCE.get(i["reason"], ""))
        at = parse_time(i.get("at")) or clock.now()
        if joined := unit_case(s, i["asset_key"]):
            return _join_unit(s, joined, i, facts | {"source": source}, at, actor)
    case_id = _next_id(s)
    if i["template_key"] == "tool_fleet":
        facts = tool_return_facts(facts, i["asset_key"], i["reason"])
    elif i["template_key"] == "device" and i["reason"] == "trade_in" and facts.get("imei") and "ref" not in facts:
        facts = device_intake.intake_facts(s, case_id, facts)  # a received device (P9-6.4)
    known = _canonical(s, i["asset_key"]) | facts
    if gone := missing_fields(s, i, known):
        raise ActionError("validation_error", f"The case needs {', '.join(gone)} (the pack's minimum facts).")
    c = _base(case_id, i, known, i.get("by") or actor)
    if one is not None:
        c[one.group] = {one.id_fact: facts.get(one.id_fact), "facts": one_facts(s, one, i["asset_key"], facts, source, at)}
    if unit:
        c["network"] = unit_view(facts, source, unit_facts(s, i["asset_key"], facts, source, at))
    kept = ("serial", "contract_id", "line_id", "flow", "serviceDesk", "linked_case")  # a return's, a ticket's, a pack's car
    c |= {k: known[k] for k in kept if known.get(k) is not None}
    if is_refresh(c):
        c["refresh"] = dict(facts)  # the contract, its window and its lines (P9-5.1)
    else:
        record_match.receive(s, c, i.get("by") or actor)
    _value(s, c, facts)
    store.insert_new(s, c, f"Case opened from {i['reason']}", actor)
    if open_battery_case(s, c):
        store.save(s, c)  # the link to the pack's case, now that this case has its row
    device_payout.flush(s, c)  # the payout's journal line, now the case row exists (P9-6.8)
    payload = {"case_id": case_id, "owner": c["owner"], "template": c["template"], "asset_key": i["asset_key"],
               "reason": i["reason"], "by": c["intake"]["by"]}  # fmt: skip
    s.execute(
        text("INSERT INTO domain_event (type, case_id, payload) VALUES ('case.opened', :c, CAST(:p AS jsonb))"),
        {"c": case_id, "p": json.dumps(payload)},
    )
    if c["template"] == "tool_fleet" and not is_refresh(
        c
    ):  # the org's other open returns are planned again with this one (P9-1.4)
        jobs.enqueue(
            s, "case.replan", {"org_unit_id": c["owner"], "template": "tool_fleet"}, dedupe_key=f"case.replan:{c['owner']}"
        )
    if get_settings().autopilot_on_open:
        jobs.enqueue(s, "agent.autostart", {"case_id": case_id, "account": account_id}, dedupe_key=f"agent.autostart:{case_id}")
    return c
