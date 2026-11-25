"""Pack format v1: a pack is one versioned JSON document holding everything one kind of returns desk needs
(plan 9, P9-1.1; research B section 7.2). Implements registry entry I-1: `Pack`, `load_pack`, the pack files
`packs/<key>.json` and the schema `packs/pack.schema.json`.

Owns: the `Pack` model (13 parts, `PACK_PARTS`, `FIELD_PART`), `PackError` (names the pack, its version and the part
that failed), `parse_pack`, `load_pack` and `pack_keys`.
Never does: evaluate a pack (gates, overlays, valuers and the decider read it), write a file, or touch a session.
`templates.template_of_pack` builds the authoring `Template` from a pack.

The format grows by addition only: a later task adds an optional field with a default, never renames or removes one.
Pydantic validates at load; `pack.schema.json` (written by `python -m scripts.gen_pack_schema`) is for authors,
agents and Compose.

Conventions of this module's data:
- A guardrail's `forbids` and `protects` are the authoring checks of `templates.Forbid` and `templates.TextPattern`
  (`protects`: each inner list is the regexes that must all match the lowercased text).
- `valuer.params` is free-form per valuer kind. Tool fleet: `paths, classes, basep, fin, poolk, funcs, sites,
  sources, cust, dealers`. Device: `dch, dcn, dcfg, dst, dg`. The valuer modules copy what they read.
- `customer_layer.params` is keyed `"<guardrail id>.<field>"` when a pack publishes one (none of the shipped packs do).
"""

import json
from collections.abc import Mapping
from functools import cache
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from di.services.modeler.stages import STAGE_KEYS, GuardType, StageKey

PACKS_DIR = Path(__file__).parent / "packs"
SEMVER = r"^\d+\.\d+\.\d+$"
Autonomy = Literal["recommend", "limits", "alone"]
RouteClass = Literal["reuse", "release", "refurbish", "sale", "parts", "recycle", "exit"]
DimKind = Literal["set", "min", "max"]


