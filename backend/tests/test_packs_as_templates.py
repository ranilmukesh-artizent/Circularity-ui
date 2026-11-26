"""P9 writer 8: every pack file is a template of the Modeler (its picker, its screen) with the pack's own name."""

import json

import pytest

from di.services.modeler.pack import PACKS_DIR, pack_keys
from di.services.modeler.templates import TEMPLATE_KEYS, template_keys
from tests import flowkit
from tests.helpers import client, h

URL = "/api/screens/modeler"
NOT_PACKS = {"pack.schema.json", "carbon.json", "gates.catalogue.json"}
FILES = sorted(p.stem for p in PACKS_DIR.glob("*.json") if p.name not in NOT_PACKS)


@pytest.fixture(autouse=True)
def fresh_flows():
    flowkit.reset_flows()
    yield
    flowkit.reset_flows()


def test_template_keys_are_the_pack_files():
    assert set(template_keys()) == set(FILES) == set(pack_keys())
    assert template_keys()[:3] == TEMPLATE_KEYS  # the demo's three stay first, in their order


def test_screen_lists_every_pack_with_its_name():
    out = client.get(URL, headers=h("planner-a")).json()
    names = {k: json.loads((PACKS_DIR / f"{k}.json").read_text(encoding="utf-8"))["name"] for k in FILES}
    assert {t["key"]: t["name"] for t in out["templates"]} == names
    assert {t["key"]: t["name"] for t in out["packs"]["templates"]} == names
    assert {k["key"]: k["name"] for k in out["packs"]["keys"]} == names


@pytest.mark.parametrize("key", FILES)
def test_screen_opens_every_pack(key):
    r = client.get(URL, params={"template": key}, headers=h("planner-a"))
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["template"]["key"] == key and out["flow"]["name"] == out["template"]["name"]
    assert out["flow"]["graph"]["nodes"] and out["checks"] is not None
