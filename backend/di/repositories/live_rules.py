"""The business rules a case is evaluated with now (plan 8, MVP-3.3): the compiled published graph of the flow its
owner uses (di.repositories.flows.flow_for: the nearest org unit with a flow, up to `workspace`).

It reads the database, so it lives here and not in the pure di.services.modeler. The seeded industrial default has no
rule nodes and offers every route, so it compiles to no rules and the demo's cases evaluate exactly as before.

Scope facts (MVP-7.1): before the rules are read, the case gets the facts a rule may be scoped on that it does not hold
itself (di.services.modeler.facts: `alarm` from the asset's latest telemetry in the canonical `condition` record). They
are set on the case in place, so the evaluation that follows and the saved case carry the facts it was evaluated with;
with no telemetry the case has none (the demo's starting state: iot is not provisioned).
"""

from collections.abc import Mapping, MutableMapping
from dataclasses import dataclass
from typing import Any, cast

from sqlalchemy.orm import Session

from di.repositories.flows import flow_for
from di.services.canonical import store as canonical
from di.services.modeler.compile import CompiledRule, compile_flow
from di.services.modeler.facts import FACT_KEYS, TELEMETRY_FIELDS, case_scope_facts
from di.services.modeler.flow import Flow
from di.services.modeler.templates import Template, load_template


def template_of(case: Mapping[str, Any]) -> Template:
    return load_template(case.get("template") or "industrial")


def telemetry(s: Session, case: Mapping[str, Any]) -> dict[str, Any] | None:
    """The telemetry fields of the case's asset's canonical condition record (None: no asset or no telemetry)."""
    asset = case.get("assetId")
    rec = canonical.get(s, "condition", asset) if asset else None
    data = (rec or {}).get("data") or {}
    got = {f: data[f] for f in TELEMETRY_FIELDS if f in data}
    return got or None


def refresh_scope_facts(s: Session, case: MutableMapping[str, Any]) -> None:
    """Set the case's scope facts in place (and drop facts it no longer has)."""
    facts = case_scope_facts(case, telemetry(s, case))
    for k in FACT_KEYS:
        if k in facts:
            case[k] = facts[k]
        else:
            case.pop(k, None)


def live_rules(s: Session, case: MutableMapping[str, Any]) -> tuple[Template, list[CompiledRule], int]:
    """(the case's template, the compiled rules of its flow's published graph, that flow's `ver`); no flow: no rules,
    version 0. Refreshes the case's scope facts first."""
    refresh_scope_facts(s, case)
    t = template_of(case)
    f = flow_for(s, t.key, case["owner"])
    if f is None:
        return t, [], 0
    return t, compile_flow(t, cast(Flow, f.published)), f.ver


@dataclass(frozen=True)
class Shadow:
    """A flow approved into shadow (MVP-3.5): its id, the draft's version and the draft's compiled rules."""

    flow_id: int
    dver: int
    rules: list[CompiledRule]


def shadow_rules(s: Session, case: Mapping[str, Any]) -> Shadow | None:
    """The shadow run the case takes part in: its flow is in `shadow`, else None."""
    t = template_of(case)
    f = flow_for(s, t.key, case["owner"])
    if f is None or f.status != "shadow" or f.draft is None:
        return None
    return Shadow(f.id, f.dver or f.ver + 1, compile_flow(t, cast(Flow, f.draft)))
