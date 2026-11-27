"""The rental system mock's seed, synthetic and fixed (no randomness). The pinned facts are in the package docstring.

Every function here is pure: the documents as the API serves them. `load` writes them, `reset` and `ensure` as in the
other vendor mocks.
"""

from datetime import UTC, date, datetime, timedelta

from sqlalchemy import insert, text
from sqlalchemy.engine import Connection

from sim.seed import Seed
from sim.vendors.medical_rental_system.models import RECORD, metadata

AS_OF = datetime(2026, 11, 26, 9, 0, tzinfo=UTC)  # the mock's own date, not the simulated clock's
DEVICE_CLASS = "infusion_pump"
START_DATE, DAYS = "2026-11-27", 30
HOSPITALS = (  # id, latitude, longitude, region: A, B, C lie 12, 5 and 48 miles from the East depot (haversine)
    ("HOSP-A", 40.1737, -75.0, "EAST"),
    ("HOSP-B", 40.0, -74.9054, "EAST"),
    ("HOSP-C", 39.3053, -75.0, "EAST"),
    ("HOSP-D", 40.2, -74.6, "EAST"),
    ("HOSP-E", 37.6, -121.8, "WEST"),
    ("HOSP-F", 44.2, -92.8, "NORTH"),
)
DEPOTS = (  # id, label, latitude, longitude, decontamination lines
    ("EAST", "East depot (synthetic)", 40.0, -75.0, 1),
    ("WEST", "West depot (synthetic)", 37.5, -122.0, 2),
    ("NORTH", "North depot (synthetic)", 44.0, -93.0, 2),
)
REQUESTS = (  # id, hospital, requested at
    ("REQ-1", "HOSP-A", "2026-11-25T14:00:00+00:00"),
    ("REQ-2", "HOSP-B", "2026-11-25T15:00:00+00:00"),
    ("REQ-3", "HOSP-C", "2026-11-25T16:00:00+00:00"),
    ("REQ-4", "HOSP-B", "2026-11-26T08:00:00+00:00"),  # asks again 17 hours after REQ-2
)
WEEKS = tuple((date(2026, 11, 30) + timedelta(weeks=i)).isoformat() for i in range(8))
FORECAST = {  # weekly requests for the 8 weeks from 30 Nov 2026
    "EAST": (24, 12, 18, 21, 25, 27, 26, 28),  # the lowest week starts 7 Dec
    "WEST": (20, 22, 19, 21, 23, 24, 22, 25),
    "NORTH": (14, 15, 13, 15, 16, 17, 15, 18),
}
# per depot: returns in the last 14 days, returns in the 14 days before, their waiting days in tenths (the recent ones
# sum to the depot's average: 3.4 for East, 1.6 for the others), and the share of the wait by cause in tenths
# (decon_queue, service; the rest is transport)
GROUPS = (
    ("EAST", 13, 10, 34, (-4, 4, -2, 2, -6, 6, 0, -3, 3, -1, 1, 0, 0), 26, (6, 2)),
    ("WEST", 6, 6, 16, (-2, 2, -1, 1, 0, 0), 16, (3, 4)),
    ("NORTH", 5, 5, 16, (-2, 2, -1, 1, 0), 16, (3, 4)),
)
ISOLATION = {10, 11}  # SYN-MR-IP-0010 and 0011 come back from HOSP-D's isolation ward
HOSPITAL_OVERRIDE = {10: "HOSP-D", 11: "HOSP-D", 12: "HOSP-B"}
EAST_CYCLE = ("HOSP-A", "HOSP-B", "HOSP-C", "HOSP-D")
GROUP_HOSPITAL = {"WEST": "HOSP-E", "NORTH": "HOSP-F"}
# the patient monitor with the $1,350 repair (biomed_service's SYN-MR-PM-0007): a return 40 days old, so it is in no depot's
# turnaround window (no turnaround row) and no return count above changes
MONITOR = {
    "returnId": "RET-0046",
    "tag": "SYN-MR-PM-0007",
    "hospitalId": "HOSP-B",
    "ward": "Ward 2",
    "wardType": "general",
    "depot": "EAST",
    "checkedInAt": (AS_OF - timedelta(days=40, hours=2)).isoformat(),
    "previousRentalEnd": "2026-10-17",
}


def tag(n: int) -> str:
    return f"SYN-MR-IP-{n:04d}"


def hospitals() -> list[dict]:
    return [
        {"hospitalId": h, "label": f"Hospital {h[-1]} (synthetic)", "latitude": lat, "longitude": lon, "region": region}
        for h, lat, lon, region in HOSPITALS
    ]


