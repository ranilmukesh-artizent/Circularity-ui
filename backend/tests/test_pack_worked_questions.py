"""UI audit gaps 3 and 18: the Analytics pack view lists the worked questions registered for the selected pack, and the
Fabric models screen lists the templates a manual import may open cases with and their columns."""

from tests.helpers import client, h


def _ids(key: str) -> list[str]:
    r = client.get("/api/screens/analytics/pack", params={"key": key}, headers=h("admin"))
    assert r.status_code == 200, r.text
    return [q["id"] for q in r.json()["worked_questions"]]


def test_pack_view_lists_its_worked_questions():
    assert _ids("device") == ["price_after_launch", "disputes_by_partner"]
    assert _ids("used_cars") == ["wq_uc_1", "wq_uc_2"]
    assert _ids("telecom_network") == ["wq_tn_1", "wq_tn_2"]
    assert len(_ids("medical_rental")) == 2
    assert _ids("industrial") == []


def test_integration_models_lists_case_templates_and_columns():
    r = client.get("/api/screens/integration/models", headers=h("admin"))
    assert r.status_code == 200, r.text
    d = r.json()
    keys = [t["key"] for t in d["case_templates"]]
    assert {"industrial", "tool_fleet", "device"} <= set(keys)
    assert d["template_columns"]["tool_fleet"] == ["cls", "ft", "site", "rul"]
    assert d["template_columns"]["device"] == ["brand", "model", "band", "ref", "doh"]
