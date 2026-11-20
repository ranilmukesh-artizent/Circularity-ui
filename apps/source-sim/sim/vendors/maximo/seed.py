"""Load the seed (B2) into the Maximo tables, as Maximo would hold it at the demo's as-of time.

What Maximo owns here (the demo's SOURCES.eam: "installed base, asset registry, work orders, failure history,
criticality"):
- sites:        org NFIND (Northfield India); one Maximo site per facility, coded as in the WMS (Manhattan): Warehouse 1/2 and the
                Repair centre -> WH01, WH02, RC01; customer sites Site 1..8 -> ST01..ST08 (S/4 plants 2010/2020/2030 and
                1010..1080). Locations: <site>-RTN (returns bay) at the facilities, <site>-PROD at customer sites.
- assets:       every returned asset (ASSETNUM = the demo's asset id, e.g. MTR-2041) at its facility's returns bay,
                with owner tenant (PLUSCUSTOMER), condition code (grade + modifier: RT-1048 is B+, as in the demo's
                mapping CONDITIONCODE B+ -> grade B), RATED_PWR etc. in ASSETSPEC (55 kW -> 55000 W) and a RUNHOURS
                meter (RT-1048: 18,450 h). The installed base adds the assets of the 1,400 closed decisions: OPERATING
                at the customer site when redeployed or re-leased, DECOMMISSIONED otherwise.
- work orders:  per returned asset, newest first: the return inspection (INSP, at the facility; COMP when graded,
                APPR when not inspected, INPRG when a test is required), half-yearly PMs back to the install date at
                the customer site (the last one is LASTSERVICEDATE: RT-1048 2026-03-14T08:20:00+05:30), corrective
                work orders with failure reports (problem/cause/remedy) by grade (D: 3, C: 2, B: 1 on even cases,
                A: 0; RT-1048's is BRG-WEAR with ACTLABCOST 420.00 USD, supervisor R. Kumar), the next periodic
                inspection (INSP, WAPPR, targeted at the demo's next inspection month), and, for executing cases, the
                refurbishment (REFURB) or teardown (TDOWN) work order at the Repair centre: INPRG while the demo's step
                is active, COMP once acknowledged (EXTERNALREFID = the demo's WO-4xxxx).
- numbering:    WONUM = case number + sequence (RT-1048 -> 1048001, 1048002, ...), WORKORDERID from 10001.
"""

import base64
import re
from datetime import UTC, date, datetime, time, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import insert, text
from sqlalchemy.engine import Connection

from sim.seed import Seed
from sim.vendors.maximo import tables as t

IST = timezone(timedelta(hours=5, minutes=30), "IST")
ORG = "NFIND"  # Northfield India
FACILITY_SITES = {"Warehouse 1": "WH01", "Warehouse 2": "WH02", "Repair centre": "RC01"}
SYSTEM_USER = "MXINTADM"
LABOR_RATE = Decimal("70.00")  # USD per hour
SUPERVISORS = ("R. Kumar", "S. Iyer", "A. Menon", "P. Nair")
ANCHOR = 1048  # RT-1048, the demo's hero case: derived numbers are anchored on it
CRITICALITY = {"control": (1, 9), "motor": (2, 8), "pump": (2, 8), "it": (3, 5), "drill": (4, 3), "batch": (4, 3)}

