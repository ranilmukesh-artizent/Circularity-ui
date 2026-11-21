"""Plan 6, task C1: the workflow block catalogue with settings (di/workflow/blocks.py) and its read endpoint.

Every block the Workflow Studio's palette offers has a spec; every spec's defaults pass its own checks (so a workflow
saved before settings existed is valid as it is); the checks name the block and the field; the endpoint is readable by
the accounts that see the Workflow Studio (Admin and Developer) and nobody else.
"""

import pytest

from di.reads.constants import TOOLS
from di.reads.reference import lists
from di.workflow import blocks as B
from tests.helpers import client, h

REF = lists()
XF_IDS = [x["id"] for x in REF["XF"]] + [x["id"] for x in REF["FR_XF"]]


def palette_nodes() -> list[dict]:
    """One node per palette entry, as the canvas creates them."""
    nodes = [{"id": f"n_{r}", "k": "xf", "ref": r, "x": 0, "y": 0} for r in dict.fromkeys(XF_IDS)]
    nodes += [{"id": f"a_{a['id']}", "k": "act", "ref": a["id"], "x": 0, "y": 0} for a in REF["ACT_TYPES"]]
    nodes += [{"id": f"f_{f}", "k": "fixed", "ref": f, "x": 0, "y": 0} for f in REF["FXD"]]
    nodes += [{"id": f"t_{t['id']}", "k": "tool", "ref": t["id"], "x": 0, "y": 0} for t in TOOLS]
    nodes += [{"id": f"{k}_crm", "k": k, "ref": "crm", "x": 0, "y": 0} for k in ("conn", "wconn", "map")]
    return nodes


@pytest.mark.parametrize("node", palette_nodes(), ids=lambda n: n["id"])
def test_every_palette_block_has_a_spec_and_its_defaults_pass(node):
    spec = B.spec_for(node)
    assert spec is not None, node
    assert B.cfg_errors(node, {"label": "Step"}) == []
    assert B.cfg_errors(node | {"cfg": B.default_cfg(spec.ref)}, {"label": "Step"}) == []
    assert set(B.node_cfg(node)) == {f.key for f in spec.fields}


def test_every_xf_ref_is_in_the_catalogue():
    assert set(XF_IDS) <= set(B.BLOCKS)
    assert {"conn", "wconn", "map", "act", "fixed", "tool"} <= set(B.BLOCKS)


def test_fixed_and_tool_blocks_have_no_settings_and_are_read_only():
    for ref in ("fixed", "tool"):
        assert B.BLOCKS[ref].fields == () and B.BLOCKS[ref].readonly


def test_the_settings_table_keys():
    keys = {ref: [f.key for f in s.fields] for ref, s in B.BLOCKS.items()}
    assert keys["conn"] == ["resources", "mode", "lookback_days"]
    assert keys["x_fx"] == ["currency", "rate_date", "rate_table"]
    assert keys["x_val"] == ["required", "rules", "on_failure"]
    assert keys["x_late"] == ["keys", "newest_by", "late_window_min"]
    assert keys["map"] == ["version"]
    assert keys["act"] == ["timeout_s", "retries"]
    assert keys["wconn"] == ["operation"]
    assert B.default_cfg("x_fx") == {"currency": "USD", "rate_date": "record", "rate_table": "fx_rate"}


def test_errors_name_the_block_and_the_field():
    n = {"id": "t", "k": "xf", "ref": "x_fx", "x": 0, "y": 0, "cfg": {"currency": "XYZ"}}
    assert B.cfg_errors(n, {"label": "Convert currency"}) == [
        "Convert currency: Target currency XYZ is not one of USD, EUR, INR."
    ]
    n = {"id": "t", "k": "xf", "ref": "x_filter", "x": 0, "y": 0, "cfg": {"condition": [{"field": "", "check": "present"}]}}
    assert B.cfg_errors(n, {"label": "Filter and condition"}) == ["Filter and condition: Condition rule 1 has no field."]


