"""MVP-9.4: where a PLM part is used, and the parts value of an intake case from its BOM.

    where_used(s, org_unit_id, part_number) -> [{parent, parent_revision, qty}]
    BomPartsPredictor(base, lines, demand).parts_value(a, internal)
        = round(sum over harvestable lines of unit_cost x qty x min(1, demand[part] / qty) x max(gf, 0.5)
                x (1.0 internal | 0.8 external))

The PLM facts are written straight into the canonical store for org unit Customer A (keys "Customer A:<number>") and
removed afterwards. Book cases never use the BOM (parity).
"""

import pytest
from sqlalchemy import text

from di.core.db import SessionLocal, engine
from di.repositories import plm
from di.services.canonical import store as canonical
from di.services.canonical.schema import bom_key, part_key
from di.services.canonical.store import Fact
from di.services.cases import store
from di.services.engine import book
from di.services.engine.predictor import Asset, BomLine, BomPartsPredictor, FormulaPredictor
from di.services.modeler.valuers.rng import mulberry32
from tests import starting
from tests.helpers import call

ORG = "Customer A"
SRC = "plm_wc"
# part: (unit cost, state); the assemblies ASM-T1 and ASM-T2 are released (active), ASM-T3 is in work
PARTS = {"T-P1": (100, "released"), "T-P2": (50, "released"), "T-P3": (400, "in_work"), "ASM-T1": (900, "released"),
         "ASM-T2": (700, "released"), "ASM-T3": (650, "in_work"), "T-P4": (80, "released")}  # fmt: skip
# (parent, revision, child, qty, harvestable)
LINES = [
    ("ASM-T1", "B", "T-P1", 2, True), ("ASM-T1", "B", "T-P2", 1, True), ("ASM-T1", "B", "T-P3", 1, False),
    ("ASM-T1", "A", "T-P4", 3, True),  # an older revision: not the assembly's lines now
    ("ASM-T2", "A", "T-P1", 4, True), ("ASM-T3", "A", "T-P2", 1, True), ("ASM-T3", "A", "T-P4", 1, True),
]  # fmt: skip


def _facts() -> list[Fact]:
    out = []
    for n, (cost, st) in PARTS.items():
        k = part_key(ORG, n)
        out += [Fact("part", k, "number", n), Fact("part", k, "unit_cost", cost), Fact("part", k, "state", st),
                Fact("part", k, "org_unit_id", ORG)]  # fmt: skip
    for parent, rev, child, qty, harv in LINES:
        k = bom_key(ORG, parent, rev, child)
        out += [Fact("bom", k, "parent", parent), Fact("bom", k, "child", child), Fact("bom", k, "qty", qty),
                Fact("bom", k, "parent_revision", rev), Fact("bom", k, "harvestable", harv)]  # fmt: skip
    return out


def _clean() -> None:
    with engine.begin() as c:
        for t in ("provenance", "conflict", "canonical"):
            c.execute(text(f"DELETE FROM {t} WHERE model IN ('part', 'bom') AND key LIKE :k"), {"k": ORG + ":%T%"})  # noqa: S608
        c.execute(text("DELETE FROM provenance WHERE model = 'asset' AND key = 'T-BOM-1'"))
        c.execute(text("DELETE FROM canonical WHERE model = 'asset' AND key = 'T-BOM-1'"))


@pytest.fixture(scope="module", autouse=True)
def plm_data():
    starting.reset()
    _clean()
    with SessionLocal() as s:
        canonical.apply(s, SRC, _facts(), 95)
        s.commit()
    yield
    _clean()
    starting.reset()


B = Asset("motor", "B", 4)  # grade factor 0.86


def test_where_used():
    with SessionLocal() as s:
        assert plm.where_used(s, ORG, "T-P1") == [
            {"parent": "ASM-T1", "parent_revision": "B", "qty": 2}, {"parent": "ASM-T2", "parent_revision": "A", "qty": 4},
        ]  # fmt: skip
        assert plm.where_used(s, "Customer B", "T-P1") == []  # another org's PLM data never answers
        assert plm.demand(s, ORG, ["T-P1", "T-P2", "T-P4"]) == {"T-P1": 2, "T-P2": 1, "T-P4": 1}


def test_parts_value_from_bom():
    with SessionLocal() as s:
        lines = plm.bom_lines(s, ORG, "ASM-T1")
        dem = plm.demand(s, ORG, [x.part for x in lines])
    assert lines == [BomLine("T-P1", 2, 100, True), BomLine("T-P2", 1, 50, True), BomLine("T-P3", 1, 400, False)]
    p = BomPartsPredictor(FormulaPredictor(mulberry32(7)), lines, dem)
    # T-P1: 100 x 2 x min(1, 2/2) = 200; T-P2: 50 x 1 x min(1, 1/1) = 50; T-P3 is not harvestable
    assert p.parts_value(B, internal=True) == round(250 * 0.86)  # 215
    assert p.parts_value(B, internal=False) == round(250 * 0.86 * 0.8)  # 172
    assert p.parts_value(Asset("motor", "D", 4), internal=True) == 125  # grade D values at the 0.5 floor
    base, wrapped = FormulaPredictor(mulberry32(7)), BomPartsPredictor(FormulaPredictor(mulberry32(7)), lines, dem)
    assert wrapped.market_value(B) == base.market_value(B) and wrapped.sale(B, 1000) == base.sale(B, 1000)


def test_no_demand_no_value():
    lines = [BomLine("T-P1", 2, 100, True), BomLine("T-P9", 1, 60, True)]
    assert BomPartsPredictor(FormulaPredictor(mulberry32(1)), lines, {}).parts_value(B, internal=True) == 0
    assert BomPartsPredictor(FormulaPredictor(mulberry32(1)), lines, {"T-P1": 1}).parts_value(B, internal=True) == 86


def test_intake_case_uses_the_bom():
    with SessionLocal() as s:
        canonical.apply(s, SRC, [Fact("asset", "T-BOM-1", "bom_ref", "ASM-T1")], 95)
        s.commit()
    facts = {"cls": "motor", "grade": "B", "age": 4, "qty": 1, "demand": {"parts": True}}
    r = call("case.open", {"org_unit_id": ORG, "template_key": "industrial", "asset_key": "T-BOM-1", "reason": "rma",
                           "facts": facts}, "planner-a")  # fmt: skip
    assert r["ok"], r
    with SessionLocal() as s:
        c = store.get(s, r["output"]["case_id"])
    assert c is not None and c["bomRef"] == "ASM-T1"
    intparts = next(x for x in c["routes"] if x["id"] == "intparts")
    extparts = next(x for x in c["routes"] if x["id"] == "extparts")
    assert intparts["terms"][0]["amt"] == 215 and extparts["terms"][0]["amt"] == 172


def test_book_cases_unchanged():
    with SessionLocal() as s:
        for c in store.all_cases(s):
            if "intake" in c:
                continue
            b = book.get(c["id"])
            assert b is not None and c["routes"] == b["routes"], c["id"]
