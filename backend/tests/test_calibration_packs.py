"""P9-13.7: calibration and model candidates across all six packs (plan 8 MVP-12.1 to 12.3, extended).

model.fit, model.propose, model.promote and model.list take any pack key (di.services.modeler.pack.pack_keys); an
unknown key is refused naming the six. A promoted model calibrates NEW intake only (the device channel prices through the
Predictor wrapper). Rule suggestions read each pack's dimensions. The maker-checker and agent rules hold for every pack.
No factor ships by default, so no decision number changes until a person promotes a model.

The outcomes are written straight onto synthetic case records (as outcome.confirm stores them) and removed afterwards.
"""

import json

import pytest
from sqlalchemy import text

from di.core.db import SessionLocal
from di.services.actions.models import MAKER_CHECKER, PROPOSER_CHECKER, intake_predictor
from di.services.cases import store
from di.services.engine.calibration import CalibratedPredictor
from di.services.engine.predictor import FormulaPredictor
from di.services.modeler.pack import load_pack, pack_keys
from di.services.modeler.suggest import DecisionRow, suggest
from di.services.modeler.templates import load_template
from tests.helpers import call, client, h

PACKS = ("industrial", "tool_fleet", "device", "used_cars", "telecom_network", "medical_rental")
RATIO = 0.8


def _route(pack: str) -> str:
    return load_template(pack).paths[0].id


@pytest.fixture
def outcomes():
    """Five confirmed outcomes per pack: the first route of each pack, predicted 100, actual 80."""
    with SessionLocal() as s:
        store.ensure(s)  # open the book first: it opens only into an empty case table
        s.execute(text("DELETE FROM model_version"))
        for pack in PACKS:
            for k in range(5):
                doc = {
                    "id": f"CALP-{pack}-{k}", "template": pack, "cls": "x", "rec_index": 0,
                    "routes": [{"id": _route(pack), "net": 100.0}],
                    "outcome": {"net": 100.0 * RATIO, "at": f"2026-10-2{k}T09:00Z"},
                }  # fmt: skip
                s.execute(
                    text(
                        "INSERT INTO case_record (id, owner, location, stage, data) "
                        "VALUES (:i, 'Customer A', 'Site 1', 'closed', CAST(:d AS jsonb))"
                    ),
                    {"i": doc["id"], "d": json.dumps(doc)},
                )
        s.commit()
    yield
    with SessionLocal() as s:
        s.execute(text("DELETE FROM case_record WHERE id LIKE 'CALP-%'"))
        s.execute(text("DELETE FROM model_version"))
        s.commit()


def test_the_six_packs_are_all_present():
    assert set(PACKS) <= set(pack_keys())


@pytest.mark.usefixtures("outcomes")
def test_model_fit_every_pack():
    for pack in PACKS:
        out = call("model.fit", {"template": pack}, "planner-a")
        assert out["ok"], (pack, out)
        m = out["output"]
        assert m["template"] == pack and m["status"] == "candidate"
        assert m["factors"] == [{"route": _route(pack), "cls": "x", "factor": pytest.approx(RATIO)}]
        assert m["metrics"]["n"] == 5
    bad = call("model.fit", {"template": "boats"}, "planner-a")
    assert not bad["ok"] and bad["error"]["code"] == "validation_error"
    assert all(p in bad["error"]["message"] for p in PACKS)


