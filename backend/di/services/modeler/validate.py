"""Checks on a flow before it is submitted (Domain spec D6; the prototype's fValidate). Messages verbatim.

Each check is `(level, message, node_id)`: `ok`, `warn`, or `fail` (blocking). Rules that break a guardrail are
blocked, not warned; conflicting rules (the same path, one excluding, overlapping scopes) are warned.
"""

from collections.abc import Mapping, Sequence
from typing import Any, Literal, NamedTuple

from di.services.modeler.flow import Flow, Node, node_label, reach
from di.services.modeler.guard import rule_breaks
from di.services.modeler.templates import Template
from di.services.modeler.text import rule_text


class Check(NamedTuple):
    level: Literal["ok", "warn", "fail"]
    msg: str
    node_id: str | None


def _first(f: Flow, t: str) -> Node:
    return next(n for n in f["nodes"] if n["t"] == t)


def _overlap(t: Template, a: Mapping[str, Any], b: Mapping[str, Any]) -> bool:
    """Scopes overlap unless some set dimension is limited on both sides to values they do not share."""
    return all(not (a.get(d.key) and b.get(d.key)) or set(a[d.key]) & set(b[d.key]) for d in t.dims if d.kind == "set")


def _path_name(t: Template, k: str) -> str:
    p = t.path(k)
    return p.name if p else k


def _connection_checks(t: Template, f: Flow, everything: set[str]) -> list[Check]:
    trig, gate, apr = _first(f, "trigger"), _first(f, "gate"), _first(f, "approval")
    out: list[Check] = []
    lone = [n for n in f["nodes"] if n["id"] not in everything]
    if lone:
        n = len(lone)
        msg = f"{n} step{'s are' if n > 1 else ' is'} not connected to the flow and will be ignored: "
        out.append(Check("warn", msg + ", ".join(node_label(x, t) for x in lone), lone[0]["id"]))
    else:
        out.append(Check("ok", "Every step is connected from " + trig["label"].lower() + ".", None))
    outs = [n for n in f["nodes"] if n["t"] == "path"]
    no_gate, no_apr = reach(f, trig["id"], gate["id"]), reach(f, trig["id"], apr["id"])
    by_gate = [n for n in outs if n["id"] in no_gate]
    by_apr = [n for n in outs if n["id"] in no_apr]
    if by_gate:
        labels = ", ".join(n["label"] for n in by_gate)
        msg = f"Guardrail bypass: {labels} can be reached without passing the guardrail gate. Remove that connection."
        out.append(Check("fail", msg, by_gate[0]["id"]))
    else:
        out.append(Check("ok", "Every outcome passes the locked guardrail gate.", None))
    if by_apr:
        labels = ", ".join(n["label"] for n in by_apr)
        out.append(Check("fail", f"Approval bypass: {labels} can be reached without owner approval.", by_apr[0]["id"]))
    else:
        out.append(Check("ok", "Every outcome passes owner approval.", None))
    missing = [p.name for p in t.paths if not any(n.get("path") == p.id and n["id"] in everything for n in outs)]
    if missing:
        msg = "Not offered in this flow: " + ", ".join(missing) + ". Removing a path stops Recover from choosing it."
        out.append(Check("warn", msg, None))
    return out


def _rule_checks(t: Template, f: Flow) -> list[Check]:
    dec = _first(f, "decision")
    from_gate = reach(f, _first(f, "gate")["id"])
    out: list[Check] = []
    rules = [n for n in f["nodes"] if n["t"] == "rule"]
    for n in rules:
        rid, g = n.get("rid", ""), rule_breaks(t, n)
        if not n.get("path"):
            out.append(Check("fail", f"{rid} has no path. Pick one in the inspector.", n["id"]))
        elif g:
            gd = next(x for x in t.guardrails if x.id == g)
            msg = f"{rid} breaks {g}: {gd.text} (owner {gd.owner}). Blocked, not warned."
            out.append(Check("fail", msg, n["id"]))
        elif not (n["id"] in from_gate and dec["id"] in reach(f, n["id"])):
            msg = f"{rid} is inactive: it must sit between the guardrail gate and {dec['label'].lower()}."
            out.append(Check("warn", msg, n["id"]))
        else:
            out.append(Check("ok", f"{rid} active: {rule_text(t, n)}.", n["id"]))
    with_path = [n for n in rules if n.get("path")]
    for i, a in enumerate(with_path):
        for b in with_path[i + 1 :]:
            if (
                a.get("path") == b.get("path")
                and a.get("action") != b.get("action")
                and "exclude" in (a.get("action"), b.get("action"))
                and _overlap(t, a.get("scope") or {}, b.get("scope") or {})
            ):
                name = _path_name(t, a.get("path") or "")
                msg = f"Conflict: {a.get('rid')} and {b.get('rid')} pull {name} in opposite directions for overlapping returns."
                out.append(Check("warn", msg, b["id"]))
    return out


def validate_flow(t: Template, f: Flow) -> list[Check]:
    everything = reach(f, _first(f, "trigger")["id"])
    return _connection_checks(t, f, everything) + _rule_checks(t, f)


def blocking(checks: Sequence[Check]) -> list[Check]:
    """The `fail` checks: a flow with any of them cannot be submitted."""
    return [c for c in checks if c.level == "fail"]
