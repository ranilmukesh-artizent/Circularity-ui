"""Audit & provenance (#/audit; docs/backend-steps.md, B14): the log of evidence fetches and system events, the evidence
gaps, provenance records and comments.

    GET /api/screens/audit?tenant_filter=All
        entries   the demo's auditEntries() for the signed-in account: one "fetch" entry per evidence item of each
                  visible case (not missing), with its full provenance record (p), then one "event" entry per
                  instruction or event (ev) the account may see; the agent layer's additions (who acted, the agent
                  that prepared it, the run) are in `used` and `prep`. Case order, then the event log's order (newest
                  first); the page sorts and filters (search, source, kind, provenance, prepared by agent) itself.
        gaps      the demo's auditGaps(): {c: {id, assetId, evidence}, e: evidence item} for each missing item, with
                  its provenance record (p: status "unavailable" and the reason) for the data trace
        comments  the comments on the visible entries, keyed "au:<entry id>" (the demo's S.cm), oldest first
    GET /api/screens/audit/provenance?case_id=&key=   the demo's provenanceOf(caseId, key): {c, ev, p}
    GET /api/screens/audit/comments?key=              the comments under any record key (audit entries, sources ...)
    POST /api/actions/comment.add                     posting a comment (B12)

The endpoints are in di.routes.screens.audit; this module builds what they return.

Where the data comes from:
- cases: the database (di.services.cases.store), scoped like the demo's visCases (tenants, a Warehouse Manager's warehouse,
  and the top bar's tenant filter);
- events: the workspace collection "events" (di.core.state), the demo's EVENTS with what actions have added since;
- comments: the workspace collection "comments" (written by comment.add);
- provenance: the demo's provFor (di.repositories.provenance.prov_for, shared with the Case pages;
  di.repositories.cases.provenance ports only the fields its reads use). It describes each item by the demo's source catalogue
  (fixtures/golden/sources.json: name, vendor, access mode, authentication, status), which is what the page shows
  today. The connectors also keep a real HTTP fetch log (table fetch_log, GET /api/fetch-log, B9); it records the
  sync calls, not one fetch per evidence item, so it is not mixed into these entries. B17 can add it to the page as
  its own section.

Facade mapping (frontend/src/api/audit.ts), for the switch-over (B17):

| export                         | served by                                                                    |
|--------------------------------|------------------------------------------------------------------------------|
| auditEntries()                 | endpoint: GET /api/screens/audit (entries; ts as ISO strings)                 |
| auditGaps()                    | endpoint: same answer (gaps)                                                  |
| comments(key)                  | endpoint: same answer (comments) for audit entries; /audit/comments?key=      |
| provenanceOf(caseId, key)      | endpoint: GET /api/screens/audit/provenance (also in entries[].p, gaps[].p)    |
| caseById(id)                   | endpoint: GET /api/screens/audit/provenance (c), or the case APIs             |
| postComment(key, text)         | action: comment.add (already served)                                          |
| isoT, eventJson, ackKind       | frontend-only: formatting                                                     |
"""

from typing import Any

from sqlalchemy.orm import Session

from di.core import policy, state
from di.core.auth import Principal
from di.core.errors import ApiError
from di.repositories.common import iso
from di.repositories.context import call_ctx, can_see_case, visible_cases
from di.repositories.provenance import prov_for
from di.services.cases import store

Case = dict[str, Any]


# ---------------------------------------------------------------- the log
def _event_used(ev: dict) -> str:
    if ev.get("decisionId"):
        used = f"Decision {ev['decisionId']}" + (f" · {ev['approval']}" if ev.get("approval") else "")
    elif ev.get("by"):
        used = "Access control · " + ev["by"]
    else:
        used = "Fabric housekeeping"
    # the agent layer's addition: who acted, the agent that prepared it, the run
    if ev.get("by") or ev.get("prep") or ev.get("run"):
        used += (
            (" · by " + ev["by"] if ev.get("by") else "")
            + (f" · prepared by agent ({ev['prep']})" if ev.get("prep") else "")
            + (" · " + ev["run"] if ev.get("run") else "")
        )
    return used


