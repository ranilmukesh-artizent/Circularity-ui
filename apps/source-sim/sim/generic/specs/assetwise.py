"""Bentley AssetWise (the demo's SOURCES.eng): life assessments, requalification standards, engineering limits.
Read: GET /v1/assessments, /v1/standards, /v1/limits. No writes.

Field names follow the demo's MAPPINGS.eng (RUL_MONTHS, STANDARD_REF, REQUAL_STATUS). One assessment per case whose
"Engineering assessment available" evidence is not missing; RT-1048 (MTR-2041): RUL_MONTHS 36, IEC 60034-1, APPROVED.

Also holds the demo's helpers shared with the MasterControl spec: its FNV-1a hash (`hashId`) and `caseRul` (the
estimated life range and the certified period that QMS records).
"""

import math
import re
from datetime import date, datetime

from sim.generic.spec import Auth, Paging, Resource, Spec
from sim.seed import Seed
from sim.seed.model import CaseFacts

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


def month_date(text: str) -> date | None:
    """'Apr 2027' -> 2027-04-01; '—' -> None."""
    try:
        return datetime.strptime(text, "%b %Y").date()
    except (TypeError, ValueError):
        return None


def seed(s: Seed) -> dict[str, list[dict]]:
    as_of = s.world.as_of
    standards = [
        {
            "STANDARD_ID": sid,
            "STANDARD_REF": ref,
            "TITLE": title,
            "ASSET_CLASS": cls,
            "REQUAL_INTERVAL_MONTHS": months,
            "MIN_RUL_MONTHS": MIN_RUL_MONTHS,
            "STATUS": "ACTIVE",
        }
        for cls, (sid, ref, title, months) in STANDARDS.items()
    ] + [
        {
            "STANDARD_ID": sid,
            "STANDARD_REF": ref,
            "TITLE": title,
            "ASSET_CLASS": cls,
            "REQUAL_INTERVAL_MONTHS": months,
            "MIN_RUL_MONTHS": None,
            "STATUS": "ACTIVE",
        }
        for sid, ref, title, cls, months in EXTRA_STANDARDS
    ]
    limits = []
    for cls, (_, ref, _, _) in STANDARDS.items():
        pre = s.world.classes[cls].pre
        limits.append(
            {
                "LIMIT_ID": f"LIM-{pre}-RUL",
                "ASSET_CLASS": cls,
                "PARAMETER": "Remaining useful life for reuse",
                "LIMIT_TYPE": "MIN",
                "LIMIT_VALUE": MIN_RUL_MONTHS,
                "UNIT": "months",
                "STANDARD_REF": ref,
                "APPLIES_TO_ROUTES": ["redeploy", "relase", "resale"],
            }
        )
        for code, param, kind, value, unit, sref in LIMITS[cls]:
            limits.append(
                {
                    "LIMIT_ID": f"LIM-{pre}-{code}",
                    "ASSET_CLASS": cls,
                    "PARAMETER": param,
                    "LIMIT_TYPE": kind,
                    "LIMIT_VALUE": value,
                    "UNIT": unit,
                    "STANDARD_REF": sref,
                    "APPLIES_TO_ROUTES": ["redeploy", "relase", "resale", "intparts"],
                }
            )
    assessments = []
    for case in s.cases.values():
        f = case.facts
        ev = next((e for e in f.evidence if e.k == "eng"), None)
        if ev is not None and ev.state == "missing":
            continue  # the demo shows "Engineering assessment" as missing: AssetWise has nothing yet
        rul = case_rul(f)
        below = f.eng_life == "Below minimum"
        status, requal = ("APPROVED", "APPROVED") if rul else ("REJECTED", "REJECTED") if below else ("SCHEDULED", "PENDING")
        nxt = month_date(f.next_inspection)
        assessments.append(
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
                "CONDITION_GRADE": f.grade,
                "AGE_YEARS": f.age,
                "QUANTITY": f.qty,
                "NEXT_INSPECTION_DATE": nxt.isoformat() if nxt else None,
                "ASSESSED_BY": "Engineering Standards",
                "ASSESSED_AT": (f.received if f.received < as_of else as_of).isoformat(),
            }
        )
    return {"assessments": assessments, "standards": standards, "limits": limits}


SPEC = Spec(
    source_id="eng",
    title="Bentley AssetWise",
    schema="assetwise",
    base_path="/assetwise/api",
    auth=Auth("oauth_cc"),
    paging=Paging(
        "cursor",
        limit_param="$top",
        cursor_param="continuationToken",
        items_key="items",
        next_key="continuationToken",
        total_key="totalCount",
    ),
    resources=(
        Resource(
            "assessments",
            "/v1/assessments",
            "ASSESSMENT_ID",
            filters=("ASSET_ID", "ASSET_CLASS", "REQUAL_STATUS", "ASSESSMENT_STATUS", "STANDARD_REF"),
        ),
        Resource("standards", "/v1/standards", "STANDARD_ID", filters=("ASSET_CLASS", "STANDARD_REF", "STATUS")),
        Resource("limits", "/v1/limits", "LIMIT_ID", filters=("ASSET_CLASS", "LIMIT_TYPE", "STANDARD_REF")),
    ),
    seed=seed,
)
