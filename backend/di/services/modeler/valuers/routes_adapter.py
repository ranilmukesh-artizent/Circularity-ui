"""A template case's valuer output as the engine's routes (plan 8, MVP-6.4), so `rank_routes` gives the recommendation.

- Tool fleet (`PathValue`): one term per value line; values positive, costs and holding negative, so the route's net
  is the valuer's net; the route keeps the valuer's `dest` (who takes the tool, the order's `id`). Term kinds follow
  `_KINDS` (tests/test_routes_adapter.py states the table).
- Device (`ChannelValue`): the expected cash a unit (`sale`) and the penalty for days past the service level (`risk`),
  so the route's net is the channel's score.
A path the valuer (or a business rule) leaves out fails at gate 2 (Policy & certification) with the valuer's reason.
Pure: no Session, no I/O.
"""

from collections.abc import Sequence
from typing import Any, cast

from di.services.engine.routes import POLICY, Route, fail, mk_route
from di.services.modeler.templates import Template
from di.services.modeler.valuers.device import ChannelValue
from di.services.modeler.valuers.tool_fleet import PathValue, ValueLine

# (paths or None for any, line type, label prefixes or None for any) -> term kind; the first match wins.
_KINDS: tuple[tuple[frozenset[str] | None, str, tuple[str, ...] | None, str], ...] = (
    (frozenset({"release", "refurb"}), "v", ("Fleet renewal", "New fleet order"), "lease"),
    (frozenset({"release", "refurb"}), "v", ("Value when the contract ends", "Sales order"), "sale"),
    (frozenset({"redeploy"}), "v", None, "purchase"),
    (frozenset({"resell"}), "v", None, "sale"),
    (frozenset({"harvest"}), "v", ("Residual material",), "material"),
    (frozenset({"harvest"}), "v", None, "parts"),
    (frozenset({"exit"}), "v", None, "material"),
    (None, "c", ("Ship to", "Inbound", "Channel fees", "Listing", "Recycling"), "fees"),
    (None, "c", ("Repairs covered",), "risk"),
    (None, "c", None, "prep"),
    (None, "h", None, "fees"),
)


def _kind(path: str, line: ValueLine) -> str:
    for paths, type_, prefixes, kind in _KINDS:
        if (
            (paths is None or path in paths)
            and line["type"] == type_
            and (prefixes is None or line["label"].startswith(prefixes))
        ):
            return kind
    raise ValueError(f"no term kind for {path} {line['type']} line {line['label']!r}")


def _term(label: str, amt: float, kind: str) -> dict[str, Any]:
    return {"label": label, "amt": amt, "kind": kind}


def _terms(v: PathValue | ChannelValue) -> list[dict[str, Any]]:
    if "lines" in v:  # a tool-fleet path (the TypedDicts are not final, so mypy does not narrow on `in`)
        pv = cast(PathValue, v)
        return [_term(x["label"], x["amt"] if x["type"] == "v" else -x["amt"], _kind(pv["k"], x)) for x in pv["lines"]]
    return [
        _term("Expected cash a unit", v["cash"], "sale"),
        _term("Days past the service level", v["score"] - v["cash"], "risk"),
    ]


def to_routes(t: Template, values: Sequence[PathValue | ChannelValue]) -> list[Route]:
    """The engine's route dicts (`mk_route`), one per value, in the valuer's order: `id` the path, `plan` its name."""
    out = []
    for v in values:
        p = t.path(v["k"])
        name = p.name if p else v["k"]
        r = mk_route({"id": v["k"], "plan": name, "terms": _terms(v), "why": v["why"]})
        r["co2"] = v["co2"]
        r["co2Src"] = v["co2Src"]
        if "lines" in v:  # a tool-fleet route carries its destination (the named order it fills), P9-1.4
            r["dest"] = cast(PathValue, v)["dest"]
        if not v["ok"]:
            fail(r, POLICY, v["why"] or f"{name} cannot take this lot")
        out.append(r)
    return out
