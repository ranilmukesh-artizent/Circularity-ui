"""P9-12.4 (story NS-RC-01): the rental fleet pack values re-rent, rebuild and sale routes of an off-rent machine on the
standard valuer (P9-12.1). RF-S1 is an excavator 20 t, 6,200 h, 8 years old, branch BR-1 (utilisation 0.72), book value
52,000. Pure: sample facts and the pack in, `PathValue`s out. Synthetic data."""

from typing import Any

import pytest

from di.services.modeler.pack import load_pack
from di.services.modeler.valuers import standard

PACK = load_pack("rental_fleet")


def case_of(sample: str) -> dict[str, Any]:
    """The facts of a replay sample as the nested case the valuer reads."""
    ex = PACK.replay.example
    assert ex is not None
    facts = next(s["facts"] for s in ex["samples"] if s["id"] == sample)
    case: dict[str, Any] = {"cls": facts["asset.asset_class"]}
    for k, v in facts.items():
        model, _, field = k.partition(".")
        case.setdefault(model, {})[field] = v
    return case


def by_k(case: dict[str, Any]) -> dict[str, Any]:
    return {v["k"]: v for v in standard.value_routes(case, PACK)}


def test_ns_rc_01_rerent_rebuild_sell():
    v = by_k(case_of("RF-S1"))
    assert list(v) == ["rerent", "rebuild", "transfer_branch", "retail", "auction", "dealer", "parts", "scrap"]
    assert (v["rerent"]["ok"], v["rerent"]["net"]) == (True, pytest.approx(27600.00))
    assert (v["rebuild"]["ok"], v["rebuild"]["net"]) == (True, pytest.approx(-6800.00))
    assert (v["retail"]["ok"], v["retail"]["net"]) == (True, pytest.approx(6270.00))
    d = standard.decide(case_of("RF-S1"), PACK, [])
    assert d["best"]["k"] == "rerent"


def test_ns_rc_01_rebuild_needs_age_and_transfer_needs_a_purchase_plan():
    young = case_of("RF-S1")
    young["asset"]["age_years"] = 5
    v = by_k(young)
    assert v["rebuild"]["ok"] is False and v["rebuild"]["why"]
    assert v["transfer_branch"]["ok"] is False  # RF-S1 has no purchase plan at another branch
    assert by_k(case_of("RF-S3"))["transfer_branch"]["ok"] is True
