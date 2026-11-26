"""Shared helpers of the ITAD tests (P9-12.3): the pack's own samples `IT-S1` .. `IT-S8` as the case document the decider reads
(nested facts, `cls` the asset class), and one decision under a flow with no rules. Synthetic data only."""

from typing import Any

from di.services.cases.decide import Decision, decide_case
from di.services.modeler.compile import CompiledRule, FlowVersion
from di.services.modeler.pack import Pack, load_pack


def pack() -> Pack:
    return load_pack("itad")


def facts(sample: str) -> dict[str, Any]:
    ex = pack().replay.example
    assert ex is not None
    return dict(next(s["facts"] for s in ex["samples"] if s["id"] == sample))


def nest(flat: dict[str, Any]) -> dict[str, Any]:
    """`{"asset.media": x}` as `{"asset": {"media": x}}`; `cls` is the asset class."""
    out: dict[str, Any] = {"cls": flat["asset.asset_class"]}
    for k, v in flat.items():
        head, _, rest = k.partition(".")
        out.setdefault(head, {})[rest] = v
    return out


def case(sample: str, **over: Any) -> dict[str, Any]:
    c = nest(facts(sample))
    for k, v in over.items():  # `asset__months_in_stock=5`
        head, _, rest = k.partition("__")
        c[head][rest] = v
    return {"id": f"CASE-{sample}", **c}


def decide(c: dict[str, Any], *rules: CompiledRule) -> Decision:
    return decide_case(c, pack(), FlowVersion(None, 1, tuple(rules)))


def route(d: Decision, rid: str) -> dict[str, Any]:
    return next(r for r in d.routes if r["id"] == rid)
