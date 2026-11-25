"""P9-3.3 (enabler for TF-06 and CR-02): rated life, criticality and end of parts of the tool classes, read from PLM.

After a Windchill sync (source-sim's mock, P9-3.3 seed), `plm.tool_ratings(s, org, cls)` lists the wear components of a
tool class and `plm.end_of_parts(s, org, cls)` gives the date the class's parts end and its successor model.
Needs source-sim running. The module starts and ends with the demo reset and removes the part and BOM facts it wrote.
"""

from datetime import date

import pytest
from sqlalchemy import text

from di.connectors import extra
from di.connectors.sync import run_sync
from di.core.db import SessionLocal, engine
from di.repositories import plm
from di.repositories.plm import ComponentRating
from tests import starting
from tests.helpers import call

SID = "plm_wc"


def _forget_plm() -> None:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM provenance WHERE model IN ('part', 'bom')"))
        conn.execute(text("DELETE FROM canonical WHERE model IN ('part', 'bom')"))


@pytest.fixture(scope="module", autouse=True)
def synced():
    starting.reset()
    _forget_plm()
    with SessionLocal() as s:
        extra.register(s, SID, "Customer A")
        s.commit()
    assert call("source.reconnect", {"source_id": SID}, "developer")["ok"]
    out = run_sync(SID, "manual", full=True)
    assert out["status"] == "ok" and out["records_failed"] == 0, out
    yield
    _forget_plm()
    starting.reset()


def test_plm_tool_ratings_for_cmh():
    with SessionLocal() as s:
        rows = plm.tool_ratings(s, "Customer A", "CMH")
    assert [(r.name, r.rated_life_hours, r.weight, r.critical) for r in rows] == [
        ("Motor armature", 1200.0, 0.4, True),
        ("Gearbox", 1500.0, 0.3, True),
        ("Electronics module", 2000.0, 0.2, True),
        ("Piston and seal kit", 600.0, 0.1, False),
    ]
    assert sum(r.weight for r in rows) == pytest.approx(1.0)
    assert all(isinstance(r, ComponentRating) and r.source == SID and r.revision for r in rows)


def test_plm_tool_ratings_other_classes_and_owner_boundary():
    with SessionLocal() as s:
        assert [r.name for r in plm.tool_ratings(s, "Customer A", "CRH")] == [
            "Brushless motor", "Electronics module", "Chuck assembly",
        ]  # fmt: skip
        assert plm.tool_ratings(s, "Customer A", "XXX") == []
        assert plm.tool_ratings(s, "Customer B", "CMH") == []  # another org's PLM data never answers
        assert plm.tool_ratings(s, None, "CMH") == []  # no shared PLM rows here


def test_plm_end_of_parts_for_crh():
    with SessionLocal() as s:
        assert plm.end_of_parts(s, "Customer A", "CRH") == (date(2027, 3, 31), "TF-CRH2")
        assert plm.end_of_parts(s, "Customer A", "CMH") == (date(2028, 6, 30), "TF-CMH2")
        assert plm.end_of_parts(s, "Customer A", "AGR") == (None, None)
        assert plm.end_of_parts(s, "Customer B", "CRH") == (None, None)