# failure class (WORKORDER.FAILURECODE) and (problem, cause, remedy) triples per asset class
FAILURES: dict[str, tuple[str, list[tuple[tuple[str, str], tuple[str, str], tuple[str, str]]]]] = {
    "motor": (
        "MOTOR",
        [
            (("BRG-WEAR", "Bearing wear"), ("LUBE-LOSS", "Loss of lubrication"), ("BRG-REPL", "Replace bearings")),
            (("WDG-INSUL", "Winding insulation breakdown"), ("OVERLOAD", "Sustained overload"), ("REWIND", "Rewind stator")),
            (("VIB-HIGH", "High vibration"), ("MISALIGN", "Shaft misalignment"), ("REALIGN", "Realign and balance")),
        ],
    ),
    "pump": (
        "PUMP",
        [
            (("SEAL-LEAK", "Mechanical seal leak"), ("SEAL-WEAR", "Seal face wear"), ("SEAL-REPL", "Replace seal")),
            (("CAV-DMG", "Cavitation damage"), ("LOW-NPSH", "Insufficient suction head"), ("IMP-REPL", "Replace impeller")),
            (("PRESS-LOW", "Low discharge pressure"), ("CONTAM", "Fluid contamination"), ("FLUSH", "Flush and refill")),
        ],
    ),
    "control": (
        "CONTROL",
        [
            (("IO-FAULT", "I/O module fault"), ("SURGE", "Voltage surge"), ("IO-REPL", "Replace I/O module")),
            (("PSU-FAIL", "Power supply failure"), ("CAP-AGE", "Capacitor ageing"), ("PSU-REPL", "Replace power supply")),
            (("FW-ERR", "Firmware error"), ("FW-BUG", "Firmware defect"), ("FW-UPD", "Update firmware")),
        ],
    ),
    "drill": (
        "TOOL",
        [
            (("BAT-DEGR", "Battery capacity degraded"), ("CYCLE-AGE", "Charge cycle ageing"), ("BAT-REPL", "Replace battery")),
            (("MTR-BRUSH", "Motor brush wear"), ("DUTY-HIGH", "High duty cycle"), ("BRUSH-REPL", "Replace brushes")),
            (("CHUCK-WEAR", "Chuck wear"), ("MISUSE", "Misuse"), ("CHUCK-REPL", "Replace chuck")),
        ],
    ),
    "it": (
        "ITEQ",
        [
            (("DISK-FAIL", "Disk failure"), ("MEDIA-WEAR", "Media wear"), ("DISK-REPL", "Replace disk")),
            (("PSU-FAIL", "Power supply failure"), ("CAP-AGE", "Capacitor ageing"), ("PSU-REPL", "Replace power supply")),
            (("BOARD-FLT", "Main board fault"), ("THERMAL", "Thermal stress"), ("BOARD-REPL", "Replace main board")),
        ],
    ),
    "batch": (
        "TOOLFLT",
        [
            (("BAT-DEGR", "Battery capacity degraded"), ("CYCLE-AGE", "Charge cycle ageing"), ("BAT-REPL", "Replace battery")),
            (("CHRG-FAIL", "Charger failure"), ("SURGE", "Voltage surge"), ("CHRG-REPL", "Replace charger")),
            (("HOUS-CRACK", "Housing cracked"), ("IMPACT", "Impact damage"), ("HOUS-REPL", "Replace housing")),
        ],
    ),
}


def run_hours_reading(f) -> Decimal:
    """The RUNHOURS meter reading of a returned asset (CaseFacts), taken when it was received. RT-1048: 6.4 years ->
    18,450 h. The AWS IoT mock's hour counters agree with it (sim/vendors/aws_iot/seed.py)."""
    n = int(f.id.split("-")[1])
    factor = (1.0, 0.85, 1.15, 0.9, 1.1, 0.95, 1.05)[(n - ANCHOR) % 7]
    return Decimal(round(f.age * 2882.8125 * factor))


def site_code(place: str) -> str:
    """Warehouse 1 -> WH01, Repair centre -> RC01, Site 3 -> ST03."""
    return FACILITY_SITES.get(place) or "ST" + place.split()[-1].zfill(2)


def rest_id(*key: str) -> str:
    """Maximo's resource id: base64 of the key attributes joined by '/', '=' padding written as '-'."""
    return "_" + base64.b64encode("/".join(key).encode()).decode().replace("=", "-")


def money(v: float | Decimal) -> Decimal:
    return Decimal(str(v)).quantize(Decimal("0.01"), ROUND_HALF_UP)


def _at(d: date, hh: int, mm: int = 0) -> datetime:
    return datetime.combine(d, time(hh, mm), IST).astimezone(UTC)


