"""Plan 9, P9-3.12 (story TF-07): the six paths valued against live named demand.

The valuer (I-21) values the six paths of a tool; what it values them against is the org's live named demand: the fleet
renewals (`fleet` source) and the parts system's sales orders, pool requests, open repair orders and trade bids (`parts`),
read from the canonical `demand` records by `di.repositories.tool_demand` (never by a language model: no model step here).
A renewal an approved decision holds is not offered to another case. The case panel shows the six rows.
It opens a tool case in its own org unit and starts and ends with the demo reset.
"""

from datetime import UTC, datetime

import pytest
from sqlalchemy import text

from di.core.db import SessionLocal, engine
from di.repositories import tool_demand
from di.services.canonical import store as canonical
from di.services.cases import intake
from di.services.modeler.valuers import tool_fleet
from tests import starting
from tests.helpers import call, client, h, tool_case_facts

ORG = "tool-fleet-p"
SERIAL = "CMH-48213"
OTHER = "CMH-48299"
RENEWAL = "FC-30117-R"
PART = tool_fleet.CLS["CMH"]["parts"][0][0]
AS_OF = datetime(2026, 10, 7, 9, 0, tzinfo=UTC)
KEYS = [RENEWAL, "FC-30101-R", "SO-P1", "RO-P1", "RO-P2", "BID-P1", "TPR-P1"]
# Demand that is not this test's: a synced stack has the fleet contract mock's renewals (no org unit, so every unit sees
# them). The repository test seeds a few of its own and asserts only on the rows it wrote.
_EX = {"site": "Phoenix", "tool_class": "CMH", "buyer": "Extra Co"}
EXTRA = {
    "FC-EXTRA-1-R": (
        "fleet",
        _EX
        | {"kind": "lease", "need_by": "2026-12-05", "lease_rate": 300, "term_months": 6, "renew": True}
        | {"contract_ref": "FC-EXTRA-1"},
    ),
    "SO-EXTRA-1": ("parts", _EX | {"kind": "so", "need_by": "2026-12-22", "price": 999}),
}

DEMAND = {
    RENEWAL: (
        "fleet",
        {
            "kind": "lease",
            "need_by": "2026-12-01",
            "lease_rate": 410,
            "term_months": 12,
            "renew": True,
            "site": "Houston",
            "tool_class": "CMH",
            "buyer": "Brightline Mechanical",
            "contract_ref": "FC-30117",
        },
    ),
    "SO-P1": (
        "parts",
        {
            "kind": "so",
            "need_by": "2026-12-20",
            "price": 2500,
            "site": "Houston",
            "tool_class": "CMH",
            "buyer": "Oakridge Tooling",
        },
    ),
    "RO-P1": (
        "parts",
        {
            "kind": "wo",
            "need_by": "2026-11-20",
            "part_name": PART,
            "backorder": True,
            "tool_class": "CMH",
            "buyer": "Harbor Machining",
        },
    ),
    "RO-P2": (
        "parts",
        {
            "kind": "wo",
            "need_by": "2026-11-25",
            "part_name": PART,
            "backorder": False,
            "tool_class": "CMH",
            "buyer": "Delta Works",
        },
    ),
    "BID-P1": (
        "parts",
        {
            "kind": "bid",
            "expires": "2026-10-20",
            "grade_min": "B",
            "price": 1500,
            "tool_class": "CMH",
            "buyer": "Lakeside Dealers",
        },
    ),
    "TPR-P1": (
        "parts",
        {"kind": "proj", "need_by": "2026-10-25", "amount": 900, "order_ref": "PR-8841", "site": "Houston", "tool_class": "CMH"},
    ),
}


def _facts(key: str, source: str, row: dict) -> list[canonical.Fact]:
    return [canonical.Fact("demand", key, k, v, resource="demand") for k, v in row.items()]


def _write_demand(only: list[str] | None = None, over: dict[str, dict] | None = None) -> None:
    with SessionLocal() as s:
        for key, (src, row) in DEMAND.items():
            if only is None or key in only:
                canonical.apply(s, src, _facts(key, src, row | ((over or {}).get(key) or {})))
        s.commit()


def _write_extra() -> None:
    with SessionLocal() as s:
        for key, (src, row) in EXTRA.items():
            canonical.apply(s, src, _facts(key, src, row))
        s.commit()


