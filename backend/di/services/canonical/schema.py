"""The canonical models and which source has authority over which field (docs/backend-steps.md, B9).

Models use the namespaces of the demo's field mappings (MAPPINGS in index.html): `asset.asset_id`,
`condition.grade`, `demand.need_by` … How they relate to the demo's seven canonical models (CANON):

    asset          Asset & component v2.3      identity, owner, configuration, components, location, availability, refs
    condition      Condition & eligibility v2.1 grade, inspection, life assessment, certificates, policy
    demand         Demand opportunity v1.8      demand line, buyer, need-by, ship-to, status, purchase baseline/alternative
    intervention   Intervention v1.5            repair/refurbishment scope, cost, duration, tests
    market         (pricing inputs of Demand)   comparable sale prices, dealer offers, time to sale
    route          (logistics inputs)           lanes, rates, carriers, ETAs
    sustainability (Outcome evidence)           emission factors, footprints
    vendor         (partner eligibility)        recycler certification, yields
    outcome        Outcome (B13b)               the actual cost lines S/4HANA posted against a decision, keyed by the
                                                approval reference (the journal entry's DocumentReferenceID)
    part           PLM part (plan 8, MVP-9.1)   number, revision, lifecycle state, name, unit cost, org unit; keyed by
                                                part_key: `<org unit or "shared">:<number>`, so the same number in two
                                                org units never collides and each key keeps its own revision
    bom            PLM BOM line (MVP-9.1)       parent, child, quantity, parent revision, harvestable; keyed by bom_key,
                                                one line per parent revision (as built next to released)
    compliance     Gate evidence (plan 9, P9-1.2) one record per asset and evidence type (a data-wipe certificate, a
                                                recall check ...): result, method, tool, reference, time, expiry,
                                                operator; keyed by compliance_key, written by one source each, so it
                                                has no FIELD_AUTHORITY entry
    contract       Fleet contract (P9-3.1)       one lease contract of the fleet contract system: customer, market,
                                                term, notice date, rate card, key account, renewal status
    contract_line  Fleet contract line (P9-3.1)  one tool on a contract: serial (the key), class, status, return
                                                reason, claims, cover terms, non-return fee
    repair_event   Repair event (P9-3.1)         one repair order of the legacy depot repair log (grade, components,
                                                hours, cost) or one teardown verdict (kind `teardown`)
    recall         Safety recall (P9-3.2)        one notice of the recall register: tool class, serial range, remedy,
                                                affected parts, status
    stock_unit     Refurbished unit (P9-3.2)     one refurbished tool in stock: serial, class, grade, remaining life,
                                                site, status
Route candidate and Decision are produced by Circularity itself (B10-B13), not by connectors; an Outcome's actuals
are read back from S/4HANA.

FIELD_AUTHORITY: when sources disagree on a field, the value of this source counts and a conflict is opened
(the demo: "Circularity names the system with authority and holds any dependent route; it never picks silently").
It follows the demo's SOURCES[*].authority labels.

MODEL_FIELDS (plan 6, B1): every field each model may hold, with its type, built once from canonical.json, the
authority table and the fields the demo's connectors write (di/services/canonical/fields.py). `check_fact` says why a fact
does not fit; the sync holds such facts as failed records (di/services/canonical/failed.py) instead of storing them.
"""

import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from di.core import golden
from di.services.canonical.fields import CONNECTOR_FIELDS

MODELS = (
    "asset", "condition", "demand", "intervention", "market", "route", "sustainability", "vendor", "outcome", "part", "bom",
    "compliance", "contract", "contract_line", "repair_event", "recall", "stock_unit",
)  # fmt: skip
SHARED_ORG = "shared"  # the key prefix of PLM data bound to no org unit


def compliance_key(asset_key: str, type: str) -> str:
    """The canonical key of a compliance record: `<asset key>:<evidence type>` (one record per asset and type)."""
    return f"{asset_key}:{type}"


def compliance_asset(key: str) -> str:
    """The asset key of a compliance record's key (an evidence type holds no colon, an asset key may)."""
    return key.rsplit(":", 1)[0]


def part_key(org_unit_id: str | None, number: str) -> str:
    """The canonical key of a PLM part: `<org unit or "shared">:<number>` (two org units may reuse a number)."""
    return f"{org_unit_id or SHARED_ORG}:{number}"


