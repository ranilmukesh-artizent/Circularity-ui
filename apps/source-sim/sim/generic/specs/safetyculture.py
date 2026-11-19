"""SafetyCulture iAuditor (the demo's SOURCES.insp): inspection reports, condition grades, photos, checklist results.
Read: GET /audits/search, /audits/{audit_id}, /media/{media_id}. Write: POST /inspections/start, POST /actions.

An audit exists for every case whose inspection or photo evidence comes from "Inspection" (the demo's evidence
source names; "MRO" evidence lives in Oracle Depot Repair instead) and is not missing. The grade is the case grade;
a partial inspection (e.g. RT-1050: "Visual inspection only") is an in-progress audit without a grade; media count is
zero when the demo says the photos are missing ("Grade given without photo evidence").

Routing note: `/audits/search` is its own resource (the lightweight id + modified_at listing iAuditor returns) and is
declared before `/audits`, so `GET /audits/search` is not taken for `GET /audits/{audit_id}`.
"""

import hashlib
from datetime import datetime, timedelta

from sim.generic.spec import Auth, Paging, Resource, Spec
from sim.generic.specs.manhattan import facility_id
from sim.generic.specs.shiplane import as_hex, case_no
from sim.seed import Seed
from sim.seed.model import CaseFacts

# components checked per class: the demo's EX_BOM component names, so findings line up with repair parts
COMPONENTS = {
    "motor": ["Bearings", "Rotor and shaft", "Housing and frame", "Terminal box", "Stator winding"],
    "pump": ["Pistons and barrel", "Shaft seal", "Bearings", "Housing", "Ports and fittings"],
    "control": ["Processor module", "I/O modules", "Power supply", "Connectors", "Firmware"],
    "drill": ["Motor", "Gearbox", "Chuck", "Housing", "Battery"],
    "batch": ["Drivers", "Battery packs", "Chucks", "Housings", "Chargers"],
    "it": ["Battery", "Display", "Keyboard", "Storage", "Chassis"],
}
FUNCTIONAL = {
    "motor": "No-load run and vibration",
    "pump": "Pressure and flow test",
    "control": "Functional and I/O self-test",
    "drill": "Function test under load",
    "batch": "Function test (sample)",
    "it": "Power-on self-test",
}
# RT-1048's workshop diagnosis (the demo's EX_SCOPE parts map to these components)
SCOPE_COMPONENTS = {"RT-1048": ["Bearings", "Housing and frame", "Terminal box", "Stator winding"]}


def component_findings(f: CaseFacts) -> list[dict]:
    """One finding per component, consistent with the grade: A all good, B one worn, C two worn + one replace,
    D two replace + one worn. Deterministic per case."""
    comps = COMPONENTS[f.cls]
    if f.id in SCOPE_COMPONENTS:
        bad = SCOPE_COMPONENTS[f.id]
        return [
            {"component": c, "status": "Worn" if c in bad else "Good", "action": "Replace" if c in bad else "None"} for c in comps
        ]
    start = as_hex(f.id, "|insp|c") % len(comps)
    order = comps[start:] + comps[:start]
    plan = {"A": [], "B": ["Worn"], "C": ["Replace", "Worn", "Worn"], "D": ["Replace", "Replace", "Worn"]}.get(f.grade or "", [])
    status = {c: "Good" for c in comps} | dict(zip(order, plan, strict=False))
    act = {"Good": "None", "Worn": "Repair", "Replace": "Replace"}
    return [{"component": c, "status": status[c], "action": act[status[c]]} for c in comps]


def _hex(*parts: str, n: int = 32) -> str:
    return hashlib.md5("|".join(parts).encode()).hexdigest()[:n]


def audit_id(f: CaseFacts) -> str:
    return "audit_" + _hex(f.id, "audit")


def inspected_at(f: CaseFacts, as_of: datetime) -> datetime:
    t = f.received + timedelta(days=as_hex(f.id, "|insp|d") % 2, hours=9 + as_hex(f.id, "|insp|h") % 8)
    return min(t, as_of - timedelta(hours=2))


TEMPLATES = {cls: "template_" + _hex(cls, "template") for cls in COMPONENTS}
INSPECTORS = ["A. Raman", "S. Iyer", "P. Kulkarni", "M. Fernandes"]


