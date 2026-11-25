"""Per-market rate cards and decision tables (plan 9, P9-4.2; registry entry I-15; story SD-03). Pure: no session, no I/O.

Owns: the shape of a table (`JdmTable`, a GoRules JDM graph), what may be stored (`validate_table`), the evaluator port
(`DecisionTableEvaluator`) with its ZEN adapter (`ZenEvaluator`), rate cards (`RateCard`, `rate`), the reference a priced
line cites (`TableRef`), and the pack's starting tables (`market_spec`, read from `valuer.params.market_tables` of the pack).
Never: reads a table from the database (di.repositories.market_tables), changes one (the `marketTable.*` actions) or reads
language. A table is computed rules: ZEN returns booleans, shares and classes, and money stays `Decimal` in our code.
A `functionNode` or `customNode` runs code, so `validate_table` refuses it and `ZenEvaluator` calls it first: a stored table
with one can never run.
"""

import json
import re
from collections.abc import Collection, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, ValidationError

from di.services.modeler.pack import load_pack

TableKind = Literal["rate_card", "decision_table"]
FUNCTION_NODE = "Function nodes run code and are not allowed in a decision table."
_ALLOWED = ("inputNode", "outputNode", "decisionTableNode", "expressionNode")
_CODE_NODES = ("functionNode", "customNode")
_HIT_POLICIES = ("first", "collect")
_IDENT = re.compile(r"[A-Za-z_]\w*")


class TableError(ValueError):
    """A table that may not be stored or run (the problems in plain words, joined)."""


