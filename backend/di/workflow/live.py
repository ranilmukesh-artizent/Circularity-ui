"""The sources as the workflow checks see them now (plan 6, task C10).

The checks (di/services/actions/workflows.py `validate`) were a port of the demo's, which read the demo's source reference
(`SOURCES`: Market pricing stale, Recycler partner a manual import, AWS IoT not connected). Here they read the
source's state as it is now (`source_system`, what people changed in the Connection Fabric), over that reference:

- a source deleted in the Connection Fabric is gone (the checks say "was deleted from the Source map");
- disconnected (or not connected): `unavailable`; the connector's own `failing` or `auth_expired`: `stale`, with its
  real age (the integration screens' rule, di/repositories/fabric.py SCREEN_STATUS);
- paused: the status it had, flagged `paused` (the checks warn; the workflow list shows "Paused upstream");
- live: the demo's status for its own sources (so the seeded workspace gives the demo's checks: Market pricing stays
  19 h old, Recycler partner a manual import), `live` for a source the demo had not connected (AWS IoT once
  connected) and for sources created in the Connection Fabric.

The browser's copy of the checks (frontend/src/api/workflowGraph.ts) reads the same overlay from the workflow list
(`GET /api/screens/workflows` → `live`), so the canvas and the server agree.

`fields(s, sid)`: the field names a source's records carry (the keys of its newest landed records and the names its
field mapping uses on either side), for the field-aware settings checks (blocks.cfg_errors ctx["fields"]); None when
nothing is known (then those checks are skipped).
"""

import copy
from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from di.core import clock
from di.repositories.common import SOURCES, ms
from di.repositories.constants import MAPPINGS
from di.repositories.fabric import SCREEN_STATUS, type_of
from di.services.engine.jsmath import js_round

SAMPLE = 300  # newest landed records read per source for its field names
# the connector states that override the demo's status; live and paused keep it
_OVERRIDE = {"unavailable": "unavailable", "disconnected": "unavailable", "manual": "manual", "stale": "stale"}


def _age(m: float) -> str:
    """srcAge: "just now", "4 min", "19 h", "3 days" (di/repositories/fabric.py src_age)."""
    if m < 1:
        return "just now"
    if m < 60:
        return f"{js_round(m)} min"
    if m < 2880:
        return f"{js_round(m / 60)} h"
    return f"{js_round(m / 1440)} days"


def _fresh(last: Any, fallback: str) -> str:
    if not isinstance(last, datetime):
        return fallback
    return _age(max(0.0, (ms(clock.now().isoformat()) - ms(last.isoformat())) / 60000))


def _effective(ref: dict | None, st: str | None, prev: str | None) -> tuple[str, bool]:
    """(status, paused) for a source whose reference status is ref["status"] and whose connector state is `st`."""
    base = (ref or {}).get("status") or "live"
    paused = st == "paused"
    if paused:
        st = prev or "live"
    if st in SCREEN_STATUS and st not in _OVERRIDE:  # failing, auth_expired
        return SCREEN_STATUS[st], paused
    if st in _OVERRIDE:
        return _OVERRIDE[st], paused
    # live: the demo's status, unless the demo had not connected it
    return ("live" if base == "unavailable" else base), paused


