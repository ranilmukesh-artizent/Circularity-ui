"""Plan 9 P9-9.19 (story UC-20, last clause): save the worked question as a view, share it with a role and set an alert on
`days_in_stock` (di.services.analytics_views; actions view.save, view.share, view.setAlert, view.list).

The stock is the used-car mock's EV crossovers of Customer A (52 to 66 days on a lot). The alert fires one My work item per
recipient (the owner, each shared role) when the measure crosses the threshold, and not again until it has been back under."""

import pytest
from sqlalchemy import text

from di.connectors import extra
from di.core.db import SessionLocal, engine
from di.services import analytics_views, questions  # noqa: F401  (questions registers the pack questions)
from di.services.canonical import store
from di.services.canonical.schema import vin_key
from tests.helpers import call, client, h

pytestmark = pytest.mark.usefixtures("no_synced_conflicts")

ORG, OTHER, SID = "Customer A", "Customer B", "uc_dms"
EV_DAYS = {"LOT-N": 58, "LOT-C": 33, "LOT-S": 29}
EV = ((41, "LOT-N", 52), (42, "LOT-N", 58), (43, "LOT-N", 61), (44, "LOT-N", 66), (46, "LOT-C", 31))
SAVE = {"org_unit_id": ORG, "pack": "used_cars", "question_id": "wq_uc_1", "name": "EV crossovers by lot", "params": {}}


def vin(n: int) -> str:
    return f"SYNUV{n:012d}"


def _clean() -> None:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM work_item WHERE type = :t"), {"t": analytics_views.ALERT_TYPE})
        conn.execute(text("DELETE FROM analytics_view"))
        conn.execute(text("DELETE FROM provenance WHERE key LIKE :p"), {"p": "%:SYNUV%"})
        conn.execute(text("DELETE FROM canonical WHERE key LIKE :p"), {"p": "%:SYNUV%"})


def _set_days(n: int, lot: str, days: int) -> None:
    with SessionLocal() as s:
        k = vin_key(ORG, vin(n))
        store.apply(s, SID, [store.Fact("asset", k, "lot_id", lot), store.Fact("asset", k, "days_on_lot", days),
                             store.Fact("asset", k, "segment", "ev_crossover"), store.Fact("asset", k, "return_kind", "trade_in"),
                             store.Fact("market", k, "lot_days_to_sale", EV_DAYS)])  # fmt: skip
        s.commit()


@pytest.fixture(autouse=True)
def stock():
    _clean()
    with SessionLocal() as s:
        extra.register(s, SID, ORG)
        s.commit()
    for n, lot, d in EV:
        _set_days(n, lot, d)
    yield
    _clean()


def _ok(r: dict) -> dict:
    assert r.get("ok"), r
    return r["output"]


def _evaluate() -> None:
    with SessionLocal() as s:
        analytics_views.evaluate_alerts(s, "system")
        s.commit()


def _alert_items() -> list[tuple[str, str | None]]:
    with SessionLocal() as s:
        rows = s.execute(
            text("SELECT owner_role, owner_account FROM work_item WHERE type = :t AND status = 'open' ORDER BY owner_role, id"),
            {"t": analytics_views.ALERT_TYPE},
        )
        return [(r.owner_role, r.owner_account) for r in rows]


def _mywork(user: str) -> list[dict]:
    r = client.get("/api/screens/mywork", headers=h(user))
    assert r.status_code == 200, r.text
    return [i for i in r.json()["items"] if "EV crossovers by lot" in i["title"]]


def _views(user: str) -> list[dict]:
    return _ok(call("view.list", {}, user))["views"]


def test_uc_20_save_share_alert():
    saved = _ok(call("view.save", SAVE, "planner.a"))
    vid = saved["id"]
    assert saved["owner"] == "planner-a" and saved["shared_with_roles"] == [] and saved["alert"] is None
    assert [v["id"] for v in _views("planner.a")] == [vid] and _views("approver") == []  # not shared yet

    shared = _ok(call("view.share", {"view_id": vid, "roles": ["Approver"]}, "planner.a"))
    assert shared["shared_with_roles"] == ["Approver"]
    seen = _views("approver")
    assert [v["id"] for v in seen] == [vid] and seen[0]["mine"] is False and seen[0]["owner"] == "planner-a"
    assert _views("finance") == []  # a role it is not shared with

    alert = {"view_id": vid, "measure": "days_in_stock", "op": ">", "threshold": 45}
    assert _ok(call("view.setAlert", alert, "planner.a"))["alert"] == {"measure": "days_in_stock", "op": ">", "threshold": 45}
    assert _alert_items() == [("Approver", None), ("Planner", "planner-a")]  # 66 days is over 45: one item each, at once

    _evaluate()
    _evaluate()  # the same crossing is not raised again
    assert len(_alert_items()) == 2
    for user in ("planner.a", "approver"):
        item = _mywork(user)
        assert len(item) == 1 and "days_in_stock is 66" in item[0]["cause"] and "45" in item[0]["cause"], item
    assert _mywork("finance") == []