class _Part(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class LegalReview(_Part):
    status: Literal["pending", "reviewed"]
    date: str | None = None


class FlowRef(_Part):
    key: str
    name: str


class ClarifyOption(_Part):
    label: str
    adds: str


class Clarify(_Part):
    question: str
    options: list[ClarifyOption]


class AssetAttrs(_Part):
    serialised: bool
    has_media: bool
    hazardous: bool
    regulated: bool
    patient_data: bool


class PackClass(_Part):
    id: str
    name: str
    attrs: AssetAttrs
    new_price: float | None = None


class Grades(_Part):
    scale: list[str]
    graded_by: Literal["read", "computed"]
    map_from: dict[str, Any] = Field(default_factory=dict)


class PackStage(_Part):
    key: StageKey
    label: str
    agent: str
    autonomy: Autonomy
    confidence: float


class PackRoute(_Part):
    id: str
    name: str
    app: str
    owner: str
    lead_days: int | None = None
    classes: list[RouteClass]
    instructions: list[str] = Field(default_factory=list)


class ForbidDef(_Part):
    path: str
    actions: list[str]
    scope_any: dict[str, list[str]] = Field(default_factory=dict)


class GuardParam(_Part):
    field: str
    value: float
    stricter: Literal["lower", "higher"]
    min: float
    max: float


class PackGuardrail(_Part):
    id: str
    text: str
    owner: str
    type: GuardType
    stage: StageKey
    locked: bool
    forbids: list[ForbidDef] = Field(default_factory=list)
    protects: list[list[str]] = Field(default_factory=list)
    approvers: list[str] = Field(default_factory=list)
    param: GuardParam | None = None


class GateRef(_Part):
    id: str
    params: dict[str, Any] = Field(default_factory=dict)
    active: bool = True


class ScopeDimDef(_Part):
    key: str
    label: str
    kind: DimKind
    values: list[str]
    fields: list[str] = Field(default_factory=list)


class PhraseDef(_Part):
    key: str
    fmt: str
    joiner: str
    words: dict[str, str] = Field(default_factory=dict)


class WordingDef(_Part):
    every: str
    phrases: list[PhraseDef]
    path_names: dict[str, str]


class ParamRange(_Part):
    value: float
    min: float
    max: float


class SampleDiversion(_Part):
    text: str
    op: dict[str, Any]
    blocked: bool
    reason: str


class CustomerLayer(_Part):
    editable: dict[str, list[str]] = Field(default_factory=dict)
    params: dict[str, ParamRange] = Field(default_factory=dict)
    sample_diversions: list[SampleDiversion] = Field(default_factory=list)
    merge_rule: Literal["stricter_wins"] = "stricter_wins"


class Diversion(_Part):
    """One customer step or shortcut, written by `apply_overlay` (P9-1.3); never present in a pack file."""

    op_id: str
    stage: StageKey
    when: list[dict[str, Any]] = Field(default_factory=list)
    kind: Literal["step", "shortcut"]
    step: str | None = None
    to: str | None = None
    owner_role: str = ""


class DataSystem(_Part):
    type: str
    name: str
    adapter: Literal["registry", "needs_connector"]
    system_of_record: bool = False


class DataEntity(_Part):
    name: str
    canonical: str


class PackData(_Part):
    systems: list[DataSystem] = Field(default_factory=list)
    entities: list[DataEntity] = Field(default_factory=list)
    mappings: list[dict[str, Any]] = Field(default_factory=list)
    min_fields: list[str] = Field(default_factory=list)
    record_match: dict[str, Any] | None = None


class CarbonRef(_Part):
    set: str
    d_rule: Literal["demand", "low", "transport_only", "none"]


class PackValuer(_Part):
    kind: Literal["industrial", "tool_fleet", "device", "standard"]
    params: dict[str, Any] = Field(default_factory=dict)
    carbon: CarbonRef


class Replay(_Part):
    dataset: str | None = None
    example: dict[str, Any] | None = None


class ExceptionType(_Part):
    id: str
    label: str
    owner_role: str
    action: str


class Runtime(_Part):
    exception_types: list[ExceptionType] = Field(default_factory=list)
    suggestion_rules: list[dict[str, Any]] = Field(default_factory=list)
    sla_hours: dict[str, float] = Field(default_factory=dict)
    escalate_to: str | None = None


class Kpi(_Part):
    id: str
    label: str
    definition: str
    measure: dict[str, Any] | None = None
    trend: Literal["weekly", "monthly"] | None = None


class AnalyticsQuestion(_Part):
    question: str
    chart: str
    query: dict[str, Any] | None = None
    example: list[Any] = Field(default_factory=list)


class Pack(_Part):
    """A template pack. Each top-level field belongs to one of the 13 parts (`FIELD_PART`)."""

    # 1 identity
    key: str
    name: str
    version: str = Field(pattern=SEMVER)
    unit: str
    author_role: str
    prefix: str
    industry: str
    regions: list[str]
    legal_review: LegalReview
    data_licence: str
    flows: list[FlowRef]
    # 2 prompts
    prompts: list[str] = Field(min_length=3, max_length=3)
    clarify: Clarify | None = None
    # 3 classes
    classes: list[PackClass]
    grades: Grades
    # 4 stages
    stages: list[PackStage]
    # 5 routes
    routes: list[PackRoute] = Field(min_length=1)
    # 6 guardrails and gates
    guardrails: list[PackGuardrail]
    gates: list[GateRef]
    dims: list[ScopeDimDef]
    actors: list[tuple[str, str, str]]
    wording: WordingDef
    # 7 customer layer
    customer_layer: CustomerLayer
    diversions: list[Diversion]
    # 8 data
    data: PackData
    # 9 valuer
    valuer: PackValuer
    # 10 replay
    replay: Replay
    # 11 runtime
    runtime: Runtime
    # 12 KPIs
    kpis: list[Kpi]
    analytics: list[AnalyticsQuestion]
    # 13 stories
    stories: list[str]

    @field_validator("stages")
    @classmethod
    def _seven_stages(cls, v: list[PackStage]) -> list[PackStage]:
        if tuple(s.key for s in v) != STAGE_KEYS:
            raise ValueError(f"exactly the seven stages in order: {', '.join(STAGE_KEYS)}")
        if any(not 0.65 <= s.confidence <= 0.85 for s in v):
            raise ValueError("stage confidence must be from 0.65 to 0.85")
        return v

    @field_validator("routes")
    @classmethod
    def _unique_routes(cls, v: list[PackRoute]) -> list[PackRoute]:
        ids = [r.id for r in v]
        if len(set(ids)) != len(ids):
            raise ValueError("route ids must be unique")
        return v


PACK_PARTS: dict[int, str] = {
    1: "identity", 2: "prompts", 3: "classes", 4: "stages", 5: "routes", 6: "guardrails", 7: "customer_layer",
    8: "data", 9: "valuer", 10: "replay", 11: "runtime", 12: "kpis", 13: "stories",
}  # fmt: skip
FIELD_PART: dict[str, int] = {
    **dict.fromkeys(
        ("key", "name", "version", "unit", "author_role", "prefix", "industry", "regions", "legal_review",
         "data_licence", "flows"), 1),
    **dict.fromkeys(("prompts", "clarify"), 2),
    **dict.fromkeys(("classes", "grades"), 3),
    "stages": 4,
    "routes": 5,
    **dict.fromkeys(("guardrails", "gates", "dims", "actors", "wording"), 6),
    **dict.fromkeys(("customer_layer", "diversions"), 7),
    "data": 8,
    "valuer": 9,
    "replay": 10,
    "runtime": 11,
    **dict.fromkeys(("kpis", "analytics"), 12),
    "stories": 13,
}  # fmt: skip


class PackError(ValueError):
    """A pack that does not validate: names the pack, its version and the part (1-13; 0 for an unknown field)."""

    def __init__(self, key: str, version: str, part: int, part_name: str, message: str) -> None:
        self.key, self.version, self.part, self.part_name = key, version, part, part_name
        super().__init__(f"Pack {key} v{version}: part {part} ({part_name}): {message}")


def parse_pack(doc: Mapping[str, Any]) -> Pack:
    """Validate `doc`; the first error's top-level field gives the part named in the `PackError`."""
    try:
        return Pack.model_validate(dict(doc))
    except ValidationError as e:
        first = e.errors()[0]
        field = str(first["loc"][0]) if first["loc"] else ""
        part = FIELD_PART.get(field, 0)
        raise PackError(
            str(doc.get("key", "?")), str(doc.get("version", "?")), part, PACK_PARTS.get(part, "unknown field"), first["msg"]
        ) from e


_NOT_PACKS = frozenset({"pack.schema.json", "carbon.json", "gates.catalogue.json"})


def pack_keys() -> tuple[str, ...]:
    """The pack files present, sorted."""
    return tuple(sorted(p.stem for p in PACKS_DIR.glob("*.json") if p.name not in _NOT_PACKS))


@cache
def load_pack(key: str) -> Pack:
    """`packs/<key>.json` through `parse_pack`. Cached: treat as read-only. KeyError for an unknown key."""
    if key not in pack_keys():
        raise KeyError(key)
    return parse_pack(json.loads((PACKS_DIR / f"{key}.json").read_text(encoding="utf-8")))
