"""MasterControl seed: the demo's reuse policies, life certificates, test criteria and deviations (B5b).

Values and identifiers are those of the replaced generic mock (sim/generic/specs/mastercontrol.py): a life certificate
for every case the demo can certify (its caseRul), so RT-1048 (MTR-2041) holds QMS-2906, 24 months, CERT_EXPIRY
2027-03-01 (the first day of the month before the next inspection, Apr 2027), REUSE_CLASS ALLOWED_CAT2 under
POL-REUSE-MTR v3.2, TEST_RESULT PASS. The demo's CF-32: CTL-0122 requalified 12 Sep 2026.

Revision history (so "only effective documents are policy" has something to decide): every class policy has the
superseded previous revision (effective 2025-04-01) and the motor policy a draft v3.3 in approval.
The demo's helpers (hashId, caseRul) are copied here so this mock does not depend on the AssetWise mock.
"""

import math
import re
from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import insert, text
from sqlalchemy.engine import Connection

from sim.seed import Seed
from sim.seed.model import CaseFacts
from sim.vendors.mastercontrol import tables as t

# class -> (reuse class, policy title, revision)
REUSE = {
    "motor": ("ALLOWED_CAT2", "Reuse and redeployment of industrial motors", "3.2"),
    "pump": ("ALLOWED_CAT2", "Reuse and redeployment of hydraulic pumps", "3.2"),
    "control": ("ALLOWED_CAT3", "Reuse of control units and PLCs (requalification required)", "2.4"),
    "drill": ("ALLOWED_CAT1", "Reuse and resale of power tools", "1.9"),
    "batch": ("RESTRICTED_CAT4", "Reuse of tool-fleet batches with Li-ion cells", "2.0"),
    "it": ("ALLOWED_CAT2", "Reuse and resale of IT electronics (data erasure required)", "4.1"),
}
STANDARD_REF = {  # the class's requalification standard (as AssetWise holds it)
    "motor": "IEC 60034-1",
    "pump": "ISO 4413",
    "control": "IEC 61131-2",
    "drill": "IEC 62841-1",
    "batch": "IEC 62133-2",
    "it": "IEC 62368-1",
}
OTHER_DOCS = [
    ("SOP-DATA-ERASE", "Data sanitization before release of IT assets", "4.0", "it", "NIST SP 800-88"),
    ("SOP-LIION-REQUAL", "Requalification of used Li-ion cells and packs", "1.3", "batch", "IEC 62133-2"),
    ("POL-RECYCLER-CERT", "Certification requirements for recycler and exit partners", "2.1", None, "ISO 14001 / R2v3"),
    ("POL-LIFE-CERT", "Certification of remaining operating life", "3.0", None, None),
]
DRAFTS = [("motor", "3.3", "ALLOWED_CAT1")]  # in approval: not policy until released and effective
# class -> [(test name, method, acceptance criteria)] (the demo's workshop operations, EX_OPS)
TESTS = {
    "motor": [
        ("Surge and insulation test", "Surge comparison + insulation resistance at 500 V DC", ">= 100 MOhm; no surge mismatch"),
        ("Load test bench", "3 h at rated load", "Temperature rise within class F; current within 5 % of nameplate"),
        ("Balancing", "Dynamic balancing of the rotor", "Balance grade G2.5"),
        ("Vibration check", "Velocity RMS at bearings", "<= 2.8 mm/s"),
    ],
    "pump": [
        ("Test rig", "Flow and pressure at rated speed", "Volumetric efficiency >= 85 %"),
        ("Flushing rig", "Fluid cleanliness after flush", "ISO 4406 18/16/13 or better"),
    ],
    "control": [
        ("Burn-in rack", "8 h powered burn-in", "No resets; self-test errors <= 2"),
        ("Functional test station", "I/O and communication test", "All channels pass"),
    ],
    "drill": [
        ("Battery cycler", "Capacity test over 2 cycles", ">= 70 % of rated capacity"),
        ("Function test", "No-load and load run", "No abnormal noise, sparking or overheating"),
    ],
    "batch": [
        ("Battery cycler", "Capacity test per pack", ">= 60 % state of health"),
        ("Function test", "Sample function test per lot", "All sampled tools pass"),
    ],
    "it": [
        ("Imaging station", "Reimage and data erasure verification", "Erasure certificate issued"),
        ("Battery test", "Full charge and discharge", ">= 60 % state of health"),
    ],
}
REQUALIFIED = {"CTL-0122": date(2026, 9, 12)}  # the demo's conflict CF-32: QMS says requalified 12 Sep
# (id, title, asset, severity, status, disposition, approver, opened, closed) - DEV-118 / Q. Lead are the demo's
DEVIATIONS = [
    (
        "DEV-117",
        "Self-test errors above limit at first burn-in (3 > 2); requalified after firmware reflash",
        "CTL-0122",
        "Minor",
        "Closed",
        "Rework and retest",
        "Q. Lead",
        date(2026, 9, 8),
        date(2026, 9, 12),
    ),
    (
        "DEV-118",
        "Bearing temperature above limit during load test; bearing set replaced, retest passed",
        "MTR-2041",
        "Minor",
        "Closed",
        "Rework and retest",
        "Q. Lead",
        date(2026, 10, 5),
        date(2026, 10, 6),
    ),
]
OWNER = "Quality Assurance"
SEED_USER = "qa.admin"


