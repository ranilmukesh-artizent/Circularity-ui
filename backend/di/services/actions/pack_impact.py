"""What publishing a pack version would change (plan 9, P9-1.6; stories X-01 and X-03), for `pack.import`: the open cases
of the pack's key in scope and the pack's sample queue, each decided by `decide_case` (I-6, R19) under the pack in force
and under the new version, with the owner's published flow and customer overlay laid over both.

    impact(s, old, new, org_unit_id) -> {"changed": n, "total": n, "dv": dollars}

`changed` counts the decisions whose route or hold differs; `dv` is the sum of the recommendations' net over all of them,
new minus old (a held or unvalued decision is worth nothing). The pack files and stored versions are never changed.
Never does: write a row. Industrial book cases carry no template key and are not counted (the engine decides them).
"""

from collections.abc import Mapping
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from di.core import orgs
from di.repositories.live_rules import flow_version, live_pack
from di.repositories.orgs import units
from di.services.cases import decide, store
from di.services.engine.jsmath import js_round
from di.services.modeler.compile import FlowVersion
from di.services.modeler.pack import Pack
from di.services.modeler.valuers import device, tool_fleet


def _open_cases(s: Session, key: str, org_unit_id: str | None) -> list[store.Case]:
    """The open cases of the key whose owner is the org or below it (every owner for a pack for every org)."""
    rows = s.execute(
        text("SELECT data FROM case_record WHERE stage <> 'closed' AND data ->> 'template' = :k ORDER BY id"), {"k": key}
    ).scalars()
    tree = units(s)
    return [c for c in rows if org_unit_id is None or org_unit_id in orgs.ancestors(tree, c["owner"])]


def _samples(kind: str) -> tuple[list[Mapping[str, Any]], list[Mapping[str, Any]] | None]:
    """The pack's sample queue by valuer kind, and the world a tool-fleet sample is planned in."""
    if kind == "tool_fleet":
        return list(tool_fleet.sample_queue()), list(tool_fleet.sample_live_cases())
    if kind == "device":
        return list(device.sample_lots()), None
    return [], None


def _net(d: decide.Decision) -> float:
    return d.net if d.recommendation else 0.0


def impact(s: Session, old: Pack, new: Pack, org_unit_id: str | None) -> dict[str, Any]:
    """The decisions that differ under `new` from `old` (module docstring)."""
    changed, total, dv = 0, 0, 0.0

    def compare(c: Mapping[str, Any], fv: FlowVersion, owner: str, queue: list[Mapping[str, Any]] | None) -> None:
        nonlocal changed, total, dv
        probe = {"template": new.key, "owner": owner}
        before = decide.decide_case(c, live_pack(s, probe, old), fv, session=s, queue=queue)
        after = decide.decide_case(c, live_pack(s, probe, new), fv, session=s, queue=queue)
        total += 1
        changed += int((before.route, before.hold is None) != (after.route, after.hold is None))
        dv += _net(after) - _net(before)

    for doc in _open_cases(s, new.key, org_unit_id):
        compare(doc, flow_version(s, dict(doc)), doc["owner"], None)
    sample, world = _samples(new.valuer.kind)
    for lot in sample:
        compare(lot, FlowVersion(None, 0, ()), org_unit_id or "workspace", world)
    return {"changed": changed, "total": total, "dv": js_round(dv)}
