"""The instruction row update only writes known columns (refactor A3, F15)."""

import pytest

from di.services.instructions.send import _update


def test_update_refuses_an_unknown_column(session):
    with pytest.raises(ValueError, match="not an updatable instruction column"):
        _update(session, 0, **{"status = 'x'; --": "y"})
    with pytest.raises(ValueError, match="not an updatable instruction column"):
        _update(session, 0, approval_ref="x")
    session.rollback()


def test_update_accepts_the_columns_send_writes(session):
    _update(  # id 0 matches no row: the statement only has to be valid
        session, 0, status="failed", last_error="e", simulated=True, due_at=None, sent_at=None, request=[], waiting_for=None
    )
    session.rollback()


def test_finance_names_the_material_only_for_an_industrial_asset(monkeypatch):
    """S/4 refuses a journal item naming a material it lacks: only an industrial asset is one (MARA); a tool serial is not
    (smoke-p9-3 step 14: "material CMH-48213 does not exist" failed the re-issue's finance step)."""
    from di.services.instructions import writers

    seen: list = []
    monkeypatch.setattr(writers, "post_journal", lambda s, ins, ref, header, items: (seen.append(items), ("1", {}))[1])
    terms = [{"label": "Refurbishment", "kind": "prep", "amt": -400}, {"label": "Lease renewal", "kind": "lease", "amt": 900}]
    base = {"id": "RT-9001", "exec": {"ref": "APR-2026-11-9001"}, "location": "Warehouse 1", "recommendation": {"terms": terms}}
    writers.finance(None, {"idem_key": "k"}, base | {"assetId": "MTR-2041"}, {})  # type: ignore[arg-type]
    writers.finance(None, {"idem_key": "k"}, base | {"assetId": "CMH-48213", "template": "tool_fleet"}, {})  # type: ignore[arg-type]
    industrial, tool = seen
    assert len(tool) == len(industrial) == 3  # two cost lines and the clearing line
    assert all("<Material>MTR-2041</Material>" in it for it in industrial[:-1])
    assert not any("<Material>" in it for it in tool)
