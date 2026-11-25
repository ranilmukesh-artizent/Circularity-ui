"""One DMN decision with a decision table (plan 9, P9-8.21; DMN 1.3 `decision`, `decisionTable`, `input`, `output`, `rule`).

Owns: `DmnNs` (the DMN 1.3 namespace), `Column`, `Row` and `add_decision`, which writes one `<decision>` with its
`<decisionTable>` into a `<definitions>` element. Entries are FEEL unary tests text already (`"D"`, `>= 80`, `-` for any).
Never does: decide what a row says (`export_dmn` for rules and guardrails, `export_tables` for I-15 tables) or serialize.
"""

import xml.etree.ElementTree as ET
from collections.abc import Sequence
from dataclasses import dataclass

from di.services.modeler.export_xml import ncname, sub

DmnNs = "https://www.omg.org/spec/DMN/20191111/MODEL/"
ANY = "-"  # the FEEL "irrelevant" unary test


@dataclass(frozen=True)
class Column:
    name: str  # the label, and for an output its name
    expr: str  # an input's FEEL expression (the field it reads); unused for an output
    type_ref: str = "string"


@dataclass(frozen=True)
class Row:
    id: str
    inputs: Sequence[str]  # one unary test per input column
    outputs: Sequence[str]  # one FEEL literal per output column
    note: str = ""


def feel_str(v: object) -> str:
    return '"' + str(v).replace("\\", "\\\\").replace('"', '\\"') + '"'


def add_decision(
    root: ET.Element, did: str, name: str, description: str, hit: str, inputs: Sequence[Column], outputs: Sequence[Column],
    rows: Sequence[Row], note_header: str,
) -> ET.Element:  # fmt: skip
    """A decision with a decision table of hit policy `hit` (FIRST or COLLECT); each row's note is an annotation entry."""
    d = sub(root, "decision", id=ncname(did), name=name)
    sub(d, "description", description)
    sub(d, "variable", id=ncname(did, "var"), name=name)
    t = sub(d, "decisionTable", id=ncname(did, "table"), hitPolicy=hit)
    for i, c in enumerate(inputs, 1):
        col = sub(t, "input", id=ncname(did, "in", i), label=c.name)
        e = sub(col, "inputExpression", id=ncname(did, "in", i, "expr"), typeRef=c.type_ref)
        sub(e, "text", c.expr)
    for i, c in enumerate(outputs, 1):
        sub(t, "output", id=ncname(did, "out", i), name=c.name, label=c.name, typeRef=c.type_ref)
    sub(t, "annotation", name=note_header)
    for r in rows:
        el = sub(t, "rule", id=ncname(did, "rule", r.id))
        for i, x in enumerate(r.inputs, 1):
            sub(sub(el, "inputEntry", id=ncname(did, r.id, "in", i)), "text", x)
        for i, x in enumerate(r.outputs, 1):
            sub(sub(el, "outputEntry", id=ncname(did, r.id, "out", i)), "text", x)
        sub(sub(el, "annotationEntry"), "text", r.note)
    return d
