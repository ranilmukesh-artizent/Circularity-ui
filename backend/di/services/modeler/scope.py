"""Is a case in a rule's scope (Domain spec D4; the prototype's inScope and dIn, generalised over a template's dims)?

- `set`: the rule's list is empty (any) or holds the case's value;
- `max`: the case's value is below the rule's; `min`: at or above it. An empty bound ("" or None) is no bound.
"""

from collections.abc import Mapping, Sequence
from typing import Any

from di.services.modeler.templates import ScopeDim


def _get(case: Mapping[str, Any], dotted: str) -> Any:
    node: Any = case
    for part in dotted.split("."):
        if not isinstance(node, Mapping):
            return None
        node = node.get(part)
    return node


def case_value(case: Mapping[str, Any], dim: ScopeDim) -> Any:
    """The case's value for a dim: the first of its fields that is set (JavaScript's `a || b`), else the last."""
    fields = dim.case_fields()
    for f in fields[:-1]:
        v = _get(case, f)
        if v:
            return v
    return _get(case, fields[-1])


def _number(v: Any) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def in_scope(case: Mapping[str, Any], scope: Mapping[str, Any], dims: Sequence[ScopeDim]) -> bool:
    for d in dims:
        want = scope.get(d.key)
        if d.kind == "set":
            if want and case_value(case, d) not in want:
                return False
            continue
        if want is None or want == "":
            continue
        bound, v = _number(want), _number(case_value(case, d))
        if bound is None or v is None or not (v < bound if d.kind == "max" else v >= bound):
            return False
    return True
