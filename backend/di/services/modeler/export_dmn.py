"""A flow as DMN 1.3 XML (plan 9, P9-8.21; enabler E 8.2 "DMN export"). Pure: no session, no I/O, standard library only.

Owns: `to_dmn`, `decision_id` and `Table` (re-exported). The file holds, in this order:
- one decision with a decision table, hit policy FIRST: the inputs are the pack's scope dimensions, the outputs the path and
  the action, the rows the compiled rules in order, then a default row that is the waive-all fallback (when the rules leave
  no route eligible the engine waives them);
- one decision with the pack's guardrails (hit policy COLLECT), each annotated "locked, owner <role>" or "owner <role>";
- one decision for each market decision table (registry entry I-15) that is unary on plain fields; the others are listed in
  the first decision's description as "not exportable".
Never does: read a flow or a table from the database, validate against an XSD (none is installed; the tests read the
structure), import DMN, or carry what DMN has no form for: locked stages, scopes beyond the inputs, shadow runs (the
description says so).
"""

import xml.etree.ElementTree as ET
from collections.abc import Sequence
from typing import Any

from di.services.modeler.compile import CompiledRule
from di.services.modeler.dmn_table import ANY, Column, DmnNs, Row, add_decision, feel_str
from di.services.modeler.export_tables import Table, add_table_decision
from di.services.modeler.export_xml import ncname, serialize, sub
from di.services.modeler.flow import Flow
from di.services.modeler.pack import Pack
from di.services.modeler.templates import ScopeDim, template_of_pack

__all__ = ["Table", "decision_id", "to_dmn"]

WAIVER = "Waive-all fallback: when the rules leave no route eligible they are waived and the decision engine chooses."
LOSSY = (
    "Exported from the Modeler. The export is lossy by design: locked stages, scope fields beyond the inputs shown and "
    "shadow runs have no DMN form."
)


def decision_id(pack: Pack) -> str:
    """The id of the decision that holds the flow's rules (the BPMN business rule task refers to it)."""
    return ncname("decision", pack.key)


def _number(v: Any) -> str | None:
    try:
        return format(float(v), "g")
    except (TypeError, ValueError):
        return None


def _entry(d: ScopeDim, scope: dict[str, Any]) -> str:
    want = scope.get(d.key)
    if d.kind == "set":
        return ", ".join(feel_str(x) for x in want) if want else ANY
    n = _number(want)
    return ANY if n is None else (f"< {n}" if d.kind == "max" else f">= {n}")


def to_dmn(pack: Pack, flow: Flow, compiled: Sequence[CompiledRule], tables: Sequence[Table]) -> str:
    dims = template_of_pack(pack).dims
    root = ET.Element("definitions", {"xmlns": DmnNs})
    root.set("id", ncname("definitions", pack.key))
    root.set("name", f"{pack.name} decisions")
    root.set("namespace", f"https://circularity.example/dmn/{pack.key}")
    skipped: list[str] = []
    rules_el = ET.Element("holder")  # the rules decision goes first, but its description needs the skipped tables
    rows = [Row(f"{n}_{c.id}", [_entry(d, c.scope) for d in dims], [feel_str(c.path), feel_str(c.action)], f"{c.id}: {c.text}")
            for n, c in enumerate(compiled, 1)]  # fmt: skip
    rows.append(Row("default", [ANY] * len(dims), ['""', feel_str("waive")], WAIVER))
    tables_el = ET.Element("holder")
    for t in tables:
        if (why := add_table_decision(tables_el, t)) is not None:
            skipped.append(f"{t.title} {t.market} v{t.version} ({why})")
    locked = sum(1 for n in flow["nodes"] if n.get("lock"))
    desc = f"{LOSSY} {locked} locked steps are left out. {WAIVER}"
    if skipped:
        desc += " Not exportable: " + "; ".join(skipped) + "."
    add_decision(
        rules_el, decision_id(pack), f"{pack.name} business rules", desc, "FIRST",
        [Column(d.label, d.key, "number" if d.kind != "set" else "string") for d in dims],
        [Column("path", "path"), Column("action", "action")], rows, "Rule",
    )  # fmt: skip
    guards = [
        Row(g.id, [feel_str(g.stage)], [feel_str(g.id), feel_str(g.text)],
            f"locked, owner {g.owner}" if g.locked else f"owner {g.owner}, not locked")
        for g in pack.guardrails
    ]  # fmt: skip
    add_decision(
        rules_el, ncname("decision", pack.key, "guardrails"), f"{pack.name} guardrails",
        "Guardrails the decision gate enforces. A guardrail marked locked is changed only by its owner.", "COLLECT",
        [Column("Stage", "stage")], [Column("guardrail", "guardrail"), Column("text", "text")], guards, "Guardrail",
    )  # fmt: skip
    root.extend([*rules_el, *tables_el])
    ta = sub(root, "textAnnotation", id=ncname("note", pack.key))
    sub(ta, "text", LOSSY)
    return serialize(root)
