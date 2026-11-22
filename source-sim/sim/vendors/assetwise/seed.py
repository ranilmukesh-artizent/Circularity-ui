"""Load the seed (B2) into the AssetWise engineering data warehouse, as AssetWise would hold it at the demo's as-of time.

Three warehouse entity sets (one row per entity in `assetwise.entity`, columns as the warehouse views name them):
- LifeAssessments: one per case whose "Engineering assessment available" evidence is not missing. RT-1048 (MTR-2041):
  RUL_MONTHS 36 (range 30-40), IEC 60034-1, REQUAL_STATUS APPROVED, APPROVAL_STATUS Approved, valid for the
  standard's requalification interval (24 months for motors) from approval. Assessments with a life estimate are
  approved; "Below minimum" ones are rejected; the rest are drafts (scheduled, requalification pending).
- Standards: the requalification standard of each asset class (IEC 60034-1 for motors, 24-month interval, minimum
  remaining life 12 months) and three supporting standards.
- EngineeringLimits: the minimum remaining life per class and the class's engineering limits.

Also holds the demo's helpers shared with other mocks: its FNV-1a hash (`hash_id`) and `case_rul` (the estimated life
range and the certified period that QMS records).
"""

import math
import re
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import Column, DateTime, MetaData, String, Table, insert, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Connection

from sim.seed import Seed
from sim.seed.model import CaseFacts

metadata = MetaData(schema="assetwise")
ENTITY = Table(
    "entity",
    metadata,
    Column("entity_set", String(40), primary_key=True),
    Column("key", String(40), primary_key=True),
    Column("data", JSONB, nullable=False),
    Column("modified_on", DateTime(timezone=True), nullable=False),
)
KEYS = {"LifeAssessments": "ASSESSMENT_ID", "Standards": "STANDARD_ID", "EngineeringLimits": "LIMIT_ID"}

