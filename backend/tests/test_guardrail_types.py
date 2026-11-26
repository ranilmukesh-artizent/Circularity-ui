"""P9-0.11: every guardrail of the three template packs has a type and a stage; Compliance ones are locked."""

from di.services.engine import book
from di.services.modeler import stages
from di.services.modeler.templates import TEMPLATE_KEYS, load_template
from tests.helpers import client, h

TABLE = {
    "industrial": {"GR-I1": ("Compliance", "condition"), "GR-I2": ("Compliance", "condition"),
                   "GR-I3": ("Compliance", "match"), "GR-I4": ("Compliance", "execute"),
                   "GR-I5": ("Approval", "decide")},
    "tool_fleet": {"GR-01": ("Compliance", "decide"), "GR-02": ("Compliance", "decide"),
                   "GR-03": ("Threshold", "condition"), "GR-04": ("Threshold", "value"),
                   "GR-05": ("Approval", "decide"), "GR-06": ("Compliance", "execute"),
                   "GR-14": ("Approval", "decide"), "GR-15": ("Approval", "decide")},
    "device": {"GR-D1": ("Compliance", "condition"), "GR-D2": ("Threshold", "value"),
               "GR-D3": ("Compliance", "decide"), "GR-D4": ("Threshold", "decide"),
               "GR-D5": ("Threshold", "value"), "GR-D6": ("Approval", "decide"),
               "GR-D7": ("Compliance", "match"), "GR-D11": ("Threshold", "condition"),
               "GR-D13": ("Data quality", "match")},
}  # fmt: skip


def test_stage_keys_are_the_seven_in_order():
    assert stages.STAGE_KEYS == ("receive", "match", "condition", "value", "decide", "execute", "close")
    assert set(stages.STAGE_LABELS) == set(stages.STAGE_KEYS)
    assert stages.STAGE_LABELS["value"] == "Value each route"


def test_every_guardrail_has_type_and_stage():
    assert set(TABLE) == set(TEMPLATE_KEYS)
    n = 0
    for key, rows in TABLE.items():
        got = {g.id: (g.type, g.stage) for g in load_template(key).guardrails}
        assert got == rows, key
        n += len(got)
    assert n == 20


def test_compliance_guardrails_are_locked():
    for key in TEMPLATE_KEYS:
        for g in load_template(key).guardrails:
            assert g.locked == (g.type == "Compliance"), g.id


def test_types_change_no_decision():
    c = book.evaluated(book.get("RT-1048"))
    assert c["routes"] == book.get("RT-1048")["routes"]


def test_modeler_screen_lists_type_and_stage():
    out = client.get("/api/screens/modeler", params={"template": "tool_fleet"}, headers=h("planner-a")).json()
    assert out["template"]["key"] == "tool_fleet"
    g = next(g for g in out["template"]["guardrails"] if g["id"] == "GR-03")
    assert (g["type"], g["stage"], g["stage_label"], g["locked"]) == ("Threshold", "condition", "Condition", False)