def vin_key(org_unit_id: str | None, vin: str) -> str:
    """The canonical key of a used car (plan 9, P9-9.2): `<org unit or "shared">:<VIN>`, as part_key. The lease system,
    the dealer system and later the title and inspection sources write the car's `asset`, `condition` and `market`
    facts under it."""
    return f"{org_unit_id or SHARED_ORG}:{vin}"


def serial_key(org_unit_id: str | None, serial: str) -> str:
    """The canonical key of a piece of network equipment (plan 9, P9-10.2): `<org unit or "shared">:<serial>`, as
    vin_key. The network inventory and the decommission tracker write the unit's `asset` facts under it."""
    return f"{org_unit_id or SHARED_ORG}:{serial}"


def bom_key(org_unit_id: str | None, parent: str, parent_revision: str, child: str) -> str:
    """The canonical key of a BOM line: the parent's part key, its revision and the child's number."""
    return f"{part_key(org_unit_id, parent)}@{parent_revision}>{child}"


FIELD_AUTHORITY: dict[str, str] = {
    # asset
    "asset.asset_id": "eam",  # Asset identity
    "asset.owner_tenant": "lease",  # Ownership, Lessee
    "asset.lessee": "lease",
    "asset.lease_ref": "lease",
    "asset.contract_end": "lease",  # Contract term
    "asset.configuration": "plm",  # Configuration
    "asset.compatibility": "plm",
    "asset.components": "bom",  # Part structure
    "asset.location": "wms",  # Location
    "asset.availability": "wms",  # Availability
    "asset.qty": "wms",
    "asset.return_ref": "rl",  # Return receipt
    "asset.received_at": "rl",
    "asset.disposition": "rl",
    "asset.work_order_ref": "eam",  # Work order status
    "asset.run_hours": "iot",  # Operating hours (B5c: the device's hour counter over Maximo's RUNHOURS meter)
    # condition
    "condition.grade": "repair",  # Inspection grade (MRO)
    "condition.inspection_ref": "repair",
    "condition.test_result": "repair",  # Bench test result
    "condition.life_assessment": "eng",  # Life assessment
    "condition.requalification": "eng",
    "condition.certificates": "qms",  # Certification
    "condition.policy": "qms",  # Policy
    "condition.duty_cycle_pct": "iot",  # Duty (B5c)
    # demand
    "demand.demand_id": "oms",  # Order line
    "demand.ship_to": "oms",  # Ship-to
    "demand.need_by": "oms",  # Need-by date
    "demand.status": "crm",  # Opportunity stage
    "demand.purchase_baseline": "erp",  # Purchase baseline
    "demand.supplier_lead_time": "proc",  # Supplier lead time
    "demand.purchase_alternative": "proc",  # Quoted price
    "demand.service_demand": "fsm",  # Service demand
    # intervention
    "intervention.scope": "repair",  # Repair scope and hours
    "intervention.cost": "repair",
    "intervention.hours": "repair",
    # market
    "market.sale_price": "mkt",  # Market price
    "market.dealer_offer": "dlr",  # Dealer offer
    # route (logistics)
    "route.lane_rate": "tms",  # Lane rate
    "route.carrier": "tms",  # Carrier booking
    "route.eta": "tms",  # ETA
    # sustainability, vendor
    "sustainability.emission_factor": "esg",  # Emissions factor
    "vendor.certification": "rcy",  # Vendor certification
    # outcome (B13b): actual costs are SAP S/4HANA's (K1, the book of record for actual cost)
    "outcome.line": "erp",
    "outcome.accounting_document": "erp",
}


def authority(model: str, field: str) -> str | None:
    """The source with authority over model.field (a nested field like certificates[0].expires uses its top field)."""
    top = field.split(".")[0].split("[")[0]
    return FIELD_AUTHORITY.get(f"{model}.{top}")


# ---------------------------------------------------------------- the schema each fact is checked against (plan 6 B1)
@dataclass(frozen=True)
class FieldSpec:
    type: str  # text, ref, date, number, bool, list, object, any (di/services/canonical/fields.py)
    required: bool = False  # a required field's fact may not carry an empty value


