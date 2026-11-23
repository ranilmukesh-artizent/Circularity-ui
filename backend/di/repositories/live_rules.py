"""The business rules a case is evaluated with now (plan 8, MVP-3.3): the compiled published graph of the flow its
owner uses (di.repositories.flows.flow_for: the nearest org unit with a flow, up to `workspace`).

It reads the database, so it lives here and not in the pure di.services.modeler. The seeded industrial default has no
rule nodes and offers every route, so it compiles to no rules and the demo's cases evaluate exactly as before.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, cast

from sqlalchemy.orm import Session

from di.repositories.flows import flow_for
from di.services.modeler.compile import CompiledRule, compile_flow
from di.services.modeler.flow import Flow
from di.services.modeler.templates import Template, load_template


def template_of(case: Mapping[str, Any]) -> Template:
    return load_template(case.get("template") or "industrial")


def live_rules(s: Session, case: Mapping[str, Any]) -> tuple[Template, list[CompiledRule], int]:
    """(the case's template, the compiled rules of its flow's published graph, that flow's `ver`); no flow: no rules,
    version 0."""
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