def _clear() -> None:
    k = {"k": KEYS + list(EXTRA), "s": [SERIAL, OTHER]}
    with engine.begin() as c:
        for t in ("provenance", "canonical", "conflict"):
            c.execute(text(f"DELETE FROM {t} WHERE model = 'demand' AND key = ANY(:k)"), k)  # noqa: S608
        c.execute(text("DELETE FROM provenance WHERE model = 'condition' AND source_id = 'repairlog' AND key = ANY(:s)"), k)
        c.execute(text("DELETE FROM canonical WHERE model = 'condition' AND key = ANY(:s)"), k)
        c.execute(text("DELETE FROM job WHERE kind = 'case.reevaluate'"))


def _grade_a(serial: str = SERIAL) -> None:
    f = {"grade": "A", "test_result": "pass", "inspection_ref": "DR-60001", "graded_at": "2026-10-07T03:00:00Z"}
    with SessionLocal() as s:
        canonical.apply(s, "repairlog", [canonical.Fact("condition", serial, k, v, resource="orders") for k, v in f.items()])
        s.commit()


def _open(serial: str = SERIAL) -> str:
    with SessionLocal() as s:
        c = intake.open_case(
            s, {"org_unit_id": ORG, "template_key": "tool_fleet", "asset_key": serial, "reason": "contract_end",
                "facts": tool_case_facts(serial, {"tool_class": "CMH", "site": "Houston", "grade": "A"})}, "system")  # fmt: skip
        s.commit()
        return c["id"]


@pytest.fixture(scope="module", autouse=True)
def world():
    starting.reset()
    _clear()
    assert call("org.create", {"id": ORG, "parent_id": "workspace", "kind": "company", "name": "Tool fleet P"}, "admin")["ok"]
    yield
    _clear()
    starting.reset()


@pytest.fixture
def clean():
    _clear()
    with engine.begin() as c:
        c.execute(text("DELETE FROM case_record WHERE owner = :o"), {"o": ORG})
    yield
    _clear()


def _paths(case_id: str, user: str = "admin") -> dict:
    r = client.get(f"/api/screens/toolfleet/{case_id}", headers=h(user))
    assert r.status_code == 200, r.text
    return r.json()


def _by_k(v: dict) -> dict:
    return {p["k"]: p for p in v["paths"]}


# ------------------------------------------------------------------ the repository
def _mine(items: list[dict]) -> list[dict]:
    return [x for x in items if x["id"] in KEYS]


def test_tf_07_named_demand_in_the_valuers_shape(clean):
    _write_demand()
    _write_extra()
    with SessionLocal() as s:
        d = tool_demand.named_demand(s, ORG, "CMH", AS_OF)
        other = tool_demand.named_demand(s, ORG, "BRK", AS_OF)
    # rows that are not this test's (the extras it seeded, a synced stack's renewals) are read too; only ours are asserted
    assert {"FC-EXTRA-1-R", "SO-EXTRA-1"} <= {x["id"] for x in d["lease"] + d["so"]}
    mine = _mine(d["lease"])
    assert [(x["id"], x["who"], x["site"], x["need"], x["rate"], x["term"], x["renew"], x["kind"]) for x in mine] == [
        (RENEWAL, "Brightline Mechanical", "Houston", 55, 410, 12, True, "lease")
    ]
    assert [(x["id"], x["need"], x["price"]) for x in _mine(d["so"])] == [("SO-P1", 74, 2500)]
    assert [(x["id"], x["gmin"], x["exp"], x["price"]) for x in _mine(d["bid"])] == [("BID-P1", "B", 13, 1500)]
    assert (d["proj"]["id"], d["proj"]["need"], d["proj"]["rental"], d["proj"]["quote"]) == ("TPR-P1", 18, 900, "PR-8841")
    assert [(x["id"], x["backorder"]) for x in _mine(d["wo"][PART])] == [("RO-P1", True), ("RO-P2", False)]
    assert d["rcq"] == ""
    # another class sees none of ours
    assert not _mine(other["lease"] + other["so"] + other["bid"])
    assert (other["proj"] or {}).get("id") != "TPR-P1"
    assert not _mine(other["wo"].get(PART, []))


def test_tf_07_demand_in_the_past_is_not_offered(clean):
    _write_demand(over={RENEWAL: {"need_by": "2026-10-01"}, "BID-P1": {"expires": "2026-10-06"}})
    with SessionLocal() as s:
        d = tool_demand.named_demand(s, ORG, "CMH", AS_OF)
    # only this test's rows are asserted: a stack with the fleet mock synced offers its own live renewals too
    assert _mine(d["lease"]) == [] and _mine(d["bid"]) == [] and [x["id"] for x in _mine(d["so"])] == ["SO-P1"]


