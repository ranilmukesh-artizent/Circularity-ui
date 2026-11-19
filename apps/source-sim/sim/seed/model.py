"""The synthetic world as typed objects (docs/BACKEND_STEPS.md, B2).

Each case is split three ways:
- source facts (`CaseFacts`, `RouteFacts`, `Term`, `Evidence`, `Demand`): what the enterprise systems hold. The mock
  systems (B3-B5) seed only these.
- `DemoResults`: what the demo computed from them (gates, ranges, rank, recommendation). The decision engine (B10)
  recomputes these and its tests compare against them.
- `WorkflowState`: where the demo's case stands (stage, approval, execution). di builds this itself (B11-B13).
"""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class _M(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid", frozen=True)


# ---------------- world ----------------
class Site(_M):
    id: str
    name: str


class Route(_M):
    id: str
    name: str
    short: str
    color: str


class AssetClass(_M):
    label: str
    plural: str
    pre: str  # asset id prefix, e.g. MTR
    pnew: float  # price new, USD
    tau: float  # life constant, years
    mfr: list[str]
    weight: float


class ModelVersion(_M):
    v: str
    released: str
    bias: float
    k: float
    from_: int = Field(alias="from")
    to: int


class World(_M):
    as_of: datetime
    months: list[str]
    tenants: list[str]
    sites: list[Site]
    facilities: list[str]
    routes: list[Route]
    route_mix: list[tuple[str, int]]
    models: list[ModelVersion]
    gates: list[str]
    classes: dict[str, AssetClass]
    grade_factor: dict[str, float]


# ---------------- case: source facts ----------------
class Term(_M):
    label: str
    amt: float
    kind: str  # purchase, prep, service, residual, sale, fees, ...


class RouteFacts(_M):
    id: str  # redeploy, resale, intparts, relase, material, extparts, exit
    plan: str
    target: str | None = None
    vendor: str | None = None
    variant: str | None = None
    demand_label: str | None = None
    demand_status: Literal["confirmed", "forecast"] | str | None = None
    terms: list[Term]
    sigma: float
    p: float  # success probability
    unc: str | None = None
    why: str | None = None
    hold_back: bool | None = None
    refurb_delta: float | None = None
    gate_notes: list[str] = []

    @property
    def net(self) -> float:
        return sum(t.amt for t in self.terms)


class Evidence(_M):
    k: str
    label: str
    source: str
    state: str  # ready, missing, requested, ...
    fresh: str
    note: str = ""


class Demand(_M):
    confirmed: bool
    internal: bool
    parts: bool
    lease: str | None = None
    site: str | None = None


class CaseFacts(_M):
    id: str  # RT-1048
    asset_id: str  # MTR-2041
    cls: str
    product: str
    mfr: str
    spec: dict[str, Any]
    owner: str  # tenant
    location: str
    received: datetime
    qty: int
    age: float
    grade: str | None = None
    condition: str
    assessment: str
    readiness: str
    eng_life: str
    next_inspection: str
    horizon: str | None = None
    timing: str | None = None
    kind: str
    hero: bool
    demand: Demand
    evidence: list[Evidence]
    facts: list[str] = []
    pool_id: str | None = None
    routes: list[RouteFacts]


# ---------------- case: what the demo computed, and its workflow state ----------------
class RouteResult(_M):
    """Same order as CaseFacts.routes. A case can hold two routes with the same id (e.g. RT-1049: sell as is,
    and refurbish then sell), so pair them by position, not by id."""

    id: str
    variant: str | None = None
    net: float
    p10: float
    p90: float
    gates: list[str]  # pass | fail | skip, one per gate
    excluded: bool
    fail_gate: int
    fail_reason: str
    rank: int | None


class DemoResults(_M):
    routes: list[RouteResult]
    recommendation: int | None  # index into routes (and CaseFacts.routes); None when blocked or nothing is eligible
    model: str  # model version used
    predictions: list[dict[str, Any]] = []
    snapshot: dict[str, Any] = {}
    pool: dict[str, Any] | None = None
    pool_result: dict[str, Any] | None = None


class WorkflowState(_M):
    stage: str  # none, awaiting_approval, reeval, approved, executing
    blocked: dict[str, Any] | None = None
    approval: dict[str, Any] | None = None
    override: dict[str, Any] | None = None
    exec: dict[str, Any] | None = None
    reeval_reason: str | None = None
    notes: list[Any] = []


class Case(_M):
    facts: CaseFacts
    results: DemoResults
    state: WorkflowState


# ---------------- closed decisions (Analytics) ----------------
class ClosedDecision(_M):
    id: str  # CS-2001
    date: datetime
    mi: int  # month index into World.months
    tenant: str
    site: str
    asset_id: str
    cls: str
    grade: str
    equip: str
    comp: str
    q: int
    route: str
    rec: str
    model: str
    status: str
    snapshot: str
    p10: float
    p50: float
    p90: float
    actual: float | None
    baseline: float
    avoided: float
    days: int | None
    base_days: int
    co2e: float
    co2m: float | None
    ero: float
    override: dict[str, Any] | None
    pool: dict[str, Any] | None
