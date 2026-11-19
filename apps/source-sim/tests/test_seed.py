"""B2 parity: the seed holds exactly the demo's world (docs/BACKEND_STEPS.md)."""

from datetime import UTC, datetime

import pytest

from sim.registry import SYSTEMS, VENDOR_OVERRIDES
from sim.seed import golden, seed


@pytest.fixture(scope="module")
def s():
    return seed()


def test_counts(s):
    assert len(s.cases) == 128
    assert list(s.cases)[0] == "RT-1001" and list(s.cases)[-1] == "RT-1128"
    assert len(s.decisions) == 1400
    assert len(s.sources) == 21


def test_world(s):
    w = s.world
    assert w.as_of == datetime(2026, 10, 7, 9, 0, tzinfo=UTC)
    assert w.tenants == ["Customer A", "Customer B", "Customer C"]
    assert len(w.sites) == 8 and len(w.gates) == 6 and len(w.routes) == 7
    assert set(w.classes) == {"motor", "pump", "control", "drill", "batch", "it"}


def test_no_unresolved_refs():
    def walk(n):
        if isinstance(n, dict):
            assert "$ref" not in n
            for v in n.values():
                walk(v)
        elif isinstance(n, list):
            for v in n:
                walk(v)

    for name in ("world", "cases", "decisions", "sources"):
        walk(golden.load(name))


def test_every_route_net_is_the_sum_of_its_lines(s):
    """The demo's invariant 'Every route net equals the sum of its cost and value lines', on the seed's facts."""
    for case in s.cases.values():
        assert len(case.facts.routes) == len(case.results.routes)
        for fact, result in zip(case.facts.routes, case.results.routes, strict=True):
            assert fact.id == result.id
            assert fact.net == pytest.approx(result.net, abs=0.01), (case.facts.id, fact.id, fact.variant)


def test_two_routes_can_share_an_id(s):
    """RT-1049 has two resale routes (as is: $186, refurbished: $171); the recommendation is the first."""
    c = s.cases["RT-1049"]
    resale = [r for r in c.facts.routes if r.id == "resale"]
    assert sorted(r.net for r in resale) == [171, 186]
    assert c.facts.routes[c.results.recommendation].net == 186


def test_rt_1048_matches_the_demo(s):
    c = s.cases["RT-1048"]
    f = c.facts
    assert (f.asset_id, f.cls, f.owner, f.location, f.grade, f.mfr) == (
        "MTR-2041",
        "motor",
        "Customer A",
        "Warehouse 1",
        "B",
        "Voltara",
    )
    assert f.demand.site == "Site 3" and f.demand.confirmed
    redeploy = next(r for r in f.routes if r.id == "redeploy")
    assert [(t.label, t.amt) for t in redeploy.terms] == [
        ("Avoided equivalent purchase", 12000),
        ("Preparation and transfer", -1800),
        ("Service exposure (30 months)", -900),
        ("Residual value adjustment", 300),
    ]
    assert redeploy.net == 9600
    rr = c.results.routes[c.results.recommendation]
    assert rr.id == "redeploy"
    assert (rr.p10, rr.p90, rr.rank, rr.gates) == (8371, 10608, 1, ["pass"] * 6)
    assert c.state.stage == "awaiting_approval"


def test_stage_split_matches_the_demo(s):
    stages: dict[str, int] = {}
    for c in s.cases.values():
        stages[c.state.stage] = stages.get(c.state.stage, 0) + 1
    assert stages == {"awaiting_approval": 41, "reeval": 8, "executing": 31, "none": 41, "approved": 7}


def test_recommendation_is_the_top_ranked_eligible_route(s):
    for c in s.cases.values():
        if c.results.recommendation is None:
            continue
        rec = c.results.routes[c.results.recommendation]
        assert not rec.excluded and rec.rank == 1, c.facts.id


def test_closed_decisions(s):
    assert {d.status for d in s.decisions} >= {"reconciled"}
    assert sum(1 for d in s.decisions if d.status == "reconciled") == 1277  # README section 3
    assert all(0 <= d.mi < len(s.world.months) for d in s.decisions)


def test_sources_match_the_registry(s):
    assert {x["id"] for x in s.sources} == {sys.source_id for sys in SYSTEMS}
    by_id = {x["id"]: x for x in s.sources}
    for sys in SYSTEMS:
        assert VENDOR_OVERRIDES.get(sys.source_id, by_id[sys.source_id]["vendor"]) == sys.vendor, sys.source_id