# ---------------------------------------------------------------- the JDM graph
class JdmNode(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: str
    type: str
    name: str | None = None
    content: Any = None


class JdmEdge(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: str
    sourceId: str  # the JDM key
    targetId: str  # the JDM key


class JdmTable(BaseModel):
    """A JDM graph: one input node, one output node and one or more decision table or expression nodes."""

    model_config = ConfigDict(extra="allow")
    nodes: list[JdmNode]
    edges: list[JdmEdge]

    def dump(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude_none=True)


def validate_table(body: Mapping[str, Any], declared: Collection[str] | None = None) -> list[str]:
    """The problems of a decision table body in plain words (empty: it may be stored). `declared`: the input fields the pack
    allows the table to read (`market_tables[*].inputs`); None skips that check."""
    try:
        t = JdmTable.model_validate(dict(body))
    except ValidationError:
        return ["A decision table is a graph with nodes and edges."]
    problems: list[str] = []
    types = [n.type for n in t.nodes]
    if any(x in _CODE_NODES for x in types):
        problems.append(FUNCTION_NODE)
    other = [x for x in dict.fromkeys(types) if x not in _ALLOWED and x not in _CODE_NODES]
    problems += [f"A {x} is not allowed in a decision table." for x in other]
    if types.count("inputNode") != 1:
        problems.append("A decision table has exactly one input node.")
    if types.count("outputNode") != 1:
        problems.append("A decision table has exactly one output node.")
    if not any(x in ("decisionTableNode", "expressionNode") for x in types):
        problems.append("A decision table has at least one decision table or expression node.")
    for n in t.nodes:
        if n.type == "decisionTableNode":
            problems += _table_node(n, declared)
    return problems


def _table_node(n: JdmNode, declared: Collection[str] | None) -> list[str]:
    c = n.content if isinstance(n.content, dict) else {}
    out: list[str] = []
    if c.get("hitPolicy") not in _HIT_POLICIES:
        out.append(f"{n.name or n.id}: the hit policy is first or collect.")
    for col in c.get("inputs") or []:
        field_ = str(col.get("field") or "") if isinstance(col, dict) else ""
        m = _IDENT.match(field_)
        if declared is not None and m and m.group(0) not in declared:
            out.append(f"{n.name or n.id}: {m.group(0)} is not an input of this table.")
    return out


# ---------------------------------------------------------------- the evaluator
@dataclass(frozen=True)
class TableResult:
    outputs: dict[str, Any]
    matched: list[str]  # the row ids that fired, for the "why" text
    trace: list[str] = field(default_factory=list)


class DecisionTableEvaluator(Protocol):
    def evaluate(self, table: JdmTable, inputs: Mapping[str, Any]) -> TableResult: ...


class ZenEvaluator:
    """The ZEN adapter (zen-engine, GoRules): `zen.ZenEngine().create_decision(json).evaluate(inputs, {"trace": True})`."""

    def evaluate(self, table: JdmTable, inputs: Mapping[str, Any]) -> TableResult:
        body = table.dump()
        if problems := validate_table(body):
            raise TableError(" ".join(problems))
        import zen  # lazy: only an evaluation needs the engine

        decision = zen.ZenEngine().create_decision(json.dumps(body))
        r = decision.evaluate(dict(inputs), {"trace": True})
        matched: list[str] = []
        trace: list[str] = []
        for step in sorted((r.get("trace") or {}).values(), key=lambda s: s.get("order", 0)):
            data = step.get("traceData")
            rows = [data] if isinstance(data, dict) else [d for d in data or [] if isinstance(d, dict)]
            ids = [str(d["rule"]["_id"]) for d in rows if isinstance(d.get("rule"), dict) and "_id" in d["rule"]]
            matched += ids
            if ids:
                trace.append(f"{step.get('name') or step.get('id')}: row {', '.join(ids)}")
        result = r.get("result")
        return TableResult(outputs=result if isinstance(result, dict) else {"result": result}, matched=matched, trace=trace)


# ---------------------------------------------------------------- rate cards
@dataclass(frozen=True)
class RateCard:
    market: str
    name: str
    version: int
    currency: str
    valid_from: date
    valid_to: date | None
    values: Mapping[str, Decimal]


def rate(card: RateCard, key: str) -> Decimal:
    try:
        return card.values[key]
    except KeyError:
        raise KeyError(f"{card.market} {card.name} v{card.version} has no rate {key}") from None


def rate_card(row: Any) -> RateCard:
    """A `RateCard` from a stored row (di.repositories.market_tables.TableRow) of kind rate_card."""
    vals = {k: Decimal(str(v)) for k, v in (row.body.get("values") or {}).items()}
    return RateCard(row.market, row.name, row.version, row.currency or "", row.valid_from, row.valid_to, vals)


def values_problems(body: Mapping[str, Any], keys: Iterable[str] | None = None) -> list[str]:
    """The problems of a rate card body `{"values": {key: number}}`; `keys`: the rates the pack's card has."""
    vals = body.get("values")
    if not isinstance(vals, dict) or not vals:
        return ["A rate card has values: a number for each rate."]
    out: list[str] = []
    for k, v in vals.items():
        try:
            if isinstance(v, bool) or Decimal(str(v)) < 0:
                raise InvalidOperation
        except InvalidOperation:
            out.append(f"The rate {k} must be a number of at least 0.")
    if keys is not None and set(vals) != set(keys):
        out.append("A rate card has the rates " + ", ".join(sorted(keys)) + ".")
    return out


# ---------------------------------------------------------------- the pack's starting tables
class RateVersion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    valid_from: date
    valid_to: date | None = None
    values: dict[str, dict[str, float]]  # market -> rate -> value


class TableSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    title: str
    kind: TableKind
    inputs: list[str] = []
    versions: list[RateVersion] = []  # a rate card: its starting versions
    body: dict[str, Any] | None = None  # a decision table: the same JDM graph in every market


class MarketSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    flow: str
    valid_from: date
    markets: dict[str, str]  # market -> currency
    tables: list[TableSpec]

    def table(self, name: str) -> TableSpec:
        for t in self.tables:
            if t.name == name:
                return t
        raise KeyError(f"No table {name}")

    def has(self, name: str) -> bool:
        return any(t.name == name for t in self.tables)


def market_spec(pack_key: str) -> MarketSpec | None:
    """The pack's `valuer.params.market_tables`, or None for a pack without tables."""
    raw = load_pack(pack_key).valuer.params.get("market_tables")
    return MarketSpec.model_validate(raw) if raw else None


def table_title(pack_key: str, name: str) -> str:
    spec = market_spec(pack_key)
    return spec.table(name).title if spec and spec.has(name) else name


@dataclass(frozen=True)
class TableRef:
    """What a priced line cites: the table version it used, e.g. "DE labour rates v1"."""

    pack: str
    flow: str
    market: str
    name: str
    version: int

    def __str__(self) -> str:
        return f"{self.market} {table_title(self.pack, self.name)} v{self.version}"