# ------------------------------------------------------------------ the panel
def test_tf_07_six_paths_with_named_demand(clean):
    _write_demand()
    _grade_a()
    v = _paths(_open())
    rows = _by_k(v)
    assert list(rows) == ["release", "refurb", "redeploy", "resell", "harvest", "exit"]
    assert all({"k", "name", "ok", "net", "gross", "cost", "hold", "why", "lines", "dest"} <= set(p) for p in v["paths"])
    rel = rows["release"]
    first = "Fleet renewal FC-30117-R · Brightline Mechanical, 12 months in today's money"
    assert rel["ok"] and rel["lines"][0]["label"] == first
    assert rel["dest"]["id"] == RENEWAL
    ros = " ".join(x["label"] for x in rows["harvest"]["lines"])
    assert "RO-P1" in ros and rows["harvest"]["ok"]


def test_tf_07_blocked_paths_say_why(clean):
    _write_demand()
    _grade_a()
    rows = _by_k(_paths(_open()))
    assert not rows["refurb"]["ok"]
    assert rows["refurb"]["why"] == "Grade A needs only a clean and inspect (priced under Re-issue and Pre-owned sale)"


def test_tf_07_best_second_and_uplift(clean):
    _write_demand()
    _grade_a()
    v = _paths(_open())
    rows = _by_k(v)
    ok = sorted((p for p in v["paths"] if p["ok"]), key=lambda p: -p["net"])
    assert v["best"] == ok[0]["k"] and v["second"] == ok[1]["k"]
    assert v["standard"] == "release"  # grade A in fleet management: the default path is the re-issue
    assert v["uplift"] == pytest.approx(rows[v["best"]]["net"] - rows[v["standard"]]["net"], abs=0.01)


def test_tf_07_held_demand_excluded(clean):
    _write_demand(only=[RENEWAL])
    _grade_a()
    first = _open()
    assert _by_k(_paths(first))["release"]["dest"]["id"] == RENEWAL
    with engine.begin() as c:  # an approved decision holds the renewal
        c.execute(
            text("UPDATE case_record SET stage = 'approved', data = jsonb_set(data, '{stage}', '\"approved\"') WHERE id = :i"),
            {"i": first},
        )
    with SessionLocal() as s:
        assert _mine(tool_demand.named_demand(s, ORG, "CMH", AS_OF)["lease"]) == []
        assert [x["id"] for x in _mine(tool_demand.named_demand(s, ORG, "CMH", AS_OF, case_id=first)["lease"])] == [RENEWAL]
    _grade_a(OTHER)
    second = _open(OTHER)
    labels = " ".join(x["label"] for p in _paths(second)["paths"] for x in p["lines"])
    assert RENEWAL not in labels


def test_tf_07_own_contracts_renewal_wins_over_a_richer_fleet_wide_one(clean):
    """A return takes the renewal of its OWN contract; another contract's renewal only when its own has none."""
    _write_demand(only=[RENEWAL])
    rich = {"kind": "lease", "need_by": "2026-12-01", "lease_rate": 900, "term_months": 12, "renew": True, "site": "Houston",
            "tool_class": "CMH", "buyer": "Fleet Wide Co", "contract_ref": "FC-30101"}  # fmt: skip
    with SessionLocal() as s:
        canonical.apply(s, "fleet", _facts("FC-30101-R", "fleet", rich))
        s.commit()
    _grade_a()

    def open_for(contract: str) -> str:
        with SessionLocal() as s:
            facts = tool_case_facts(SERIAL, {"tool_class": "CMH", "site": "Houston", "grade": "A", "contract_id": contract},
                                    line={"contract_id": contract})  # fmt: skip
            c = intake.open_case(
                s, {"org_unit_id": ORG, "template_key": "tool_fleet", "asset_key": SERIAL, "reason": "contract_end",
                    "facts": facts}, "system")  # fmt: skip
            s.commit()
            return c["id"]

    own = open_for("FC-30117")
    assert _by_k(_paths(own))["release"]["dest"]["id"] == RENEWAL
    with engine.begin() as c:
        c.execute(text("DELETE FROM case_record WHERE owner = :o"), {"o": ORG})
    none = open_for("FC-99999")  # no renewal of its own: the best of the feed
    assert _by_k(_paths(none))["release"]["dest"]["id"] == "FC-30101-R"