@pytest.mark.usefixtures("outcomes")
def test_promote_calibrates_new_intake_only_per_pack():
    from di.services.device import inputs as device_inputs

    case = {"imei": "IMEI-CALP", "ref": 500, "grade": "B", "model": "iPhone 13", "storage_gb": 128}
    with SessionLocal() as s:
        base = device_inputs.price_bands(s, case, {}, None)
    assert base, "a received device has a band per channel"
    with SessionLocal() as s:
        s.execute(text("DELETE FROM case_record WHERE id LIKE 'CALP-device-%'"))
        for k in range(5):  # buynow outcomes at 1.10 x the prediction
            doc = {
                "id": f"CALP-device-{k}", "template": "device", "cls": "device", "rec_index": 0,
                "routes": [{"id": "buynow", "net": 100.0}], "outcome": {"net": 110.0, "at": f"2026-10-2{k}T09:00Z"},
            }  # fmt: skip
            s.execute(
                text(
                    "INSERT INTO case_record (id, owner, location, stage, data) "
                    "VALUES (:i, 'Customer A', 'Site 1', 'closed', CAST(:d AS jsonb))"
                ),
                {"i": doc["id"], "d": json.dumps(doc)},
            )
        s.commit()
    mid = call("model.fit", {"template": "device"}, "planner-a")["output"]["id"]
    assert call("model.propose", {"id": mid}, "planner-a")["ok"]
    assert call("model.promote", {"id": mid}, "approver")["ok"]
    with SessionLocal() as s:
        after = device_inputs.price_bands(s, case, {}, None)
        p = intake_predictor(s, FormulaPredictor(), "device", "device")
        ind = intake_predictor(s, FormulaPredictor(), "x", "industrial")
        stored = s.execute(text("SELECT data FROM case_record WHERE id = 'CALP-device-0'")).scalar_one()
    assert isinstance(p, CalibratedPredictor)
    assert after["buynow"]["p50"] == pytest.approx(1.10 * base["buynow"]["p50"])
    assert after["auction"] == base["auction"]  # a route without a factor keeps the base
    assert not isinstance(ind, CalibratedPredictor)  # the industrial book is unchanged
    assert stored["routes"] == [{"id": "buynow", "net": 100.0}]  # a stored case keeps its routes


def test_rule_suggestions_every_pack():
    t = load_template("used_cars")
    dim = next(d for d in t.dims if d.kind == "set")
    value = dim.values[0]
    to, frm = t.paths[1].id, t.paths[0].id

    def row(i: int, v: str, route: str) -> DecisionRow:
        return DecisionRow(f"UC-{i}", "used_cars", frm, route, {dim.key: v})

    rows = [row(1, value, to), row(2, value, to), row(3, value, to), row(4, value, frm)]  # 3 of 4: 75 %
    out = suggest(t, rows)
    assert [(s.dim, s.value, s.path, s.overrides) for s in out] == [(dim.key, value, to, 3)]
    assert suggest(t, rows[:2] + rows[3:]) == []  # two overrides: below 3
    assert suggest(t, rows + [row(5 + k, value, frm) for k in range(3)]) == []  # 3 of 7: below 60 %


@pytest.mark.usefixtures("outcomes")
def test_model_maker_cannot_promote_any_pack():
    for pack in PACKS:
        mid = call("model.fit", {"template": pack}, "admin")["output"]["id"]
        out = call("model.promote", {"id": mid}, "admin")
        assert not out["ok"] and out["error"]["message"] == MAKER_CHECKER
        assert call("model.propose", {"id": mid}, "planner-b")["ok"]
        out = call("model.promote", {"id": mid}, "planner-b")  # the proposer, who also lacks approve.flows
        assert not out["ok"]
    mid = call("model.fit", {"template": "telecom_network"}, "admin")["output"]["id"]
    assert call("model.propose", {"id": mid}, "admin")["ok"]
    assert call("model.promote", {"id": mid}, "admin")["error"]["message"] == MAKER_CHECKER
    assert PROPOSER_CHECKER  # exercised for the proposer in test_model_promote


@pytest.mark.usefixtures("outcomes")
def test_model_agent_cannot_propose_any_pack():
    prep = {"X-Circularity-Preparer": "gap"}  # the call is prepared by an agent for a person who holds the permission
    for pack in PACKS:
        mid = call("model.fit", {"template": pack}, "planner-a")["output"]["id"]
        for action, user in (("model.propose", "planner-a"), ("model.promote", "approver")):
            r = client.post(f"/api/actions/{action}", json={"id": mid}, headers=h(user) | prep).json()
            assert not r["ok"] and r["error"]["code"] == "approval_required", (pack, action, r)


def test_every_pack_loads_for_the_model_list():
    for pack in PACKS:
        assert load_pack(pack).key == pack
        out = call("model.list", {"template": pack}, "planner-a")
        assert out["ok"] and out["output"]["template"] == pack
