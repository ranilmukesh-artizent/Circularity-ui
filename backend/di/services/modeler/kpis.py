"""Pack KPIs and analytics questions as data (plan 9, P9-1.13, story X-09; research B section 7.2 part 12).

A pack's `kpis[].measure` and `analytics[].query` are JSON, computed here over case documents; no page and no route
knows a KPI by name, so a new pack's KPIs are served with no code.

The measure grammar: `{kind: "share" | "avg" | "count" | "sum", of, where, over, unit?, scale?}`.
- `where`: conditions (`{fact, op, value}`, the ops of a gate's trigger) a case must meet; all of them.
- `over`: conditions that make the share's denominator (a share is the cases that meet `where` among those that meet
  `over`, in percent); `where` and `over` default to every case.
- `of` (avg and sum): a dotted path into the case, or `"a / b"` for the ratio of two paths (a case where either is
  missing, or b is zero, is left out).
- `scale` multiplies the value (default 1; a share is already in percent) and `unit` names it (a share is `%`).
- Facts a case does not hold itself, derived here: `held_by_guardrails` (true when `gateHold` is set or a gate failed)
  and `evidence_result.<type>` (the result of the newest evidence record of that type).
A value is None ("No data yet") when no case meets the measure. `compute(kpi, cases)` also gives a trend: one value per
week or month of `received`.

Owns: the grammar and its arithmetic. Never does: read a session, a pack file or the clock, or write anything. The screens
pass the pack and the cases it may show. Implements nothing in the registry; I-1's `Kpi` and `AnalyticsQuestion` carry
the data.
"""

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any

from di.services.modeler.pack import AnalyticsQuestion, Kpi, Pack

KINDS = ("share", "avg", "count", "sum")
OPS = ("eq", "ne", "in", "gte", "lte", "exists")
EXAMPLES = 5


class KpiError(ValueError):
    """A measure or query the grammar does not accept."""


def _lookup(doc: Any, path: str) -> Any:
    cur = doc
    for part in path.split("."):
        if not isinstance(cur, Mapping) or part not in cur:
            return None
        cur = cur[part]
    return cur


def _num(v: Any) -> float | None:
    return float(v) if isinstance(v, int | float) and not isinstance(v, bool) else None


def facts_of(case: Mapping[str, Any]) -> dict[str, Any]:
    """The case with the derived facts of the module docstring."""
    newest: dict[str, tuple[str, Any]] = {}
    for r in case.get("evidenceRecords") or []:
        if isinstance(r, Mapping) and isinstance(r.get("type"), str):
            at = str(r.get("at") or "")
            if r["type"] not in newest or at >= newest[r["type"]][0]:
                newest[r["type"]] = (at, r.get("result"))
    failed = any(isinstance(g, Mapping) and g.get("passed") is False for g in case.get("gates") or [])
    return {
        **case,
        "held_by_guardrails": case.get("gateHold") is not None or failed,
        "evidence_result": {t: v[1] for t, v in newest.items()},
    }


def _holds(cond: Mapping[str, Any], facts: Mapping[str, Any]) -> bool:
    v, want, op = _lookup(facts, cond["fact"]), cond.get("value"), cond["op"]
    if op == "exists":
        return (v is not None) is (want is not False)
    if op == "ne":
        return bool(v != want)
    if v is None:
        return False
    try:
        if op == "eq":
            return bool(v == want)
        if op == "in":
            return bool(v in (want or ()))
        return bool(v >= want) if op == "gte" else bool(v <= want)
    except TypeError:
        return False


def _conds(raw: Any, where: str) -> list[Mapping[str, Any]]:
    if raw is None:
        return []
    ok = isinstance(raw, list) and all(
        isinstance(c, dict) and isinstance(c.get("fact"), str) and c.get("op") in OPS and set(c) <= {"fact", "op", "value"}
        for c in raw
    )
    if not ok:
        raise KpiError(f"{where} is a list of conditions (fact, op, value)")
    return list(raw)


def _all(conds: Sequence[Mapping[str, Any]], facts: Mapping[str, Any]) -> bool:
    return all(_holds(c, facts) for c in conds)


def _of(facts: Mapping[str, Any], of: str) -> float | None:
    top, sep, bottom = of.partition(" / ")
    a = _num(_lookup(facts, top.strip()))
    if not sep:
        return a
    b = _num(_lookup(facts, bottom.strip()))
    return None if a is None or not b else a / b


def check_measure(measure: Mapping[str, Any]) -> None:
    """KpiError unless the measure follows the grammar."""
    if measure.get("kind") not in KINDS:
        raise KpiError(f"A measure's kind is one of {', '.join(KINDS)}")
    extra = set(measure) - {"kind", "of", "where", "over", "unit", "scale"}
    if extra:
        raise KpiError(f"A measure has no {sorted(extra)[0]}")
    if measure["kind"] in ("avg", "sum") and not isinstance(measure.get("of"), str):
        raise KpiError(f"A {measure['kind']} measure needs `of`, a path in the case")
    _conds(measure.get("where"), "where")
    _conds(measure.get("over"), "over")
    scale = measure.get("scale", 1)
    if _num(scale) is None:
        raise KpiError("A measure's scale is a number")