def sources(s: Session) -> dict[str, dict]:
    """Every source that exists now, by id, in the demo's order then the ones created here; each the reference record
    (or a minimal one) with `status` (and `paused`, `connectorStatus`) as it is now. Without the tables: the reference."""
    from di.connectors import lifecycle

    try:
        with s.begin_nested():
            rows = {
                r["id"]: r
                for r in s.execute(text("SELECT id, status, vendor, type, last_success_at, owner FROM source_system")).mappings()
            }
            gone = lifecycle.deleted(s)
            cfgs = lifecycle.configs(s)
    except Exception:  # noqa: BLE001 - no Connection Fabric tables (a bare test database): the demo's reference
        return dict(SOURCES)
    out: dict[str, dict] = {}
    for sid, ref in SOURCES.items():
        if sid in gone:
            continue
        row = rows.get(sid)
        if row is None:
            out[sid] = ref
            continue
        status, paused = _effective(ref, row["status"], (cfgs.get(sid) or {}).get("prev"))
        if status == ref["status"] and not paused:
            out[sid] = ref  # as the demo has it: the same object, the same texts
            continue
        x = copy.deepcopy(ref) | {"status": status, "connectorStatus": row["status"]}
        if status == "stale" and ref["status"] != "stale":
            x["fresh"] = _fresh(row["last_success_at"], ref.get("fresh") or "—")
        if paused:
            x["paused"] = True
        out[sid] = x
    for sid, row in rows.items():  # created in the Connection Fabric
        if sid in SOURCES or sid in gone:
            continue
        cfg = cfgs.get(sid) or {}
        t = type_of(row["type"])
        status, paused = _effective(None, row["status"], cfg.get("prev"))
        x = {
            "id": sid, "name": cfg.get("name") or t["label"], "vendor": row["vendor"], "status": status,
            "connectorStatus": row["status"], "mode": cfg.get("mode") or "", "auth": cfg.get("auth") or "",
            "read": list(cfg.get("read") or []), "write": list(cfg.get("write") or []), "cat": t.get("cat", "internal"),
            "fresh": _fresh(row["last_success_at"], "—"), "type": row["type"], "owner": row["owner"] or "",
            "authority": [],
        }  # fmt: skip
        if paused:
            x["paused"] = True
        out[sid] = x
    return out


def overlay(live: dict[str, dict]) -> dict[str, dict]:
    """What the browser's checks need on top of the integration screen's sources: per source that exists, its status
    for the checks, its age and whether it is paused (GET /api/screens/workflows `live`); for a source made in the
    Connection Fabric also what the demo's MAP_TARGET and DELIVER do not know: the canonical model its mapping feeds
    (`target`) and how it takes instructions (`deliver`), as the server's checks read them."""
    from di.services.actions.workflows import made_here_lookups

    extra = made_here_lookups(live)
    return {
        sid: {"status": x["status"], "fresh": x.get("fresh") or "—", **({"paused": True} if x.get("paused") else {}),
              **extra.get(sid, {})}
        for sid, x in live.items()
    }  # fmt: skip


def mappings(s: Session) -> dict[str, list]:
    """The field mappings now (the demo's, with the ones edited here; deleted sources left out)."""
    from di.connectors import lifecycle

    try:
        with s.begin_nested():
            return lifecycle.mappings(MAPPINGS, lifecycle.configs(s), lifecycle.deleted(s))
    except Exception:  # noqa: BLE001 - no Connection Fabric tables: the demo's mappings
        return dict(MAPPINGS)


def _names(name: str) -> set[str]:
    """A mapping's field name and its last part ("Opportunity.StageName" → also "StageName"; "demand.qty" → "qty")."""
    name = str(name or "").strip()
    if not name:
        return set()
    out = {name}
    for sep in (".", "-"):
        if sep in name:
            out.add(name.rsplit(sep, 1)[1])
    return out


def fields(s: Session, sid: str, maps: dict[str, list] | None = None) -> set[str] | None:
    """The field names the source's records carry (see the module docstring), or None when nothing is known."""
    out: set[str] = set()
    try:
        with s.begin_nested():
            out |= set(
                s.execute(
                    text(
                        "SELECT DISTINCT k FROM (SELECT payload FROM raw_record WHERE source_id = :s "
                        "AND jsonb_typeof(payload) = 'object' ORDER BY fetched_at DESC LIMIT :n) x, "
                        "jsonb_object_keys(x.payload) k"
                    ),
                    {"s": sid, "n": SAMPLE},
                ).scalars()
            )
    except Exception:  # noqa: BLE001, S110 - no landed records table: the mapping alone
        pass
    for m in (maps if maps is not None else mappings(s)).get(sid) or []:
        if isinstance(m, list | tuple) and len(m) >= 3:
            out |= _names(m[0]) | _names(m[2])
    return out or None
