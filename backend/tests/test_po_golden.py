"""MVP-0.3: the PO prototype goldens (fixtures/golden/po, written only by frontend/scripts/dump-po-golden.mjs) hold
the templates, cases, rules and sentences the later MVP tasks compare against."""

from di.core.golden import load

EQUIP_PATHS = ["release", "refurb", "redeploy", "resell", "harvest", "exit"]
EQUIP_GUARDS = {
    "GR-01": "Grade C and D tools are never issued to a fleet without refurbishment",
    "GR-02": "Refurbishment always ends in a named fleet contract, sales order or pool request",
    "GR-03": "Harvested parts are certified only at or above the fit-for-use threshold",
    "GR-04": "The holding cost rate is set by Finance",
    "GR-05": "Every decision is approved by a named owner before execution",
    "GR-06": "Recycling only through a certified recycler, certificate and CO2 record on file",
}
SENTENCES = [
    "Never recycle construction lasers",
    "Prefer tool pool for grade A or B from Repair center",
    "Only harvest parts for breakers under 30% life",
    "Lower the fit-for-use threshold to 60",
    "Skip approval for grade A",
    "Lots over 45 days on hand: Auction only",
    "Never list grade D on Buy Now",
    "Samsung under 24 months prefer offers",
]


def _templates() -> dict:
    return {t["key"]: t for t in load("po/templates")["templates"]}


def test_templates_have_equip_and_device():
    assert {"equip", "device"} <= set(_templates())


def test_equip_paths_and_guards():
    equip = _templates()["equip"]
    assert [p["key"] for p in equip["paths"]] == EQUIP_PATHS
    assert {g["id"]: g["text"] for g in equip["guards"]} == EQUIP_GUARDS
    assert [g["id"] for g in equip["guards"]] == sorted(EQUIP_GUARDS)


def test_device_paths_and_guards():
    device = _templates()["device"]
    assert [p["key"] for p in device["paths"]] == ["buynow", "offers", "auction", "market"]
    assert [g["id"] for g in device["guards"]] == [f"GR-D{i}" for i in range(1, 7)]


def test_equip_cases_not_empty():
    cases = load("po/equip_cases")
    assert cases["cases"]
    assert set(cases["open_ids"]) <= {c["id"] for c in cases["cases"]}


def test_apply_cases_include_a_waiver():
    assert any(a["result"].get("waived") is True for a in load("po/apply_cases")["cases"])


def test_every_sentence_is_parsed():
    assert [p["text"] for p in load("po/parse_cases")["cases"]] == SENTENCES