def entries(p: Principal, session: Session, tenant_filter: str = "All") -> list[dict]:
    """The demo's auditEntries() (with the agent layer's additions), for the signed-in account."""
    ctx = call_ctx(p, session)
    out: list[dict] = []
    for c in visible_cases(ctx, tenant_filter):
        for e in c.get("evidence") or []:
            if e["state"] == "missing":
                continue
            pv = prov_for(c, e)
            out.append({
                "id": "AU-" + pv["id"], "kind": "fetch", "ts": pv["fetchedAt"], "source": pv["sourceName"],
                "caseId": c["id"], "asset": c["assetId"], "item": e["label"], "key": e["k"], "request": pv["request"],
                "result": "Partial record" if pv["status"] == "partial" else "1 record · " + (pv["table"] or "—"),
                "used": "; ".join(pv["usedIn"][:2]), "status": pv["status"], "prep": None, "p": pv,
            })  # fmt: skip
    by_id = {c["id"]: c for c in store.all_cases(session)}
    tenant_scoped = bool(policy.policy(p.account).get("tenantScoped"))
    for ev in state.items(session, "events", newest_first=True):
        ec = by_id.get(ev.get("caseId")) if ev.get("caseId") else None
        if ec is not None:
            if not can_see_case(p.account, p.ctx, ec):
                continue
            if tenant_filter != "All" and ec["owner"] != tenant_filter:
                continue
        elif tenant_scoped:
            continue
        direction = "Outbound " if ev.get("dir") == "out" else "Inbound "
        key = ev.get("key")
        out.append({
            "id": "AE-" + ev["id"], "kind": "event", "ts": iso(ev["ts"]), "source": ev.get("dest"),
            "caseId": ev.get("caseId") or "—", "asset": ec["assetId"] if ec else "—", "item": ev.get("type"), "key": "event",
            "request": direction + str(ev.get("type")) + (" · " + key if key and key != "—" else ""),
            "result": ev.get("ack"), "used": _event_used(ev), "status": "recorded", "prep": ev.get("prep") or None, "ev": ev,
        })  # fmt: skip
    return out


def gaps(p: Principal, session: Session, tenant_filter: str = "All") -> list[dict]:
    """The demo's auditGaps(): each missing evidence item of the visible cases, with its (unavailable) provenance."""
    out = []
    for c in visible_cases(call_ctx(p, session), tenant_filter):
        lite = {"id": c["id"], "assetId": c["assetId"], "evidence": c.get("evidence") or []}
        for e in c.get("evidence") or []:
            if e["state"] == "missing":
                out.append({"c": lite, "e": e, "p": prov_for(c, e)})
    return out


def comments_by_key(session: Session, keys: set[str] | None = None) -> dict[str, list[dict]]:
    """Comments (state collection "comments"), grouped by record key, oldest first, as the demo's S.cm."""
    out: dict[str, list[dict]] = {}
    for x in state.items(session, "comments"):
        if keys is None or x.get("key") in keys:
            out.setdefault(x["key"], []).append(
                {"by": x.get("by"), "at": x.get("at"), "text": x.get("text"), "prep": x.get("prep")}
            )
    return out


def page(p: Principal, session: Session, tenant_filter: str = "All") -> dict:
    """GET /api/screens/audit: the entries, the gaps and the comments on the entries."""
    es = entries(p, session, tenant_filter)
    return {
        "entries": es,
        "gaps": gaps(p, session, tenant_filter),
        "comments": comments_by_key(session, {"au:" + x["id"] for x in es}),
    }


def provenance_of(p: Principal, session: Session, case_id: str, key: str) -> dict:
    """The demo's provenanceOf(caseId, key): {c, ev, p}; 404 for an unknown case or item, the record boundary checked."""
    c = store.get(session, case_id)
    if c is None:
        raise ApiError("not_found", f"No case {case_id}.", 404)
    p.require_record(case_id, c["owner"], c["location"])
    ev = next((x for x in c.get("evidence") or [] if x["k"] == key), None)
    if ev is None:
        raise ApiError("not_found", f"{case_id} has no evidence item {key}.", 404)
    lite = {"id": c["id"], "assetId": c["assetId"], "evidence": c.get("evidence") or []}
    return {"c": lite, "ev": ev, "p": prov_for(c, ev)}


def comments(session: Session, key: str) -> list[dict]:
    """Comments under one record key (an audit entry "au:<id>", a source "src:<id>" ...), oldest first."""
    return comments_by_key(session, {key}).get(key, [])