def test_uc_20_alert_fires_once_per_crossing():
    vid = _ok(call("view.save", SAVE, "planner.a"))["id"]
    _ok(call("view.setAlert", {"view_id": vid, "measure": "days_in_stock", "op": ">", "threshold": 70}, "planner.a"))
    _evaluate()
    assert _alert_items() == []  # 66 days: not crossed
    _set_days(44, "LOT-N", 75)
    _evaluate()
    _evaluate()
    assert _alert_items() == [("Planner", "planner-a")]  # crossed: one, not one per tick
    _set_days(44, "LOT-N", 66)
    _evaluate()
    assert _alert_items() == []  # back under: the item closes
    _set_days(44, "LOT-N", 80)
    _evaluate()
    assert _alert_items() == [("Planner", "planner-a")]  # a new crossing raises a new one


def test_uc_20_clearing_the_alert_closes_its_items():
    vid = _ok(call("view.save", SAVE, "planner.a"))["id"]
    _ok(call("view.setAlert", {"view_id": vid, "measure": "days_in_stock", "op": ">", "threshold": 45}, "planner.a"))
    assert len(_alert_items()) == 1
    assert _ok(call("view.setAlert", {"view_id": vid, "clear": True}, "planner.a"))["alert"] is None
    assert _alert_items() == []


def test_uc_20_view_checks():
    bad = call("view.save", SAVE | {"question_id": "nope"}, "planner.a")
    assert bad["ok"] is False and bad["error"]["code"] == "not_found"
    other = call("view.save", SAVE | {"org_unit_id": OTHER}, "planner.a")  # Planner A may not see Customer B
    assert other["ok"] is False and other["error"]["code"] == "tenant_boundary", other
    vid = _ok(call("view.save", SAVE, "planner.a"))["id"]
    role = call("view.share", {"view_id": vid, "roles": ["Wizard"]}, "planner.a")
    assert role["ok"] is False and role["error"]["code"] == "validation_error"
    measure = call("view.setAlert", {"view_id": vid, "measure": "mystery", "op": ">", "threshold": 1}, "planner.a")
    assert measure["ok"] is False and measure["error"]["code"] == "validation_error"
    op = call("view.setAlert", {"view_id": vid, "measure": "days_in_stock", "op": "~", "threshold": 1}, "planner.a")
    assert op["ok"] is False and op["error"]["code"] == "validation_error"


def test_uc_20_only_the_owner_changes_a_view():
    vid = _ok(call("view.save", SAVE, "planner.a"))["id"]
    _ok(call("view.share", {"view_id": vid, "roles": ["Approver"]}, "planner.a"))
    for action, body in (("view.share", {"roles": ["Finance"]}),
                         ("view.setAlert", {"measure": "days_in_stock", "op": ">", "threshold": 1})):  # fmt: skip
        r = call(action, {"view_id": vid} | body, "approver")  # sees it, but it is not theirs
        assert r["ok"] is False and r["error"]["code"] == "out_of_scope", (action, r)
    assert _views("planner.a")[0]["shared_with_roles"] == ["Approver"]
    gone = call("view.share", {"view_id": 999999, "roles": []}, "planner.a")
    assert gone["ok"] is False and gone["error"]["code"] == "not_found"


def test_uc_20_agent_reads_views_but_never_shares_or_sets_alerts():
    vid = _ok(call("view.save", SAVE, "planner.a"))["id"]
    hdr = h("planner.a") | {"X-Circularity-Preparer": "coordinator"}
    read = client.post("/api/actions/view.list", json={}, headers=hdr).json()
    assert read["ok"] is True and [v["id"] for v in read["output"]["views"]] == [vid]
    share = client.post("/api/actions/view.share", json={"view_id": vid, "roles": ["Approver"]}, headers=hdr).json()
    assert share["ok"] is False and share["error"]["code"] == "approval_required", share
    confirmed = client.post("/api/actions/view.share", json={"view_id": vid, "roles": ["Approver"]},
                            headers=hdr | {"X-Circularity-Confirmed": "true"}).json()  # fmt: skip
    assert confirmed["ok"] is False and confirmed["error"]["code"] == "approval_required"
    assert _views("planner.a")[0]["shared_with_roles"] == [] and _views("approver") == []
    alert = {"view_id": vid, "measure": "days_in_stock", "op": ">", "threshold": 45}
    held = client.post("/api/actions/view.setAlert", json=alert, headers=hdr).json()
    assert held["ok"] is True and set(held["output"]) == {"held", "reasons"}, held  # held for the person, not run
    assert _views("planner.a")[0]["alert"] is None and _alert_items() == []