def seed(s: Seed) -> dict[str, list[dict]]:
    search, audits, media, actions = [], [], [], []
    for case in s.cases.values():
        f = case.facts
        ev = {e.k: e for e in f.evidence}
        insp, photo = ev.get("insp"), ev.get("photo")
        mine = [e for e in (insp, photo) if e and e.source == "Inspection" and e.state != "missing"]
        if not mine:
            continue
        aid = audit_id(f)
        complete = bool(insp and insp.source == "Inspection" and insp.state == "ready" and f.grade)
        at = inspected_at(f, s.world.as_of)
        photos = photo is not None and photo.source == "Inspection" and photo.state == "ready"
        n_media = (6 + as_hex(f.id, "|insp|m") % 9) if photos else 0
        findings = component_findings(f) if complete else []
        items = [
            {
                "item_id": f"item_{i + 1:02d}",
                "label": f"{x['component']} condition",
                "type": "question",
                "response": {"Good": "Pass", "Worn": "Attention", "Replace": "Fail"}[x["status"]],
                "action_required": x["action"],
                "score": {"Good": 1, "Worn": 0.5, "Replace": 0}[x["status"]],
                "max_score": 1,
            }
            for i, x in enumerate(findings)
        ]
        functional_done = complete and not any("Functional test not run" in e.note for e in f.evidence)
        items.append(
            {
                "item_id": f"item_{len(items) + 1:02d}",
                "label": FUNCTIONAL[f.cls],
                "type": "question",
                "response": ("Fail" if f.grade == "D" else "Pass") if functional_done else None,
                "action_required": None if functional_done else "Run test",
                "score": (0 if f.grade == "D" else 1) if functional_done else None,
                "max_score": 1,
            }
        )
        scored = [x for x in items if x["score"] is not None]
        score = round(100 * sum(x["score"] for x in scored) / len(scored), 1) if scored else None
        modified = at + timedelta(minutes=35 + as_hex(f.id, "|insp|dur") % 50)
        media_ids = [f"media_{_hex(f.id, 'media', str(i), n=24)}" for i in range(n_media)]
        search.append(
            {
                "audit_id": aid,
                "template_id": TEMPLATES[f.cls],
                "created_at": at.isoformat(),
                "modified_at": modified.isoformat(),
                "archived": False,
            }
        )
        audits.append(
            {
                "audit_id": aid,
                "template_id": TEMPLATES[f.cls],
                "created_at": at.isoformat(),
                "modified_at": modified.isoformat(),
                "audit_data": {
                    "name": f"{f.id} / {f.asset_id} · {f.product} receiving inspection",
                    "document_no": f"INS-{20000 + case_no(f.id) * 7 % 997}",
                    "date_started": at.isoformat(),
                    "date_completed": modified.isoformat() if complete else None,
                    "status": "complete" if complete else "in_progress",
                    "score_percentage": score,
                    "authorship": {"author": INSPECTORS[as_hex(f.id, "|insp|who") % len(INSPECTORS)]},
                    "site": {"site_id": facility_id(f.location), "name": f.location},
                },
                "template_data": {"metadata": {"name": f"Returned {f.product.lower()} · receiving inspection v3"}},
                "header_items": {
                    "asset_id": f.asset_id,
                    "return_reference": f.id,
                    "owner": f.owner,
                    "manufacturer": f.mfr,
                },
                "asset_id": f.asset_id,
                "grade_text": f"Grade {f.grade}" if complete else None,
                "condition": f.condition,
                "items": items,
                "media_count": n_media,
                "media_ids": media_ids,
                "notes": insp.note if insp and insp.source == "Inspection" and insp.note else "",
            }
        )
        for i, mid in enumerate(media_ids):
            media.append(
                {
                    "media_id": mid,
                    "audit_id": aid,
                    "file_name": f"{f.asset_id}_{i + 1:02d}.jpg",
                    "content_type": "image/jpeg",
                    "label": ["Nameplate", "Overall view", "Damage close-up", "Serial label"][i % 4]
                    if i < 4
                    else f"Detail {i - 3}",
                    "taken_at": (at + timedelta(minutes=3 * i)).isoformat(),
                    "size_bytes": 900_000 + as_hex(mid, "s") % 2_400_000,
                    "download_url": f"/safetyculture/media/{mid}",
                }
            )
        for x in items:
            if x["action_required"] in ("Replace", "Repair", "Run test"):
                actions.append(
                    {
                        "action_id": f"action_{_hex(aid, x['item_id'], n=24)}",
                        "audit_id": aid,
                        "item_id": x["item_id"],
                        "title": f"{x['action_required']}: {x['label']} · {f.asset_id}",
                        "status": "to_do",
                        "priority": "high" if x["action_required"] == "Replace" else "medium",
                        "assignee": "Repair centre (RC01)",
                        "created_at": modified.isoformat(),
                        "due_at": (modified + timedelta(days=5)).isoformat(),
                        "return_reference": f.id,
                    }
                )
    return {"audit_search": search, "audits": audits, "media": media, "inspections": [], "actions": actions}


SPEC = Spec(
    source_id="insp",
    title="SafetyCulture",
    schema="safetyculture",
    base_path="/safetyculture",
    auth=Auth("oauth_cc"),
    paging=Paging(
        "offset", limit_param="limit", offset_param="offset", items_key="data", next_key="next_offset", total_key="total"
    ),
    resources=(
        # before /audits: GET /audits/search must not be read as GET /audits/{audit_id}
        Resource("audit_search", "/audits/search", "audit_id", filters=("template_id", "archived")),
        Resource("audits", "/audits", "audit_id", filters=("template_id", "asset_id", "grade_text")),
        Resource("media", "/media", "media_id", filters=("audit_id",)),
        Resource(
            "inspections",
            "/inspections/start",
            "audit_id",
            filters=("template_id",),
            create=True,
            id_format="audit_{n:032x}",
            event="safetyculture.inspection",
        ),
        Resource(
            "actions",
            "/actions",
            "action_id",
            filters=("audit_id", "status", "priority", "return_reference"),
            create=True,
            update=True,
            id_format="action_{n:024x}",
            event="safetyculture.action",
        ),
    ),
    updated_since_param="modified_after",
    seed=seed,
)
