"""The Connection Fabric's health as Home and the Command Center read it (ported from the demo): the starting workflow
catalogue without its random run data (wfSeed, wfStat), integration health (S.hh, hhTotals), source exceptions
(smExceptions), open conflicts, stale sources and the workspace events (EVENTS)."""

from di.actions.pipeline import CallContext
from di.reads import workspace as ws
from di.reads.common import (
    SOURCES,
    STARTING_CONFLICTS,
    STARTING_MAPPINGS,
    hash_id,
)

WF_DEC = ["Standard six-gate decision", "Pool allocation to approval", "Evidence gaps and demand first"]


def workflows() -> list[dict]:
    """The demo's starting workflows without their random run data: one ingest per source (a draft when the source is
    not connected), one outbound per write channel, and the three decision workflows. The Oracle Depot Repair ingest
    is the one whose last run failed (STARTING_FAILED_WORKFLOWS)."""
    out: list[dict] = []

    def add(name: str, src: str | None, status: str = "published") -> None:
        failing = name in ws.STARTING_FAILED_WORKFLOWS
        out.append({"id": f"WF-{101 + len(out)}", "name": name, "src": src, "status": status, "failing": failing})

    for s in SOURCES.values():
        add("Ingest · " + s["vendor"], s["id"], "draft" if s["status"] == "unavailable" else "published")
    for s in SOURCES.values():
        if s.get("write"):
            for ch in ("api", "file") if s["type"] == "erp" else ("api",):
                add("Outbound · " + s["vendor"] + (" (interface file)" if ch == "file" else ""), s["id"])
    for name in WF_DEC:
        add(name, None)
    return out


def wf_stat(w: dict) -> str:
    """The demo's wfStat."""
    return "failing" if w["status"] == "published" and w["failing"] else w["status"]


def hh() -> list[dict]:
    """The demo's S.hh: 24 hourly buckets of successful, warning and failed syncs and events (hhInit)."""
    out = []
    for i in range(24):
        h = int(hash_id(f"hh{i}"), 16)
        out.append(
            {
                "ok": 18 + h % 30,
                "warn": 2 + h % 4 if h % 5 == 0 else 1 if h % 3 == 0 else 0,
                "bad": 2 if h % 11 == 0 else 1 if h % 7 == 0 else 0,
            }
        )
    return out


def hh_totals() -> dict:
    """The demo's hhTotals: the last 24 hours' totals, the runs in progress and the success share."""
    t = {"ok": 0, "warn": 0, "bad": 0}
    for b in hh():
        for k in t:
            t[k] += b[k]
    t["run"] = sum(1 for s in SOURCES.values() if s.get("syncing"))  # no workflow runs on the server
    n = t["ok"] + t["warn"] + t["bad"]
    t["pct"] = t["ok"] / n * 100 if n else 100
    return t


def sm_exceptions() -> list[dict]:
    """The demo's smExceptions: sources not connected, stale or unmapped, and open conflicts."""
    o: list[dict] = []
    for s in SOURCES.values():
        if s["status"] == "unavailable":
            o.append({"src": s["name"], "obj": s["vendor"], "issue": "Not connected: no feed", "sev": "High", "st": "Open"})
        elif s["status"] == "stale":
            o.append({"src": s["name"], "obj": s["vendor"], "issue": "Feed token expired", "sev": "High", "st": "Open"})
        if s["status"] != "unavailable" and not STARTING_MAPPINGS.get(s["id"]):
            o.append({"src": s["name"], "obj": s["vendor"], "issue": "No field mapping defined", "sev": "High", "st": "Open"})
        elif s["status"] == "manual":
            o.append(
                {
                    "src": s["name"],
                    "obj": s["vendor"],
                    "issue": "Manual import only, no live feed",
                    "sev": "Low",
                    "st": "In Progress",
                }
            )
    for c in open_conflicts():
        o.append(
            {
                "src": c["a"]["src"],
                "obj": c["asset"],
                "issue": c["kind"] + " differs from " + c["b"]["src"],
                "sev": "Medium",
                "st": "Open",
            }
        )
    return o


def open_conflicts() -> list[dict]:
    return [c for c in STARTING_CONFLICTS if c["status"] == "open"]


def stale_sources() -> list[dict]:
    return [s for s in SOURCES.values() if s["status"] in ("stale", "unavailable")]


def ws_events(ctx: CallContext) -> list[dict]:
    """The demo's EVENTS, newest first (the workspace collection "events")."""
    from di import state

    return state.items(ctx.session, "events", newest_first=True)