# canonical.json's models by the namespace their fields live in here; Route candidate and Decision are produced by
# Circularity itself (B10-B13) and never come from a connector
_CANON_NS = {
    "Asset & component": "asset",
    "Condition & eligibility": "condition",
    "Demand opportunity": "demand",
    "Intervention": "intervention",
    "Outcome": "outcome",
}
# The named orders of the tool-fleet queue (plan 9, P9-1.4): a `demand` record with `pack` "tool_fleet" is one order
# (kind lease, so, bid, proj, or wo for a part) the queue planner gives to one return. A lease takes its rate from
# `lease_rate`, its term from `proposed_term_months` and is a renewal when it names a `contract_ref`.
NAMED_ORDER_FIELDS = {
    "pack": "text", "org_unit": "text", "cls": "text", "who": "text", "need_days": "number", "price": "number",
    "gmin": "text", "exp_days": "number", "rental": "number", "part": "text", "backorder": "bool", "what": "text",
    "when": "text",
}  # fmt: skip

# the identity keys of canonical.json's models, and of the PLM part and BOM line (MVP-9.1)
REQUIRED = {
    ("asset", "asset_id"), ("demand", "demand_id"), ("part", "number"), ("bom", "parent"), ("bom", "child"),
    ("contract", "contract_id"), ("contract_line", "line_id"), ("repair_event", "event_id"), ("recall", "recall_id"),
    ("stock_unit", "unit_id"),
}  # fmt: skip
_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


def top_field(field: str) -> str:
    """certificates[0].expires -> certificates, line.DECOM -> line, source_refs[] -> source_refs."""
    return re.split(r"[.\[(]", field, maxsplit=1)[0]


def _build() -> dict[str, dict[str, FieldSpec]]:
    """canonical.json (its models' fields and its mappings' targets), FIELD_AUTHORITY and the connectors' fields."""
    types: dict[str, dict[str, str]] = {m: {} for m in MODELS}
    canon = golden.load("canonical")
    for m in canon["models"]:
        if ns := _CANON_NS.get(m["n"]):
            for f in m["fields"]:
                types[ns].setdefault(top_field(f), "list" if f.endswith("[]") else "any")
    for rows in canon["mappings"].values():
        for _sf, _sv, target, _cv, _t in rows:
            ns, _, f = target.partition(".")
            if ns in types:
                types[ns].setdefault(top_field(f), "any")
    for key in FIELD_AUTHORITY:
        ns, _, f = key.partition(".")
        types[ns].setdefault(f, "any")
    for ns, fields in CONNECTOR_FIELDS.items():
        for f, t in fields.items():
            if types[ns].get(f) in (None, "any"):
                types[ns][f] = t
    types["demand"] |= NAMED_ORDER_FIELDS
    return {ns: {f: FieldSpec(t, (ns, f) in REQUIRED) for f, t in fs.items()} for ns, fs in types.items()}


MODEL_FIELDS: dict[str, dict[str, FieldSpec]] = _build()


def _type_ok(value: Any, t: str) -> bool:
    if t in ("text", "ref"):
        return isinstance(value, str)
    if t == "date":
        return isinstance(value, str) and _DATE.match(value) is not None
    if t == "number":
        return isinstance(value, int | float | Decimal) and not isinstance(value, bool)
    if t == "bool":
        return isinstance(value, bool)
    if t == "list":
        return isinstance(value, list)
    if t == "object":
        return isinstance(value, dict)
    return True  # any


def check_fact(f: Any) -> str | None:
    """Why the fact does not fit its canonical model (an unknown field, an empty required field, a value of the wrong
    type), or None when it fits. A nested field (certificates[0].expires) is checked by its top field's name only."""
    spec = MODEL_FIELDS.get(f.model, {}).get(top_field(f.field))
    if spec is None:
        return f"Unknown field {f.model}.{f.field}"
    if f.value is None or f.value == "":
        return f"{f.model}.{f.field} is required" if spec.required else None
    if top_field(f.field) == f.field and not _type_ok(f.value, spec.type):
        return f"{f.model}.{f.field} must be {_TYPE_TEXT[spec.type]}, got {type(f.value).__name__} {str(f.value)[:40]!r}"
    return None


_TYPE_TEXT = {
    "text": "text", "ref": "a reference (text)", "date": "a date (YYYY-MM-DD)", "number": "a number", "bool": "true or false",
    "list": "a list", "object": "an object", "any": "a value",
}  # fmt: skip


def split_facts(facts: list) -> tuple[list, list[tuple[Any, str]]]:
    """The facts that fit the schema, and the others with the reason each is held."""
    ok, bad = [], []
    for f in facts:
        why = check_fact(f)
        if why is None:
            ok.append(f)
        else:
            bad.append((f, why))
    return ok, bad