def test_field_type_checks():
    def errs(ref: str, cfg: dict, k: str = "xf", **ctx) -> list[str]:
        return B.cfg_errors({"id": "n", "k": k, "ref": ref, "cfg": cfg}, {"label": "S", **ctx})

    assert errs("x_gw", {"timeout_s": "fast"}) == ["S: Timeout (s) must be a number."]
    assert errs("x_gw", {"timeout_s": 0}) == ["S: Timeout (s) must be at least 1."]
    assert errs("x_file", {"checksum_required": "yes"}) == ["S: Checksum required must be yes or no."]
    assert errs("x_val", {"required": "qty"}) == ["S: Required fields must be a list of field names."]
    assert errs("x_val", {"rules": [{"field": "qty", "check": "regex", "arg": "("}]})[0].startswith(
        "S: Rules rule 1 has a pattern that does not compile"
    )
    assert errs("x_val", {"rules": [{"field": "qty", "check": "range", "arg": ">0"}]}) == []
    assert errs("x_val", {"rules": [{"field": "qty", "check": "range", "arg": "big"}]}) == [
        "S: Rules rule 1 needs a range such as 0..100, >0 or <=5."
    ]
    assert errs("x_val", {"rules": [{"field": "qty", "check": "bigger"}]}) == [
        "S: Rules rule 1 has an unknown check bigger (present, type, regex, range or in)."
    ]
    assert errs("x_units", {"units": {"power": "parsec"}})[0].startswith("S: Field units: parsec is not one of")
    assert errs("x_units", {"units": {"power": "kW"}}) == []
    assert errs("conn", {"mode": "sometimes"}, k="conn") == ["S: Mode sometimes is not one of delta, full."]
    assert errs("x_fx", {"colour": "red"}) == ["S: colour is not a setting of this block."]
    assert errs("map", {"version": "v2"}, k="map") == ["S: Mapping version must be latest or a version number."]
    assert errs("map", {"version": 3}, k="map") == []
    assert errs("x_expr", {"target": "margin"}) == ["S: Expression is needed with Target field."]
    assert errs("x_sched", {"interval_min": 0}) == ["S: Interval (min) must be at least 1."]


def test_checks_against_what_the_source_sends():
    """With the source's fields and resources known (ctx), a key the records lack is an error."""
    n = {"id": "n", "k": "xf", "ref": "x_late", "cfg": {"keys": ["opportunity_id"]}}
    assert B.cfg_errors(n, {"label": "Order late events", "fields": {"Opportunity.Id"}}) == [
        "Order late events: Key fields opportunity_id is not a field the records carry."
    ]
    assert B.cfg_errors(n, {"label": "Order late events"}) == []  # fields unknown: not checked
    c = {"id": "r", "k": "conn", "ref": "crm", "cfg": {"resources": ["opps", "ghosts"]}}
    assert B.cfg_errors(c, {"label": "CRM", "resources": ["opps"]}) == [
        "CRM: Resources ghosts is not a resource of this connection."
    ]


def test_the_endpoint_serves_the_catalogue_to_the_studio_only():
    r = client.get("/api/screens/workflows/blocks", headers=h("developer"))
    assert r.status_code == 200, r.text
    body = r.json()
    by = {b["ref"]: b for b in body["blocks"]}
    assert set(by) == set(B.BLOCKS)
    fx = {f["key"]: f for f in by["x_fx"]["fields"]}
    assert fx["currency"]["type"] == "select" and fx["currency"]["default"] == "USD"
    assert "EUR" in fx["currency"]["choices"]
    assert by["fixed"]["readonly"] is True and by["fixed"]["fields"] == []
    assert isinstance(body["resources"], dict)
    assert client.get("/api/screens/workflows/blocks", headers=h("admin")).status_code == 200
    for acct in ("exec", "ops", "approver", "engineer", "finance", "warehouse1"):
        r = client.get("/api/screens/workflows/blocks", headers=h(acct))
        assert r.status_code == 403 and r.json()["error"]["code"] == "out_of_scope", acct
