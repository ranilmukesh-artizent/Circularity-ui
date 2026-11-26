"""Ask's starters by pack and page (UI pack audit E17): GET /api/ask/starters.

- a pack's case gets the pack's own questions first, then the case questions; none is an action on a person's behalf
- the Modeler asks about the flow's template; Home and Integration have their own
- the role decides: a Warehouse Manager is not offered Integration's questions; the server filters, not the page
- the industrial pack has no pack questions (the web app shows the demo's starters for it)
"""

import pytest
from sqlalchemy import text

from di.core.db import SessionLocal
from di.services.ask import starters
from tests import starting
from tests.helpers import client, h


def setup_module():
    starting.reset()


def get(user: str, **q) -> dict:
    r = client.get("/api/ask/starters", params=q, headers=h(user))
    assert r.status_code == 200, r.text
    return r.json()


def texts(r: dict) -> list[str]:
    return [x["text"] for x in r["starters"]]


def test_sign_in_is_required():
    assert client.get("/api/ask/starters").status_code == 401


def test_industrial_case_has_no_pack_starters():
    r = get("planner-a", page="product", case_id="RT-1048")
    assert r["pack"] is None
    assert texts(r) == [x.text for x in starters.PAGE["case"]]


def test_a_pack_case_gets_the_pack_questions_first():
    with SessionLocal() as s:
        row = s.execute(text("SELECT id FROM case_record WHERE data ->> 'template' = 'device' LIMIT 1")).first()
    if row is None:
        pytest.skip("no device case in the seed")
    r = get("admin", page="product", case_id=row[0])
    assert r["pack"] == "device"
    t = texts(r)
    assert t[: len(starters.PACK_CASE["device"])] == [x.text for x in starters.PACK_CASE["device"]]
    assert t[-1] == starters.PAGE["case"][-1].text


def test_modeler_uses_the_flow_template():
    r = get("admin", page="modeler", section="used_cars")
    assert r["pack"] == "used_cars"
    assert texts(r)[0] == starters.PACK_WIDE["used_cars"][0].text
    assert any("guardrails" in x for x in texts(r))


def test_pages_have_their_own_and_role_filters():
    assert "What needs me today?" in texts(get("admin", page="home"))
    assert "Which sources need attention?" in texts(get("admin", page="integration"))
    assert get("warehouse1", page="integration")["starters"] == []
    assert get("warehouse1", page="modeler", section="device")["starters"] == []


def test_no_starter_acts_for_a_person():
    for group in (starters.PACK_CASE, starters.PACK_WIDE, starters.PAGE):
        for items in group.values():
            for x in items:
                t = x.text.lower()
                assert not any(w in t for w in ("approve ", "waive", "override", "decline ")), x.text