def _value(measure: Mapping[str, Any], cases: Sequence[Mapping[str, Any]]) -> float | None:
    check_measure(measure)
    where, over = _conds(measure.get("where"), "where"), _conds(measure.get("over"), "over")
    kind, scale = measure["kind"], float(measure.get("scale", 1))
    facts = [facts_of(c) for c in cases]
    if kind == "share":
        base = [f for f in facts if _all(over, f)]
        return round(100 * sum(1 for f in base if _all(where, f)) / len(base) * scale, 2) if base else None
    hit = [f for f in facts if _all(where, f)]
    if kind == "count":
        return round(len(hit) * scale, 2) if facts else None
    vals = [v for f in hit if (v := _of(f, str(measure["of"]))) is not None]
    if not vals:
        return None
    return round((sum(vals) if kind == "sum" else sum(vals) / len(vals)) * scale, 2)


def _unit(measure: Mapping[str, Any] | None) -> str:
    if not measure:
        return ""
    return str(measure.get("unit") or ("%" if measure.get("kind") == "share" else ""))


def _bucket(received: Any, every: str) -> str | None:
    try:
        at = datetime.fromisoformat(str(received).replace("Z", "+00:00"))
    except ValueError:
        return None
    if every == "weekly":
        iso = at.isocalendar()
        return f"{iso.year}-W{iso.week:02d}"
    return f"{at.year}-{at.month:02d}"


def _trend(measure: Mapping[str, Any], cases: Sequence[Mapping[str, Any]], every: str) -> list[dict[str, Any]]:
    groups: dict[str, list[Mapping[str, Any]]] = {}
    for c in cases:
        if (b := _bucket(c.get("received"), every)) is not None:
            groups.setdefault(b, []).append(c)
    points = [{"period": p, "value": _value(measure, groups[p])} for p in sorted(groups)]
    return [x for x in points if x["value"] is not None]


def compute(kpi: Kpi, cases: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """`{value, unit, trend}` of the KPI over the cases. KpiError for a measure the grammar refuses; a KPI with no measure
    has no value (the pack says so, the page shows "No data yet")."""
    if kpi.measure is None:
        return {"value": None, "unit": "", "trend": []}
    trend = _trend(kpi.measure, cases, kpi.trend) if kpi.trend else []
    return {"value": _value(kpi.measure, cases), "unit": _unit(kpi.measure), "trend": trend}


def kpi_rows(pack: Pack, cases: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """The pack's KPIs as the screens show them: id, label, definition, value, unit, trend and `error` (the grammar's refusal
    of a measure, else None). A KPI whose measure is refused shows no value; the others are served."""
    if pack.valuer.kind == "industrial":  # the demo's own pages carry its numbers: the pack's KPIs describe them, parity first
        return []
    out: list[dict[str, Any]] = []
    for k in pack.kpis:
        try:
            got, error = compute(k, cases), None
        except KpiError as e:
            got, error = {"value": None, "unit": _unit(k.measure), "trend": []}, str(e)
        out.append({"id": k.id, "label": k.label, "definition": k.definition, **got, "error": error})
    return out


def question(q: AnalyticsQuestion, cases: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """The answer to one analytics question: `rows` of `{key, value}` (one per value of the `group_by` path, sorted by key;
    the measure defaults to a count) and up to five `examples`, case ids of the first rows. A question with no query has
    neither."""
    out: dict[str, Any] = {"question": q.question, "chart": q.chart, "rows": [], "examples": []}
    if not q.query:
        return out
    path, measure = q.query.get("group_by"), q.query.get("measure") or {"kind": "count"}
    if not isinstance(path, str):
        raise KpiError("A question's query has `group_by`, a path in the case")
    check_measure(measure)
    groups: dict[str, list[Mapping[str, Any]]] = {}
    for c in cases:
        key = _lookup(facts_of(c), path)
        groups.setdefault("none" if key is None else str(key), []).append(c)
    for key in sorted(groups):
        value = _value(measure, groups[key])
        if value is not None:
            out["rows"].append({"key": key, "value": value})
            out["examples"].extend(str(c.get("id")) for c in groups[key] if str(c.get("id")) not in out["examples"])
    out["examples"] = out["examples"][:EXAMPLES]
    return out


def question_rows(pack: Pack, cases: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """The pack's questions answered over the cases; one the grammar refuses has no rows."""
    if pack.valuer.kind == "industrial":  # as `kpi_rows`: the demo's Analytics page answers its own questions
        return []
    out = []
    for q in pack.analytics:
        try:
            out.append(question(q, cases))
        except KpiError:
            out.append({"question": q.question, "chart": q.chart, "rows": [], "examples": []})
    return out