# class -> (standard id, reference, title, requalification interval in months)
STANDARDS = {
    "motor": ("STD-MTR-01", "IEC 60034-1", "Rotating electrical machines - rating and performance", 24),
    "pump": ("STD-PMP-01", "ISO 4413", "Hydraulic fluid power - general rules and safety requirements", 24),
    "control": ("STD-CTL-01", "IEC 61131-2", "Programmable controllers - equipment requirements and tests", 12),
    "drill": ("STD-DRL-01", "IEC 62841-1", "Electric motor-operated hand-held tools - safety", 12),
    "batch": ("STD-BAT-01", "IEC 62133-2", "Secondary lithium cells and batteries - safety requirements", 12),
    "it": ("STD-ITE-01", "IEC 62368-1", "ICT equipment - safety requirements", 12),
}
EXTRA_STANDARDS = [
    ("STD-CTL-02", "IEC 61508", "Functional safety of E/E/PE safety-related systems", "control", 12),
    ("STD-MTR-02", "ISO 20816-3", "Mechanical vibration - industrial machines above 15 kW", "motor", 12),
    ("STD-ITE-02", "NIST SP 800-88", "Guidelines for media sanitization", "it", 0),
]
MIN_RUL_MONTHS = 12  # below this the demo says "Below minimum"
# class -> [(code, parameter, MIN|MAX, value, unit, standard ref)]
LIMITS = {
    "motor": [
        ("INS", "Insulation resistance at 500 V DC", "MIN", 100, "MOhm", "IEC 60034-1"),
        ("VIB", "Vibration velocity (RMS)", "MAX", 2.8, "mm/s", "ISO 20816-3"),
    ],
    "pump": [
        ("VEF", "Volumetric efficiency at rated pressure", "MIN", 85, "%", "ISO 4413"),
        ("LKG", "Case drain leakage", "MAX", 1.5, "l/min", "ISO 4413"),
    ],
    "control": [("SLF", "Self-test errors", "MAX", 2, "count", "IEC 61131-2")],
    "drill": [("CYC", "Battery charge cycles", "MAX", 500, "cycles", "IEC 62841-1")],
    "batch": [("BHL", "Battery state of health", "MIN", 60, "%", "IEC 62133-2")],
    "it": [("BHL", "Battery state of health", "MIN", 60, "%", "IEC 62368-1")],
}
STANDARDS_DATE = datetime(2025, 11, 3, 8, 0, tzinfo=UTC)  # when the warehouse's reference rows were last changed
APPROVER = "Engineering Standards"


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
    hi = max(est, js_round(est * (1.2 if wide else 1.11)))
    cert = (lo // 12) * 12 if lo >= 12 else max(6, (lo // 6) * 6)
    return {
        "est": est,
        "low": min(lo, est),
        "high": hi,
        "cert_months": min(cert, est),
        "cert_ref": f"QMS-{2400 + hash_id(f.id + 'qms') % 600}",
    }


def month_date(text_: str) -> date | None:
    """'Apr 2027' -> 2027-04-01; '—' -> None."""
    try:
        return datetime.strptime(text_, "%b %Y").date()  # noqa: DTZ007 - a calendar date, no time zone involved
    except (TypeError, ValueError):
        return None


def add_months(d: datetime, months: int) -> datetime:
    y, m = divmod(d.month - 1 + months, 12)
    day = min(d.day, [31, 29 if (d.year + y) % 4 == 0 else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m])
    return d.replace(year=d.year + y, month=m + 1, day=day)


def z(d: datetime | None) -> str | None:
    return d.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z") if d else None


def rows(s: Seed) -> list[dict]:
    as_of = s.world.as_of
    out: list[dict] = []

    def add(entity_set: str, data: dict, modified: datetime) -> None:
        data = data | {"MODIFIED_ON": z(modified)}
        out.append({"entity_set": entity_set, "key": data[KEYS[entity_set]], "data": data, "modified_on": modified})

    for cls, (sid, ref, title, months) in STANDARDS.items():
        add(
            "Standards",
            {
                "STANDARD_ID": sid,
                "STANDARD_REF": ref,
                "TITLE": title,
                "ASSET_CLASS": cls,
                "REQUAL_INTERVAL_MONTHS": months,
                "MIN_RUL_MONTHS": MIN_RUL_MONTHS,
                "STATUS": "ACTIVE",
            },
            STANDARDS_DATE,
        )
    for sid, ref, title, cls, months in EXTRA_STANDARDS:
        add(
            "Standards",
            {
                "STANDARD_ID": sid,
                "STANDARD_REF": ref,
                "TITLE": title,
                "ASSET_CLASS": cls,
                "REQUAL_INTERVAL_MONTHS": months,
                "MIN_RUL_MONTHS": None,
                "STATUS": "ACTIVE",
            },
            STANDARDS_DATE,
        )
    for cls, (_, ref, _, _) in STANDARDS.items():
        pre = s.world.classes[cls].pre
        add(
            "EngineeringLimits",
            {
                "LIMIT_ID": f"LIM-{pre}-RUL",
                "ASSET_CLASS": cls,
                "PARAMETER": "Remaining useful life for reuse",
                "LIMIT_TYPE": "MIN",
                "LIMIT_VALUE": MIN_RUL_MONTHS,
                "UNIT": "months",
                "STANDARD_REF": ref,
                "APPLIES_TO_ROUTES": ["redeploy", "relase", "resale"],
            },
            STANDARDS_DATE,
        )
        for code, param, kind, value, unit, sref in LIMITS[cls]:
            add(
                "EngineeringLimits",
                {
                    "LIMIT_ID": f"LIM-{pre}-{code}",
                    "ASSET_CLASS": cls,
                    "PARAMETER": param,
                    "LIMIT_TYPE": kind,
                    "LIMIT_VALUE": value,
                    "UNIT": unit,
                    "STANDARD_REF": sref,
                    "APPLIES_TO_ROUTES": ["redeploy", "relase", "resale", "intparts"],
                },
                STANDARDS_DATE,
            )

    for case in s.cases.values():
        f = case.facts
        ev = next((e for e in f.evidence if e.k == "eng"), None)
        if ev is not None and ev.state == "missing":
            continue  # the demo shows "Engineering assessment" as missing: AssetWise has nothing yet
        rul = case_rul(f)
        below = f.eng_life == "Below minimum"
        assessed = min(f.received, as_of)
        if rul:
            status, requal, approval = "APPROVED", "APPROVED", "Approved"
        elif below:
            status, requal, approval = "REJECTED", "REJECTED", "Rejected"
        else:
            status, requal, approval = "SCHEDULED", "PENDING", "Draft"
        approved_at = assessed + timedelta(hours=4) if approval != "Draft" else None
        months = STANDARDS[f.cls][3]
        nxt = month_date(f.next_inspection)
        add(
            "LifeAssessments",
            {
                "ASSESSMENT_ID": f"LA-{f.asset_id}",
                "ASSET_ID": f.asset_id,
                "ASSET_CLASS": f.cls,
                "MANUFACTURER": f.mfr,
                "METHOD": "Remaining useful life assessment",
                "LIFE_TEXT": f.eng_life,
                "RUL_MONTHS": rul["est"] if rul else None,
                "RUL_LOW_MONTHS": rul["low"] if rul else None,
                "RUL_HIGH_MONTHS": rul["high"] if rul else None,
                "MIN_RUL_MONTHS": MIN_RUL_MONTHS,
                "CONFIDENCE": None if not rul else "MEDIUM" if f.grade == "C" else "HIGH",
                "STANDARD_REF": STANDARDS[f.cls][1],
                "ASSESSMENT_STATUS": status,
                "REQUAL_STATUS": requal,
                "APPROVAL_STATUS": approval,
                "APPROVED_BY": APPROVER if approval == "Approved" else None,
                "APPROVED_AT": z(approved_at) if approval == "Approved" else None,
                "VALID_FROM": z(approved_at) if approval == "Approved" else None,
                "VALID_UNTIL": z(add_months(approved_at, months)) if approval == "Approved" else None,
                "CONDITION_GRADE": f.grade,
                "AGE_YEARS": f.age,
                "QUANTITY": f.qty,
                "NEXT_INSPECTION_DATE": nxt.isoformat() if nxt else None,
                "ASSESSED_BY": APPROVER,
                "ASSESSED_AT": z(assessed),
            },
            approved_at or assessed,
        )
    return out


def load(conn: Connection, s: Seed) -> dict[str, int]:
    data = rows(s)
    conn.execute(insert(ENTITY), data)
    counts: dict[str, int] = {}
    for r in data:
        counts[r["entity_set"]] = counts.get(r["entity_set"], 0) + 1
    return counts


def create(conn: Connection) -> None:
    conn.execute(text("CREATE SCHEMA IF NOT EXISTS assetwise"))
    metadata.create_all(conn)


def reset(conn: Connection, s: Seed) -> dict[str, int]:
    metadata.drop_all(conn)
    create(conn)
    return load(conn, s)


def ensure(conn: Connection, s: Seed) -> None:
    create(conn)
    if conn.execute(text("SELECT count(*) FROM assetwise.entity")).scalar_one() == 0:
        load(conn, s)