def _iso(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def _spec_rows(spec: dict) -> list[dict]:
    out = []
    for name, value in spec.items():
        attr = re.sub(r"[^A-Z0-9]+", "_", name.upper()).strip("_")
        row = {"assetattrid": attr, "numvalue": None, "alnvalue": None, "measureunitid": None}
        m = re.fullmatch(r"([\d,]+(?:\.\d+)?)\s*(kW|W|V|rpm|bar|l/min|m3/h|Ah|GB|TB|mm|kg|Nm)", str(value).strip())
        if name.lower() == "rated power" and m:
            n = Decimal(m.group(1).replace(",", ""))
            row |= {"assetattrid": "RATED_PWR", "numvalue": n * 1000 if m.group(2) == "kW" else n, "measureunitid": "W"}
        elif m:
            row |= {"numvalue": Decimal(m.group(1).replace(",", "")), "measureunitid": m.group(2).upper()}
        else:
            row["alnvalue"] = str(value)[:60]
        out.append(row)
    return out


def _next_inspection(text_: str) -> date | None:
    try:
        return datetime.strptime(text_, "%b %Y").date()
    except ValueError:
        return None


class _Book:
    """Collects rows and hands out ids."""

    def __init__(self):
        self.rows: dict[str, list[dict]] = {k: [] for k in ("asset", "assetmeter", "assetspec", "workorder", "wostatus", "fr")}
        self.woid = 10000
        self.frid = 50000

    def wo(self, n: int, seq: int, **v) -> dict:
        self.woid += 1
        wonum = f"{n}{seq:03d}"
        row = {
            "workorderid": self.woid,
            "wonum": wonum,
            "orgid": ORG,
            "woclass": "WORKORDER",
            "reportedby": SYSTEM_USER,
            "changeby": SYSTEM_USER,
            "estlabhrs": None,
            "estlabcost": None,
            "estmatcost": None,
            "actlabhrs": None,
            "actlabcost": None,
            "actmatcost": None,
            "actstart": None,
            "actfinish": None,
            "targstartdate": None,
            "targcompdate": None,
            "failurecode": None,
            "problemcode": None,
            "supervisor": None,
            "externalrefid": None,
            "wopriority": None,
        } | v
        row["changedate"] = row["statusdate"]
        self.rows["workorder"].append(row)
        # status history: the path Maximo would have recorded to reach the current status
        path = {
            "WAPPR": ["WAPPR"],
            "APPR": ["WAPPR", "APPR"],
            "INPRG": ["WAPPR", "APPR", "INPRG"],
            "COMP": ["WAPPR", "APPR", "INPRG", "COMP"],
            "CLOSE": ["WAPPR", "APPR", "INPRG", "COMP", "CLOSE"],
        }[row["status"]]
        stamps = [row["reportdate"], row["reportdate"], row["actstart"], row["actfinish"], row["statusdate"]]
        for i, st in enumerate(path):
            when = stamps[i] or row["statusdate"]
            self.rows["wostatus"].append(
                {"wonum": wonum, "siteid": row["siteid"], "status": st, "changedate": when, "changeby": SYSTEM_USER, "memo": None}
            )
        return row

    def failure(self, wo: dict, triple) -> None:
        for linenum, (kind, (code, desc)) in enumerate(zip(("PROBLEM", "CAUSE", "REMEDY"), triple, strict=True), start=1):
            self.frid += 1
            self.rows["fr"].append(
                {
                    "failurereportid": self.frid,
                    "wonum": wo["wonum"],
                    "siteid": wo["siteid"],
                    "assetnum": wo["assetnum"],
                    "failurecode": code,
                    "description": desc,
                    "type": kind,
                    "linenum": linenum,
                    "reportdate": wo["reportdate"],
                }
            )


def _case_history(b: _Book, seed: Seed, case) -> tuple[Decimal, datetime | None]:
    """Work orders for one returned asset; returns (total actual cost, last service date)."""
    w, f = seed.world, case.facts
    n = int(f.id.split("-")[1])
    cls = w.classes[f.cls]
    as_of = w.as_of
    today = as_of.astimezone(IST).date()
    fac = site_code(f.location)
    origin = f"ST{(n * 3) % 8 + 1:02d}"  # where it was installed before the return
    install = (f.received - timedelta(days=round(f.age * 365.25))).astimezone(IST).date()
    fclass, catalogue = FAILURES[f.cls]
    common = {"assetnum": f.asset_id, "wopriority": CRITICALITY[f.cls][0]}
    hist: list[dict] = []  # (built oldest first, numbered after)

    # half-yearly PMs back from the last service
    last = today - timedelta(days=160 + ((n - ANCHOR) * 37 + 47) % 120)
    pms = []
    d = last
    while d > install + timedelta(days=90) and len(pms) < 6:
        pms.append(d)
        d -= timedelta(days=182)
    last_service = _at(pms[0], 8, 20) if pms else None
    for j, d in enumerate(reversed(pms)):
        hrs = Decimal(3 + (n + j) % 3)
        fin = _at(d, 8, 20)
        hist.append(
            common
            | {
                "siteid": origin,
                "location": f"{origin}-PROD",
                "description": f"Half-yearly preventive maintenance - {cls.label.lower()}",
                "worktype": "PM",
                "status": "CLOSE",
                "reportdate": _at(d - timedelta(days=14), 9),
                "targstartdate": _at(d, 6),
                "actstart": fin - timedelta(hours=float(hrs)),
                "actfinish": fin,
                "statusdate": fin + timedelta(days=2),
                "estlabhrs": hrs,
                "estlabcost": hrs * LABOR_RATE,
                "actlabhrs": hrs,
                "actlabcost": hrs * LABOR_RATE,
                "actmatcost": money(cls.pnew * 0.004),
                "supervisor": SUPERVISORS[(n + j + 1) % 4],
            }
        )

    # corrective work orders with failure reports
    failures = {"D": 3, "C": 2, "B": 1 if n % 2 == 0 else 0, "A": 0}.get(f.grade or "", n % 2)
    span = max(((pms[0] if pms else today) - install).days, 60)
    for k in range(failures):
        d = install + timedelta(days=span * (k + 1) // (failures + 1))
        triple = catalogue[(n - ANCHOR + k) % 3]
        hrs = Decimal(6 + (n - ANCHOR + k) % 5)
        start = _at(d, 11, 5)
        fin = start + timedelta(days=1, hours=2)
        wo = common | {
            "siteid": origin,
            "location": f"{origin}-PROD",
            "description": f"{triple[0][1]} - {cls.label.lower()} {f.asset_id}",
            "worktype": "CM",
            "status": "CLOSE",
            "reportdate": start - timedelta(hours=2),
            "actstart": start,
            "actfinish": fin,
            "statusdate": fin + timedelta(days=3),
            "failurecode": fclass,
            "problemcode": triple[0][0],
            "estlabhrs": hrs,
            "estlabcost": hrs * LABOR_RATE,
            "actlabhrs": hrs,
            "actlabcost": hrs * LABOR_RATE,
            "actmatcost": money(cls.pnew * (0.03 + 0.01 * (k % 3))),
            "supervisor": SUPERVISORS[(n - ANCHOR + k) % 4],
            "_failure": triple,
        }
        hist.append(wo)

    # the return inspection at the facility
    recv = f.received
    insp = common | {
        "siteid": fac,
        "location": f"{fac}-RTN",
        "description": f"Return inspection and grading - {f.product.lower()}",
        "worktype": "INSP",
        "reportdate": recv + timedelta(hours=2),
        "targstartdate": recv + timedelta(hours=20),
        "estlabhrs": Decimal(2),
        "estlabcost": 2 * LABOR_RATE,
        "supervisor": SUPERVISORS[n % 4],
        "externalrefid": f.id,
    }
    if f.condition == "Not inspected":
        insp |= {"status": "APPR", "statusdate": recv + timedelta(hours=3)}
    elif f.condition == "Test required":
        insp |= {"status": "INPRG", "actstart": recv + timedelta(hours=20), "statusdate": recv + timedelta(hours=20)}
    else:
        fin = min(recv + timedelta(hours=26), as_of - timedelta(hours=1))
        insp |= {
            "status": "COMP",
            "actstart": fin - timedelta(hours=2),
            "actfinish": fin,
            "statusdate": fin,
            "actlabhrs": Decimal(2),
            "actlabcost": 2 * LABOR_RATE,
            "actmatcost": Decimal("0.00"),
        }
    hist.append(insp)

    # the next periodic inspection
    nxt = _next_inspection(f.next_inspection)
    if nxt:
        hist.append(
            common
            | {
                "siteid": fac,
                "location": f"{fac}-RTN",
                "description": f"Periodic inspection and recertification - {cls.label.lower()}",
                "worktype": "INSP",
                "status": "WAPPR",
                "reportdate": as_of - timedelta(days=2),
                "statusdate": as_of - timedelta(days=2),
                "targstartdate": _at(nxt, 9),
                "targcompdate": _at(nxt, 17),
                "estlabhrs": Decimal(3),
                "estlabcost": 3 * LABOR_RATE,
            }
        )

    # executing cases: the refurbishment or teardown work order at the Repair centre
    for step in (case.state.exec or {}).get("steps", []):
        if step.get("k") not in ("repair", "teardown") or step.get("state") not in ("active", "done"):
            continue
        teardown = step["k"] == "teardown"
        approved = _iso(case.state.exec["approvedAt"])
        start = _iso(step.get("activeAt") or case.state.exec["approvedAt"])
        rec = case.results.recommendation
        route = f.routes[rec] if rec is not None else f.routes[0]
        prep = Decimal(str(abs(sum(term.amt for term in route.terms if term.kind == "prep")) or 400))
        hrs = (prep * Decimal("0.6") / LABOR_RATE).quantize(Decimal("0.1"))
        exec_ref = (step.get("ack") or {}).get("ref") or f"WO-{40000 + n * 7 + 13}"
        wo = common | {
            "siteid": "RC01",
            "location": "RC01-BAY1",
            "description": (
                f"Teardown, part testing and certification - {f.asset_id}"
                if teardown
                else f"Refurbish, test and certify - {f.asset_id}"
            ),
            "worktype": "TDOWN" if teardown else "REFURB",
            "reportdate": approved,
            "targstartdate": start,
            "targcompdate": start + timedelta(days=2),
            "actstart": start,
            "estlabhrs": hrs,
            "estlabcost": money(prep * Decimal("0.6")),
            "estmatcost": money(prep * Decimal("0.4")),
            "supervisor": SUPERVISORS[(n + 2) % 4],
            "externalrefid": exec_ref,
            "wopriority": 1,
        }
        if step["state"] == "done":
            fin = _iso(step["ack"]["at"])
            wo |= {
                "status": "COMP",
                "actstart": min(start, fin - timedelta(hours=4)),
                "actfinish": fin,
                "statusdate": fin,
                "actlabhrs": hrs,
                "actlabcost": money(prep * Decimal("0.6")),
                "actmatcost": money(prep * Decimal("0.4")),
            }
        else:
            wo |= {"status": "INPRG", "statusdate": start}
        hist.append(wo)

    total = Decimal("0.00")
    hist.sort(key=lambda r: (r["reportdate"], r["worktype"]))
    for seq, row in enumerate(hist, start=1):
        triple = row.pop("_failure", None)
        wo = b.wo(n, seq, **row)
        if triple:
            b.failure(wo, triple)
        total += (wo["actlabcost"] or 0) + (wo["actmatcost"] or 0)
    return money(total), last_service


def load(conn: Connection, seed: Seed) -> dict[str, int]:
    w = seed.world
    changed = w.as_of - timedelta(days=1)
    b = _Book()
    uid = 100000
    meter_id = spec_id = 0
    case_assets = set()
    for case in seed.cases.values():
        f = case.facts
        n = int(f.id.split("-")[1])
        cls = w.classes[f.cls]
        fac = site_code(f.location)
        total, last_service = _case_history(b, seed, case)
        steps = {s.get("k") for s in (case.state.exec or {}).get("steps", [])}
        if "release" in steps:
            status = "DECOMMISSIONED"
        elif f.grade == "D" or f.eng_life == "Below minimum":
            status = "BROKEN"
        elif f.grade == "C":
            status = "LIMITEDUSE"
        else:
            status = "NOT READY"
        uid += 1
        prio, crit = CRITICALITY[f.cls]
        spec_first = next(iter(f.spec.values()), "")
        b.rows["asset"].append(
            {
                "assetuid": uid,
                "assetnum": f.asset_id,
                "siteid": fac,
                "orgid": ORG,
                "location": f"{fac}-RTN",
                "description": f"{f.product} {f.mfr} {spec_first}".strip()[:100],
                "assettype": FAILURES[f.cls][0],
                "status": status,
                "statusdate": f.received,
                "priority": prio,
                "criticality": crit,
                "manufacturer": f.mfr,
                "serialnum": f"SN{(n * 7919 + 1234567) % 10_000_000:07d}",
                "installdate": f.received - timedelta(days=round(f.age * 365.25)),
                "purchaseprice": money(cls.pnew),
                "totalcost": total,
                "conditioncode": (f.grade + ("", "+", "-")[(n - ANCHOR + 1) % 3]) if f.grade else None,
                "lastservicedate": last_service,
                "isrunning": False,
                "pluscustomer": f.owner,
                "changedate": changed,
                "changeby": SYSTEM_USER,
            }
        )
        case_assets.add(f.asset_id)
        meter_id += 1
        b.rows["assetmeter"].append(
            {
                "assetmeterid": meter_id,
                "assetnum": f.asset_id,
                "siteid": fac,
                "metername": "RUNHOURS",
                "measureunitid": "HOURS",
                "lastreading": run_hours_reading(f),
                "lastreadingdate": f.received,
            }
        )
        for row in _spec_rows(f.spec):
            spec_id += 1
            b.rows["assetspec"].append({"assetspecid": spec_id, "assetnum": f.asset_id, "siteid": fac} | row)

    # installed base: the assets of the closed decisions (latest decision per asset)
    latest = {}
    for d in seed.decisions:
        if d.asset_id not in case_assets and (d.asset_id not in latest or d.date >= latest[d.asset_id].date):
            latest[d.asset_id] = d
    for asset_id, d in sorted(latest.items()):
        cls = w.classes[d.cls]
        site = site_code(d.site)
        operating = d.route in ("redeploy", "relase") and d.status != "cancelled"
        uid += 1
        prio, crit = CRITICALITY[d.cls]
        mfr = next((m for m in cls.mfr if d.equip.startswith(m.split()[0])), None)
        digits = int(re.sub(r"\D", "", asset_id) or 0)
        b.rows["asset"].append(
            {
                "assetuid": uid,
                "assetnum": asset_id,
                "siteid": site,
                "orgid": ORG,
                "location": f"{site}-PROD",
                "description": f"{cls.label} - {d.equip}"[:100],
                "assettype": FAILURES[d.cls][0],
                "status": "OPERATING" if operating else "DECOMMISSIONED",
                "statusdate": d.date,
                "priority": prio,
                "criticality": crit,
                "manufacturer": mfr,
                "serialnum": f"SN{(digits * 7919 + uid) % 10_000_000:07d}",
                "installdate": d.date if operating else None,
                "purchaseprice": money(cls.pnew),
                "totalcost": Decimal("0.00"),
                "conditioncode": d.grade,
                "lastservicedate": None,
                "isrunning": operating,
                "pluscustomer": d.tenant,
                "changedate": min(d.date, changed),
                "changeby": SYSTEM_USER,
            }
        )

    tables = (
        (t.ASSET, b.rows["asset"]),
        (t.ASSETMETER, b.rows["assetmeter"]),
        (t.ASSETSPEC, b.rows["assetspec"]),
        (t.WORKORDER, b.rows["workorder"]),
        (t.WOSTATUS, b.rows["wostatus"]),
        (t.FAILUREREPORT, b.rows["fr"]),
    )
    for table, rows in tables:
        if rows:
            conn.execute(insert(table), rows)
    return {table.name: len(rows) for table, rows in tables}


def create(conn: Connection) -> None:
    conn.execute(text("CREATE SCHEMA IF NOT EXISTS maximo"))
    t.metadata.create_all(conn)


def reset(conn: Connection, seed: Seed) -> dict[str, int]:
    t.metadata.drop_all(conn)
    create(conn)
    return load(conn, seed)


def ensure(conn: Connection, seed: Seed) -> None:
    create(conn)
    if conn.execute(text("SELECT count(*) FROM maximo.asset")).scalar_one() == 0:
        load(conn, seed)