# ------------------------------------------------------------------ the demo's helpers
def hash_id(s: str) -> int:
    """The demo's hashId (32-bit FNV-1a), as an int."""
    h = 2166136261
    for ch in s:
        h ^= ord(ch)
        h = (h * 16777619) & 0xFFFFFFFF
    return h


def js_round(x: float) -> int:
    return math.floor(x + 0.5)


def case_rul(f: CaseFacts) -> dict | None:
    """The demo's caseRul: estimated remaining life range and the certified period (never above the estimate)."""
    m = re.match(r"^(\d+)\s*months", f.eng_life or "")
    if not m:
        return None
    est = int(m.group(1))
    wide = f.grade == "C"
    lo = js_round(est * (0.75 if wide else 0.83))
    cert = (lo // 12) * 12 if lo >= 12 else max(6, (lo // 6) * 6)
    return {"cert_months": min(cert, est), "cert_ref": f"QMS-{2400 + hash_id(f.id + 'qms') % 600}"}


def month_date(text_: str) -> date | None:
    """'Apr 2027' -> 2027-04-01; '—' -> None."""
    try:
        return datetime.strptime(text_, "%b %Y").date()
    except (TypeError, ValueError):
        return None


def add_months(d: date, months: int) -> date:
    y, m = divmod(d.month - 1 + months, 12)
    return date(d.year + y, m + 1, 1)


def previous_revision(rev: str) -> str:
    major, minor = (int(x) for x in rev.split("."))
    return f"{major}.{minor - 1}" if minor else f"{major - 1}.9"


def _stamp(d: date, as_of: datetime) -> datetime:
    """A seeded change time: the business date at 00:00 UTC, never after the seed's as-of time."""
    return min(datetime.combine(d, time(0), tzinfo=UTC), as_of)


# ------------------------------------------------------------------ rows
def rows(s: Seed) -> dict[str, list[dict]]:
    as_of = s.world.as_of
    today = as_of.date()
    docs: list[dict] = []

    def doc(number, title, rev, type_, lifecycle, effective, fields, created):
        docs.append(
            {
                "infocard_id": f"IC-{len(docs) + 1:05d}",
                "document_number": number,
                "revision": rev,
                "title": title,
                "infocard_type": type_,
                "lifecycle": lifecycle,
                "effective_date": effective,
                "owner": OWNER,
                "data_fields": fields,
                "created_date": _stamp(created, as_of),
                "last_modified_date": _stamp(effective or created, as_of),
            }
        )

    for cls, (reuse, title, rev) in REUSE.items():
        number = f"POL-REUSE-{s.world.classes[cls].pre}"
        fields = {"ASSET_CLASS": cls, "REUSE_CLASS": reuse, "STANDARD_REF": STANDARD_REF[cls]}
        doc(number, title, previous_revision(rev), "Policy", "Released", date(2025, 4, 1), fields, date(2025, 3, 15))
        doc(number, title, rev, "Policy", "Released", date(2026, 4, 1), fields, date(2026, 3, 16))
    for num, title, rev, cls, ref in OTHER_DOCS:
        fields = {"ASSET_CLASS": cls, "REUSE_CLASS": None, "STANDARD_REF": ref}
        doc(
            num, title, rev, "SOP" if num.startswith("SOP") else "Policy", "Released", date(2026, 1, 15), fields, date(2026, 1, 5)
        )
    for cls, rev, reuse in DRAFTS:
        number = f"POL-REUSE-{s.world.classes[cls].pre}"
        fields = {"ASSET_CLASS": cls, "REUSE_CLASS": reuse, "STANDARD_REF": STANDARD_REF[cls]}
        doc(number, REUSE[cls][1], rev, "Policy", "In Approval", None, fields, date(2026, 9, 28))

    criteria = []
    for cls, tests in TESTS.items():
        pre = s.world.classes[cls].pre
        for i, (name, method, accept) in enumerate(tests, 1):
            criteria.append(
                {
                    "test_id": f"TC-{pre}-{i:02d}",
                    "test_name": name,
                    "asset_class": cls,
                    "method": method,
                    "acceptance_criteria": accept,
                    "standard_ref": STANDARD_REF[cls],
                    "mandatory_for_routes": ["redeploy", "relase", "resale"] if i == 1 else ["redeploy", "relase"],
                    "document_number": f"POL-REUSE-{pre}",
                    "last_modified_date": _stamp(date(2026, 4, 1), as_of),
                }
            )

    certs = []

    def cert(record_id, number, type_, issued, fields):
        stamp = _stamp(issued, as_of)
        certs.append(
            {
                "record_id": record_id,
                "certificate_number": number,
                "certificate_type": type_,
                "issued_date": issued,
                "revoked_date": None,
                "revoke_reason": None,
                "data_fields": fields,
                "created_by": SEED_USER,
                "created_date": stamp,
                "last_modified_date": stamp,
            }
        )

    for case in s.cases.values():
        f = case.facts
        issued = min(f.received.date() + timedelta(days=1), today)
        pre = s.world.classes[f.cls].pre
        rul = case_rul(f)
        if rul:
            nxt = month_date(f.next_inspection)
            expiry = add_months(nxt, -1) if nxt else add_months(issued, rul["cert_months"])
            basis = (
                "Certified by the EAM diagnostic and quality process after "
                + (f"grade {f.grade} inspection" if f.grade else "inspection")
                + " and any part replacement"
            )
            cert(
                f"CERT-{f.asset_id}",
                rul["cert_ref"],
                "LIFE_CERTIFICATION",
                issued,
                {
                    "ASSET_ID": f.asset_id,
                    "ASSET_CLASS": f.cls,
                    "CERTIFIED_LIFE_MONTHS": rul["cert_months"],
                    "CERT_EXPIRY": expiry.isoformat(),
                    "TEST_RESULT": "PASS",
                    "REUSE_CLASS": REUSE[f.cls][0],
                    "DOCUMENT_NUMBER": f"POL-REUSE-{pre}",
                    "BASIS": basis,
                },
            )
        if f.cls == "it" and f.spec.get("Data erasure") == "Certified":
            cert(
                f"DE-{f.asset_id}",
                f"DE-{f.asset_id}",
                "DATA_ERASURE",
                issued,
                {
                    "ASSET_ID": f.asset_id,
                    "ASSET_CLASS": f.cls,
                    "CERTIFIED_LIFE_MONTHS": None,
                    "CERT_EXPIRY": None,
                    "TEST_RESULT": "PASS",
                    "REUSE_CLASS": REUSE[f.cls][0],
                    "DOCUMENT_NUMBER": "SOP-DATA-ERASE",
                    "BASIS": f"{f.qty} of {f.qty} devices erased (NIST SP 800-88 purge)",
                },
            )
    for asset, when in REQUALIFIED.items():
        cert(
            f"CERT-{asset}",
            f"RQ-{asset}",
            "REQUALIFICATION",
            when,
            {
                "ASSET_ID": asset,
                "ASSET_CLASS": "control",
                "CERTIFIED_LIFE_MONTHS": 12,
                "CERT_EXPIRY": add_months(when, 12).isoformat(),
                "TEST_RESULT": "PASS",
                "REUSE_CLASS": REUSE["control"][0],
                "DOCUMENT_NUMBER": "POL-REUSE-CTL",
                "BASIS": "Requalified after burn-in and functional test",
            },
        )

    deviations = [
        {
            "deviation_id": i,
            "title": title,
            "asset_id": asset,
            "severity": sev,
            "status": st,
            "disposition": disp,
            "approver_name": appr,
            "opened_date": opened,
            "closed_date": closed,
            "last_modified_date": _stamp(closed or opened, as_of),
        }
        for i, title, asset, sev, st, disp, appr, opened, closed in DEVIATIONS
    ]
    return {"document": docs, "certificate": certs, "test_criterion": criteria, "deviation": deviations}


def load(conn: Connection, seed: Seed) -> dict[str, int]:
    data = rows(seed)
    tables = {"document": t.DOCUMENT, "certificate": t.CERTIFICATE, "test_criterion": t.TEST_CRITERION, "deviation": t.DEVIATION}
    for name, table in tables.items():
        if data[name]:
            conn.execute(insert(table), data[name])
    conn.execute(insert(t.COUNTER), [{"name": "certificate", "value": 0}])
    return {name: len(data[name]) for name in tables}


def create(conn: Connection) -> None:
    conn.execute(text("CREATE SCHEMA IF NOT EXISTS mastercontrol"))
    t.metadata.create_all(conn)


def reset(conn: Connection, seed: Seed) -> dict[str, int]:
    t.metadata.drop_all(conn)
    create(conn)
    return load(conn, seed)


def ensure(conn: Connection, seed: Seed) -> None:
    create(conn)
    if conn.execute(text("SELECT count(*) FROM mastercontrol.document")).scalar_one() == 0:
        load(conn, seed)
