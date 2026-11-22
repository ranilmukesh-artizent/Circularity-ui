"""What people change about a source in the Connection Fabric (B17, the source lifecycle), kept beside the connectors.

The demo kept a source's description (name, endpoint, method settings, operations, credentials, configuration
version and audit trail) and its field mapping in the browser; the backend keeps them as the workspace collection
"source_config", one item per source that has been changed or created:

    {"id": "erp", "name": ..., "cfgVer": "1.1", "audit": [...], "maps": [[...], ...], "prev": "live", "discBy": "Admin"}

- the item's descriptive fields overlay the demo's reference record (fixtures/golden/sources.json) on every screen;
- `maps` replaces the demo's field mapping (MAPPINGS) for that source, as the Data Mapping tab shows it; what a sync
  applies is its versioned copy in table field_mapping (di.connectors.mapping, plan 6 A4: source.update writes a
  version when the rows change, mapping.revert a new version equal to an older one);
- `prev` is the connector status a paused or disconnected source goes back to; `discBy` who disconnected it;
- `created` marks a source made here ("new": by hand in the source drawer, "catalog": from the catalogue).
The collection starts empty, so the seeded state is the demo's exactly.

**Deleted sources.** source.delete keeps the source's row and data; a source is deleted while the newest live journal
entry about it (source.delete or source.update, by `output_ref.source_id`) is a source.delete. Undoing that entry
(POST /api/journal/undo) brings the source back with everything it had, as the demo's Undo does; creating a source
with the same id again (source.update) also ends the deletion, and a source made in the app (a catalogue system
connected again) then starts clean: `purge` removes the deleted one's history, mappings and credentials. Deleted
sources are left out of every screen, never scheduled and never synced.

**Credentials in the mock.** Refreshing a source's credential (source.reconnect) clears source-sim's `token_expired`
fault for that system, the demo's "Feed token expired" on Ritchie Bros. Market Data: the mock then accepts the key
again, so the re-sync that follows really reads. Other faults of that system are kept.
"""

import logging
from typing import Any

import httpx
from sqlalchemy import text
from sqlalchemy.orm import Session

from di.core import state
from di.core.config import get_settings

log = logging.getLogger("di.lifecycle")
COLLECTION = "source_config"
state.register(COLLECTION, list)
# the journaled actions that decide whether a source exists: its deletion, or its (re-)creation
EXISTENCE_ACTIONS = ["source.delete", "source.update"]


def configs(s: Session) -> dict[str, dict[str, Any]]:
    return {i["id"]: i for i in state.items(s, COLLECTION)}


def config(s: Session, source_id: str) -> dict[str, Any]:
    """The source's item (for update), or a new one."""
    return state.get(s, COLLECTION, source_id, for_update=True) or {"id": source_id}


def save(s: Session, item: dict[str, Any]) -> dict[str, Any]:
    return state.put(s, COLLECTION, item["id"], item)


def deleted(s: Session) -> set[str]:
    rows = s.execute(
        text(
            "SELECT DISTINCT ON (output_ref->>'source_id') output_ref->>'source_id', action FROM action_journal "
            "WHERE NOT undone AND action = ANY(:a) AND output_ref ? 'source_id' "
            "ORDER BY output_ref->>'source_id', seq DESC"
        ),
        {"a": EXISTENCE_ACTIONS},
    ).all()
    return {sid for sid, action in rows if action == "source.delete"}


def is_deleted(s: Session, source_id: str) -> bool:
    return source_id in deleted(s)


def mappings(starting: dict[str, list], cfgs: dict[str, dict], gone: set[str]) -> dict[str, list]:
    """The field mappings now: the demo's, without deleted sources, with the ones saved here (in the demo's order,
    sources created here last)."""
    out = {k: (cfgs[k]["maps"] if "maps" in cfgs.get(k, {}) else v) for k, v in starting.items() if k not in gone}
    out |= {k: c["maps"] for k, c in cfgs.items() if "maps" in c and k not in starting and k not in gone}
    return out


# what a source made in the app leaves behind, per source (purge)
PURGED = (
    "sync_run", "fetch_log", "raw_record", "sync_cursor", "failed_record", "webhook_event", "field_mapping",
    "source_connection", "source_secret",
)  # fmt: skip


def purge(s: Session, source_id: str) -> None:
    """A source made in the app (catalogue, by hand) connected again under the id of a deleted one starts clean: the
    deleted source's sync runs, fetches, landed records, cursors, held records, webhook events, mapping versions,
    connection and credentials are removed, its queued syncs dropped and its retry schedule reset. Called only when
    the source is created again: until then Undo of the delete brings the deleted source back with all of it. The
    canonical facts it wrote (on keys of its own, `<system>:<key>`) and their provenance stay; the new source's syncs
    write them again."""
    for t in PURGED:
        s.execute(text(f"DELETE FROM {t} WHERE source_id = :i"), {"i": source_id})  # noqa: S608 - fixed names
    s.execute(text("DELETE FROM job WHERE kind = 'sync.source' AND payload->>'source_id' = :i"), {"i": source_id})
    s.execute(text("UPDATE source_system SET fail_streak = 0, next_retry_at = NULL WHERE id = :i"), {"i": source_id})


def refresh_credentials(source_id: str) -> bool:
    """Clear source-sim's token_expired fault for this system (keeping its other faults). True if one was cleared.
    Best effort: a source-sim that does not answer is logged; the reconnect itself is recorded either way."""
    base = get_settings().source_sim_url.rstrip("/") + "/_sim/faults"
    try:
        active = httpx.get(base, timeout=5).json()
        mine = [f for f in active if f.get("system") == source_id]
        if not any(f.get("kind") == "token_expired" for f in mine):
            return False
        httpx.delete(base, params={"system": source_id}, timeout=5).raise_for_status()
        for f in mine:
            if f.get("kind") != "token_expired":
                body = {k: f.get(k) for k in ("system", "kind", "value", "every", "note") if f.get(k) is not None}
                httpx.post(base, json=body, timeout=5)
        return True
    except (httpx.HTTPError, ValueError):
        log.warning("could not refresh the credential of %s in source-sim", source_id, exc_info=True)
        return False
