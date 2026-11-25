"""Market decision tables as DMN decisions (plan 9, P9-8.21; the tables of registry entry I-15, a GoRules JDM graph).

Owns: `Table` (what the export needs of a stored decision table), `table_decision_id`, and `add_table_decision`, which
turns a table into its own DMN decision when it is one decision table node whose input and output cells are unary tests or
literals on plain field names, and otherwise answers why it is not exportable (the caller lists that in an annotation).
Never does: read the database (the export action loads the tables), run a table (di.services.modeler.tables) or judge
a table's business meaning.
"""

import re
import xml.etree.ElementTree as ET
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from di.services.modeler.dmn_table import ANY, Column, Row, add_decision
from di.services.modeler.export_xml import ncname

_NUM = r"-?\d+(?:\.\d+)?"
_LIT = rf'(?:"(?:[^"\\]|\\.)*"|{_NUM}|true|false)'
_CMP = rf"(?:(?:<=|>=|<|>)\s*{_NUM})"
_UNARY = re.compile(rf"(?:{_LIT}|{_CMP})(?:\s*,\s*(?:{_LIT}|{_CMP}))*")
_LITERAL = re.compile(_LIT)
_FIELD = re.compile(r"[A-Za-z_]\w*")
_HIT = {"first": "FIRST", "collect": "COLLECT"}


@dataclass(frozen=True)
class Table:
    name: str
    title: str
    market: str
    version: int
    body: Mapping[str, Any]  # the JDM graph


def table_decision_id(t: Table) -> str:
    return ncname("table", t.name, t.market, f"v{t.version}")


def _type_of(cells: list[str]) -> str:
    joined = " ".join(cells)
    if re.search(r"[<>]|(?<![\w\"])-?\d", joined):
        return "number"
    return "boolean" if re.search(r"\b(true|false)\b", joined) else "string"


def _node(body: Mapping[str, Any]) -> tuple[dict[str, Any] | None, str]:
    nodes = [n for n in body.get("nodes") or [] if isinstance(n, dict)]
    kinds = sorted(str(n.get("type")) for n in nodes)
    if kinds != ["decisionTableNode", "inputNode", "outputNode"]:
        return None, "it is not one decision table between an input and an output"
    c = next(n for n in nodes if n["type"] == "decisionTableNode").get("content")
    return (c, "") if isinstance(c, dict) else (None, "its table has no content")


def add_table_decision(root: ET.Element, t: Table) -> str | None:
    """Write the table as a decision; None when written, else the reason it cannot be."""
    c, why = _node(t.body)
    if c is None:
        return why
    if c.get("hitPolicy") not in _HIT:
        return "its hit policy is not first or collect"
    ins, outs = list(c.get("inputs") or []), list(c.get("outputs") or [])
    if not ins or not outs or any(not _FIELD.fullmatch(str(x.get("field") or "")) for x in [*ins, *outs]):
        return "a column reads more than a plain field"
    rules = [r for r in c.get("rules") or [] if isinstance(r, dict)]
    cells_in = [[str(r.get(x["id"]) or "").strip() or ANY for r in rules] for x in ins]
    cells_out = [[str(r.get(x["id"]) or "").strip() for r in rules] for x in outs]
    if any(x != ANY and not _UNARY.fullmatch(x) for col in cells_in for x in col):
        return "a cell is more than a unary test"
    if any(not _LITERAL.fullmatch(x) for col in cells_out for x in col):
        return "an output is more than a literal"
    rows = [
        Row(str(r.get("_id") or n), [col[n] for col in cells_in], [col[n] for col in cells_out], f"Row {r.get('_id') or n + 1}")
        for n, r in enumerate(rules)
    ]  # fmt: skip
    add_decision(
        root, table_decision_id(t), f"{t.title} {t.market} v{t.version}",
        f"The {t.title} of market {t.market}, version {t.version}: hit policy {_HIT[c['hitPolicy']].lower()}.",
        _HIT[c["hitPolicy"]],
        [Column(str(x.get("name") or x["field"]), x["field"], _type_of(col)) for x, col in zip(ins, cells_in, strict=True)],
        [Column(str(x.get("name") or x["field"]), x["field"], _type_of(col)) for x, col in zip(outs, cells_out, strict=True)],
        rows, "Row",
    )  # fmt: skip
    return None