def depots() -> list[dict]:
    return [
        {"depotId": d, "label": label, "latitude": lat, "longitude": lon, "region": d, "deconLines": lines}
        for d, label, lat, lon, lines in DEPOTS
    ]


def requests() -> list[dict]:
    region = {h: r for h, _lat, _lon, r in HOSPITALS}
    return [
        {
            "reqId": req, "hospitalId": h, "deviceClass": DEVICE_CLASS, "startDate": START_DATE, "days": DAYS,
            "region": region[h], "requestedAt": at,
        }
        for req, h, at in REQUESTS
    ]  # fmt: skip


def forecast() -> list[dict]:
    return [
        {"region": region, "weekStart": week, "requests": n}
        for region, counts in FORECAST.items()
        for week, n in zip(WEEKS, counts, strict=True)
    ]


def _returns() -> list[tuple[dict, dict]]:
    """(return, turnaround row) per return, tags 1 to 45 in the order East recent and before, West, North."""
    out, n = [], 0
    for depot, recent, before, base, offsets, base_before, (decon_share, service_share) in GROUPS:
        tenths = [base + o for o in offsets] + [base_before] * before
        for i, total in enumerate(tenths):
            n += 1
            days_ago = i if i < recent else 15 + (i - recent)  # recent: 0 to 12 days ago, before: 15 days ago and more
            at = AS_OF - timedelta(days=days_ago, hours=3 + n % 5)
            hospital = HOSPITAL_OVERRIDE.get(n) or GROUP_HOSPITAL.get(depot) or EAST_CYCLE[(n - 1) % 4]
            isolation = n in ISOLATION
            decon, service = total * decon_share // 10, total * service_share // 10
            ret = {
                "returnId": f"RET-{n:04d}", "tag": tag(n), "hospitalId": hospital,
                "ward": "Isolation Ward 1" if isolation else f"Ward {1 + n % 6}",
                "wardType": "isolation" if isolation else "general", "depot": depot, "checkedInAt": at.isoformat(),
                "previousRentalEnd": (at.date() - timedelta(days=n % 3)).isoformat(),
            }  # fmt: skip
            row = {
                "returnId": ret["returnId"], "tag": ret["tag"], "depot": depot, "checkedInAt": ret["checkedInAt"],
                "waitingDays": {"decon_queue": decon / 10, "service": service / 10, "transport": (total - decon - service) / 10},
                "totalDays": total / 10,
            }  # fmt: skip
            out.append((ret, row))
    return out


def returns() -> list[dict]:
    """The pumps' returns (tags 1 to 45), then the patient monitor's (MONITOR)."""
    return [r for r, _t in _returns()] + [dict(MONITOR)]


def turnaround() -> list[dict]:
    return [t for _r, t in _returns()]


def _rows() -> list[dict]:
    """Every RECORD row: kind, id, list order, the filter columns and the document."""
    out: list[dict] = []

    def add(kind: str, docs: list[dict], rec_id, **cols) -> None:
        for i, d in enumerate(docs):
            out.append(
                {"kind": kind, "rec_id": rec_id(d), "ord": i, "doc": d, "depot": None, "region": None, "checked_in_at": None}
                | cols_of(d, cols)
            )

    def cols_of(d: dict, cols: dict) -> dict:
        return {c: (datetime.fromisoformat(d[f]) if c == "checked_in_at" else d[f]) for c, f in cols.items()}

    add("hospitals", hospitals(), lambda d: d["hospitalId"])
    add("depots", depots(), lambda d: d["depotId"])
    add("requests", requests(), lambda d: d["reqId"])
    add("forecast", forecast(), lambda d: f"{d['region']}:{d['weekStart']}", region="region")
    for kind, docs in (("returns", returns()), ("turnaround", turnaround())):
        add(kind, docs, lambda d: d["returnId"], depot="depot", checked_in_at="checkedInAt")
    return out


def load(conn: Connection, _s: Seed) -> dict[str, int]:
    rows = _rows()
    conn.execute(insert(RECORD), rows)
    kinds = ("hospitals", "depots", "requests", "forecast", "returns", "turnaround")
    return {k: sum(1 for r in rows if r["kind"] == k) for k in kinds}


def create(conn: Connection) -> None:
    conn.execute(text("CREATE SCHEMA IF NOT EXISTS medical_rental_system"))
    metadata.create_all(conn)


def reset(conn: Connection, s: Seed) -> dict[str, int]:
    metadata.drop_all(conn)
    create(conn)
    return load(conn, s)


def ensure(conn: Connection, s: Seed) -> None:
    create(conn)
    if conn.execute(text("SELECT count(*) FROM medical_rental_system.record")).scalar_one() == 0:
        load(conn, s)
