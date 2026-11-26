"""UI audit gaps 10 and 11 (26 Nov 2026): the Connection Fabric lists every pack's mock systems, grouped by pack.

`GET /api/screens/integration/overview` answers `pack_systems`: each extra adapter (di.connectors.extra) with a readable
name, its pack's key and name, and whether a source is registered. A person registers one with the existing
`source.reconnect` (di.connectors.extra.ensure_registered); no new write path. Reads only here: nothing is registered.
"""

import pytest

from di.connectors import extra
from di.connectors.registry import ADAPTERS
from di.services.modeler.pack import load_pack, pack_keys
from tests.helpers import client, h

EXTRA = sorted(k for k in ADAPTERS if extra.is_extra(k))


def _systems(acct: str = "developer") -> list[dict]:
    r = client.get("/api/screens/integration/overview", headers=h(acct))
    assert r.status_code == 200, r.text
    return r.json()["pack_systems"]


def test_every_extra_adapter_has_a_pack():
    assert len(EXTRA) >= 30
    assert [k for k in EXTRA if extra.PACK_OF.get(k) not in pack_keys()] == []  # a new adapter is added to PACK_OF


def test_ui_gap10_catalogue_lists_every_extra_system_with_a_readable_name():
    got = _systems()
    assert sorted(x["id"] for x in got) == EXTRA
    for x in got:
        assert x["name"] and "synthetic" not in x["name"].lower() and x["name"] != x["id"]
        assert x["pack_name"] == load_pack(x["pack"]).name
        assert isinstance(x["registered"], bool)
    assert "Windchill" in next(x for x in got if x["id"] == "plm_wc")["name"]


def test_ui_gap11_systems_are_grouped_by_pack_in_pack_order():
    got = _systems()
    packs = [x["pack"] for x in got]
    assert packs == sorted(packs, key=pack_keys().index)  # one run per pack, in the picker's order
    by = {p: [x["id"] for x in got if x["pack"] == p] for p in dict.fromkeys(packs)}
    assert {"uc_dms", "uc_auction", "uc_title", "uc_insp", "uc_lease", "uc_price", "uc_recall"} == set(by["used_cars"])
    assert {"tn_inv", "tn_decom", "tn_bench", "tn_spares", "tn_recycler", "tn_broker"} == set(by["telecom_network"])
    assert {"mr_rental", "mr_assets", "mr_biomed", "mr_decon", "mr_parts", "mr_disposal"} == set(by["medical_rental"])
    assert {"dvreg", "dvlab", "dvmkt"} <= set(by["device"]) and "tooltel" in by["tool_fleet"]


def test_ui_gap10_unregistered_systems_are_not_demo_sources():
    """The demo's 21 sources keep their place: no extra system is among them until a person registers it."""
    got = client.get("/api/screens/integration/overview", headers=h("developer")).json()
    ids = {i["id"] for i in got["integrations"]}
    assert not [x["id"] for x in got["pack_systems"] if not x["registered"] and x["id"] in ids]


@pytest.mark.parametrize("acct", ["admin", "developer"])
def test_ui_gap10_screen_read_follows_fabric_access(acct):
    assert _systems(acct)


def test_ui_gap10_account_without_fabric_access_is_refused():
    r = client.get("/api/screens/integration/overview", headers=h("planner.a"))
    assert r.status_code == 403
