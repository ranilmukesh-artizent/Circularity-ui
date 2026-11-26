"""The biomedical service mock's seed: a service record for each of the 80 devices, notices and assessments, synthetic.

Computed from the tag's number (no randomness); `service_docs()`, `corrections()` and `assessments()` are pure. The pinned
records are in the package docstring.
"""

from datetime import date, timedelta

from sqlalchemy import insert, text
from sqlalchemy.engine import Connection

from sim.seed import Seed
from sim.vendors.biomed_service.models import ASSESSMENT, CORRECTION, SERVICE, metadata
from sim.vendors.medical_asset_mgmt.seed import CLASSES

AS_OF = date(2026, 10, 7)  # the demo's as-of date
STANDARD = "IEC 62353"  # the standard the recorded electrical safety test names
PM_CODES = {"IP": "PM-12M", "PM": "PM-12M", "EB": "PM-6M", "SD": "PM-12M", "TV": "PM-6M", "PO": "PM-24M"}
PINNED = {  # tag -> overrides of the generated record
    "SYN-MR-IP-0001": {
        "pmDue": "2027-02-15", "pmCode": "PM-12M", "lastPm": "2026-02-15", "certificationExpiry": "2027-03-31",
        "notes": [{"text": "Housing scuff", "kind": "cosmetic"}],
    },
    "SYN-MR-IP-0002": {"certificationExpiry": "2026-12-07"},
    "SYN-MR-PM-0007": {
        "repairEstimate": 1350, "faults": ["Display backlight failure"],
        "notes": [{"text": "Display backlight failure", "kind": "fault"}],
    },
    "SYN-MR-IP-0030": {"model": "IP-300", "serialNo": 3030},
    "SYN-MR-IP-0031": {"model": "IP-300", "serialNo": 3131},
}  # fmt: skip
NOTICES = (
    {"noticeId": "FSN-031", "model": "IP-300", "serialFrom": 3000, "serialTo": 3099, "status": "open",
     "correctionRef": "FSN-031-A"},
    {"noticeId": "FSN-018", "model": "PM-100", "serialFrom": 1100, "serialTo": 1199, "status": "closed",
     "correctionRef": "FSN-018-B"},
)  # fmt: skip
ASSESSMENTS = (
    {"tag": "SYN-MR-EB-0040", "plannedWork": "Replace mattress cover and castors; electrical safety retest",
     "result": "servicing", "assessedBy": "Biomedical engineer 2", "at": "2026-10-05"},
    {"tag": "SYN-MR-EB-0041", "plannedWork": "Replace actuator and control unit; repaint frame; full retest",
     "result": "full_refurbishment", "assessedBy": "Biomedical engineer 2", "at": "2026-10-05"},
)  # fmt: skip


def _day(offset: int) -> str:
    return (AS_OF + timedelta(days=offset)).isoformat()


def _service(code: str, k: int) -> dict:
    tag = f"SYN-MR-{code}-{k:04d}"
    pump = code == "IP"
    base = {
        "tag": tag,
        "model": "IP-200" if pump else f"{code}-100",
        "serialNo": (2000 if pump else 1000) + k,
        "pmDue": _day(20 + (k * 11) % 300),
        "pmCode": PM_CODES[code],
        "lastPm": _day(-30 - (k * 13) % 300),
        "certificationExpiry": _day(120 + (k * 19) % 400),
        "functionalTest": {"result": "pass", "at": _day(-10 - k % 20)},
        "electricalSafety": {"standard": STANDARD, "result": "pass", "at": _day(-10 - k % 20)},
        "notes": [],
        "repairEstimate": 0,
        "faults": [],
    }
    return base | PINNED.get(tag, {})


def service_docs() -> list[dict]:
    return [_service(code, k) for _cls, code, count, _price, _models in CLASSES for k in range(1, count + 1)]


def corrections() -> list[dict]:
    return [dict(n) for n in NOTICES]


def assessments() -> list[dict]:
    return [dict(a) for a in ASSESSMENTS]


def load(conn: Connection, _s: Seed) -> dict[str, int]:
    docs = service_docs()
    conn.execute(insert(SERVICE), [{"tag": d["tag"], "ord": i, "doc": d} for i, d in enumerate(docs)])
    conn.execute(insert(CORRECTION), [{"notice_id": n["noticeId"], "ord": i, "doc": n} for i, n in enumerate(corrections())])
    conn.execute(insert(ASSESSMENT), [{"tag": a["tag"], "ord": i, "doc": a} for i, a in enumerate(assessments())])
    return {"service": len(docs), "correction": len(NOTICES), "assessment": len(ASSESSMENTS)}


def create(conn: Connection) -> None:
    conn.execute(text("CREATE SCHEMA IF NOT EXISTS biomed_service"))
    metadata.create_all(conn)


def reset(conn: Connection, s: Seed) -> dict[str, int]:
    metadata.drop_all(conn)
    create(conn)
    return load(conn, s)


def ensure(conn: Connection, s: Seed) -> None:
    create(conn)
    if conn.execute(text("SELECT count(*) FROM biomed_service.service")).scalar_one() == 0:
        load(conn, s)
