"""Load the seed (B2) into the ServiceNow FSM tables, as the instance would hold it at the demo's as-of time.

What FSM owns (the demo's SOURCES.fsm: "field service demand, technician dispatch, visit outcomes, parts consumed"):
- core_company:  the tenants (Customer A/B/C, customers), Northfield (us) and the manufacturers
- cmn_location:  customer sites Site 1..8 (name = site name, u_site_code = "Site 3") and our facilities
- sys_user:      field technicians (tech.0412 ...) and the integration user
- cmdb_model:    one per manufacturer and model (spec) of the seeded assets
- alm_asset:     every returned asset (asset_tag = asset id, e.g. MTR-2041; in stock or in maintenance at its
                 facility, company = owner tenant), plus the installed base at customer sites: units redeployed by the
                 closed decisions (motors, pumps, control units; In use)
- wm_order/wm_task/sm_part_requirement:
                 * service history of each returned asset at its former site (preventive and corrective visits, and the
                   removal visit before the return); MTR-2041's removal is WO0010382, closed 2026-09-30 14:05:11 by
                   tech.0412 after 2.5 h (the demo's MAPPINGS.fsm and source-field examples)
                 * service visits on the installed base (labour at the contracted ₹1,100/h; parts consumed)
                 * field service demand: one install order per case whose demand names a site, e.g. RT-1048 → Customer A
                   at Site 3 (Chennai Foundry), needed in 10 days, correlated with the OMS order SO-48102; confirmed
                   demand is Ready with a task Pending Dispatch, forecast demand is Draft
- sn_customerservice_case / u_upgrade_offer (plan 9 P9-4.1, own random sources, synthetic account codes only): 50
                 customer service cases (40 New, 10 Resolved; CS0010042 one CRH tool, CS0010050 a 22-line batch) and
                 2,400 upgrade offers over 24 months, acceptance logistic in the credit share
Everything is deterministic (fixed random seed, sys_id = md5 of table and natural key) and dated on or before the
as-of time, so a delta read `sys_updated_on>2026-10-07 09:00:00` returns only what changed through the API.
"""

import hashlib
import json
import math
import random
import re
from collections import Counter
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import insert, text
from sqlalchemy.engine import Connection

from sim.seed import Seed
from sim.vendors.servicenow.schema import SCHEMA, SPECS, SYS_FIELDS, TABLES, metadata

OWN_COMPANY = "Northfield Industrial Services"
LABOUR_RATE = Decimal("1100.00")  # INR per hour, the demo's contracted field labour rate
HERO_ORDER = "WO0010382"
HERO_CLOSED = datetime(2026, 9, 30, 14, 5, 11, tzinfo=UTC)
SERVICED_CLASSES = ("motor", "pump", "control")

SITE_PLACES = {
    "Site 1": ("Plot 14, MIDC Bhosari", "Pune", "Maharashtra"),
    "Site 2": ("SIPCOT Phase II", "Hosur", "Tamil Nadu"),
    "Site 3": ("Ambattur Industrial Estate", "Chennai", "Tamil Nadu"),
    "Site 4": ("MIDC Satpur", "Nashik", "Maharashtra"),
    "Site 5": ("Port Area, Gate 3", "Visakhapatnam", "Andhra Pradesh"),
    "Site 6": ("SIDCO Kurichi", "Coimbatore", "Tamil Nadu"),
    "Site 7": ("GIDC Sachin", "Surat", "Gujarat"),
    "Site 8": ("Sector F, Sanwer Road", "Indore", "Madhya Pradesh"),
}
FACILITY_PLACES = {
    "Warehouse 1": ("Sriperumbudur Logistics Park", "Chennai", "Tamil Nadu", "WH1"),
    "Warehouse 2": ("Chakan Phase II", "Pune", "Maharashtra", "WH2"),
    "Repair centre": ("Peenya Industrial Area", "Bengaluru", "Karnataka", "RC1"),
}
TECHNICIANS = [
    ("tech.0412", "Arun", "Prakash", "Site 3"),
    ("tech.0218", "Meena", "Iyer", "Site 2"),
    ("tech.0307", "Rahul", "Deshmukh", "Site 1"),
    ("tech.0521", "Sanjay", "Kulkarni", "Site 4"),
    ("tech.0634", "Lakshmi", "Narayanan", "Site 6"),
    ("tech.0145", "Vikram", "Reddy", "Site 5"),
    ("tech.0789", "Priya", "Shah", "Site 7"),
    ("tech.0856", "Imran", "Khan", "Site 8"),
    ("tech.0463", "Karthik", "Subramanian", "Site 3"),
    ("tech.0392", "Neha", "Joshi", "Site 1"),
    ("tech.0927", "Suresh", "Babu", "Site 6"),
    ("tech.0711", "Deepa", "Menon", "Site 2"),
]
PARTS = {
    "motor": [
        ("6312-2Z-C3", "Deep groove ball bearing 6312-2Z/C3", 4200),
        ("VR-60", "V-ring shaft seal 60 mm", 650),
        ("FAN-250M", "Cooling fan, 250M frame", 3800),
        ("TB-6P", "Terminal board, 6-pole", 1900),
    ],
    "pump": [
        ("MS-45", "Mechanical seal 45 mm", 7600),
        ("GS-HG2", "Gear set, HG series", 18500),
        ("ORK-12", "O-ring kit", 900),
        ("6208-2RS", "Bearing 6208-2RS", 1400),
    ],
    "control": [
        ("PSU-24V10", "24 V DC power supply, 10 A", 5200),
        ("IO-16DI", "Digital input module, 16 ch", 11800),
        ("FAN-80", "Cabinet fan 80 mm", 750),
        ("CAP-KIT", "DC bus capacitor kit", 2300),
    ],
}


def sys_id(table: str, key: str) -> str:
    return hashlib.md5(f"servicenow:{table}:{key}".encode()).hexdigest()


class _Rows:
    def __init__(self):
        self.rows: dict[str, list[dict]] = {name: [] for name in SPECS}

    def add(self, table: str, key: str, created: datetime, updated: datetime | None = None, by: str = "system", **fields):
        spec = SPECS[table]
        row = {f.name: None for f in SYS_FIELDS + spec.fields}
        row.update(
            sys_id=sys_id(table, key),
            sys_created_on=created,
            sys_created_by=by,
            sys_updated_on=updated or created,
            sys_updated_by=by,
            sys_mod_count=0 if not updated or updated == created else 2,
        )
        unknown = set(fields) - set(row)
        if unknown:
            raise KeyError(f"{table}: unknown fields {unknown}")
        row.update(fields)
        self.rows[table].append(row)
        return row["sys_id"]


def _serial(asset_id: str) -> str:
    if asset_id == "MTR-2041":
        return "SN-77120-A"  # the demo's MAPPINGS.fsm example
    h = int(hashlib.md5(asset_id.encode()).hexdigest(), 16)
    return f"SN-{10000 + h % 89999}-{'ABCDEFGH'[h % 8]}"


def _spec_summary(spec: dict) -> str:
    for k in ("Rated power", "Flow", "Family", "Type", "Device", "Tool type"):
        if k in spec:
            return str(spec[k])
    return ""


def load(conn: Connection, seed: Seed) -> dict[str, int]:
    w = seed.world
    as_of = w.as_of
    rng = random.Random(20261007)
    R = _Rows()
    base = as_of - timedelta(days=400)

    # ---------------- companies
    company: dict[str, str] = {}
    company[OWN_COMPANY] = R.add(
        "core_company",
        OWN_COMPANY,
        base,
        name=OWN_COMPANY,
        customer=False,
        vendor=False,
        manufacturer=False,
        city="Bengaluru",
        country="India",
    )
    for t in w.tenants:
        company[t] = R.add(
            "core_company", t, base, name=t, customer=True, vendor=False, manufacturer=False, city="", country="India"
        )
    for m in sorted({m for c in w.classes.values() for m in c.mfr}):
        company[m] = R.add("core_company", m, base, name=m, customer=False, vendor=True, manufacturer=True, city="", country="")

    # ---------------- locations: a site belongs to the tenant that uses it most
    site_tenant: dict[str, Counter] = {s.id: Counter() for s in w.sites}
    for d in seed.decisions:
        if d.site in site_tenant:
            site_tenant[d.site][d.tenant] += 1
    for c in seed.cases.values():
        if c.facts.demand.site in site_tenant:
            site_tenant[c.facts.demand.site][c.facts.owner] += 5
    location: dict[str, str] = {}
    tenant_of_site: dict[str, str] = {}
    for s in w.sites:
        street, city, state = SITE_PLACES.get(s.id, ("", s.name.split()[0], ""))
        tenant = min(site_tenant[s.id].items(), key=lambda kv: (-kv[1], kv[0]))[0] if site_tenant[s.id] else w.tenants[0]
        tenant_of_site[s.id] = tenant
        location[s.id] = R.add(
            "cmn_location",
            s.id,
            base,
            name=s.name,
            full_name=f"India/{state}/{city}/{s.name}",
            street=street,
            city=city,
            state=state,
            country="India",
            company=company[tenant],
            u_site_code=s.id,
        )
    for f in w.facilities:
        street, city, state, code = FACILITY_PLACES.get(f, ("", "", "", f))
        location[f] = R.add(
            "cmn_location",
            f,
            base,
            name=f,
            full_name=f"India/{state}/{city}/{f}",
            street=street,
            city=city,
            state=state,
            country="India",
            company=company[OWN_COMPANY],
            u_site_code=code,
        )

    # ---------------- users
    user: dict[str, str] = {}
    techs_at: dict[str, list[str]] = {}
    for un, first, last, home in TECHNICIANS:
        user[un] = R.add(
            "sys_user",
            un,
            base,
            user_name=un,
            name=f"{first} {last}",
            first_name=first,
            last_name=last,
            email=f"{first.lower()}.{last.lower()}@northfield.example",
            title="Field Service Technician",
            location=location[home],
            company=company[OWN_COMPANY],
            active=True,
        )
        techs_at.setdefault(home, []).append(un)
    all_techs = [t[0] for t in TECHNICIANS]
    for un, name, title in (
        ("di.integration", "DI Integration", "Integration user"),
        ("fsm.dispatcher", "FSM Dispatcher", "Dispatcher"),
    ):
        user[un] = R.add(
            "sys_user",
            un,
            base,
            user_name=un,
            name=name,
            first_name=name.split()[0],
            last_name=name.split()[1],
            email=f"{un}@northfield.example",
            title=title,
            location=None,
            company=company[OWN_COMPANY],
            active=True,
        )

    def tech_for(site: str) -> str:
        return rng.choice(techs_at.get(site) or all_techs)

    # ---------------- models
    model: dict[tuple, str] = {}

    def model_of(cls: str, mfr: str, name: str) -> str:
        key = (mfr, name)
        if key not in model:
            pre = w.classes[cls].pre
            num = f"{pre}-{int(hashlib.md5(f'{mfr}{name}'.encode()).hexdigest(), 16) % 9000 + 1000}"
            model[key] = R.add(
                "cmdb_model",
                f"{mfr}|{name}",
                base,
                display_name=f"{mfr} {name}",
                name=name,
                manufacturer=company.get(mfr),
                model_number=num,
                short_description=w.classes[cls].label,
            )
        return model[key]

    # ---------------- assets: returned (the cases) and installed (redeployed by closed decisions)
    asset: dict[str, str] = {}
    case_models: dict[str, str] = {}
    for c in seed.cases.values():
        f = c.facts
        name = f"{f.product} {_spec_summary(f.spec)}".strip()
        mid = model_of(f.cls, f.mfr, name)
        case_models[f.id] = mid
        installed = f.received - timedelta(days=round(f.age * 365.25))
        if f.location == "Repair centre":
            status, sub = 3, ""
        elif f.kind == "exit":
            status, sub = 6, "pending_disposal"
        else:
            status, sub = 6, "available" if f.readiness == "ready" else "pending_repair"
        asset[f.asset_id] = R.add(
            "alm_asset",
            f.asset_id,
            installed,
            f.received,
            by="di.integration",
            display_name=f"{f.asset_id} - {f.mfr} {name}",
            asset_tag=f.asset_id,
            serial_number=_serial(f.asset_id),
            model=mid,
            model_category=f.product,
            install_status=status,
            substatus=sub,
            location=location.get(f.location),
            company=company.get(f.owner),
            install_date=installed,
            warranty_expiration=installed + timedelta(days=730),
            quantity=f.qty,
            comments=f"Returned {f.received:%Y-%m-%d} ({f.id}); condition: {f.condition}",
        )
    installed_base: list[tuple] = []  # (asset id, cls, site, tenant, installed at)
    for d in seed.decisions:
        if d.route != "redeploy" or d.status != "reconciled" or d.cls not in SERVICED_CLASSES or d.asset_id in asset:
            continue
        if d.site not in location:
            continue
        mfr = next((m for m in w.classes[d.cls].mfr if d.equip.startswith(m)), w.classes[d.cls].mfr[0])
        name = d.equip[len(mfr) :].strip() if d.equip.startswith(mfr) else d.equip
        mid = model_of(d.cls, mfr, name)
        at = d.date + timedelta(days=d.days or 14)
        if at >= as_of:
            continue
        asset[d.asset_id] = R.add(
            "alm_asset",
            d.asset_id,
            at,
            by="di.integration",
            display_name=f"{d.asset_id} - {mfr} {name}",
            asset_tag=d.asset_id,
            serial_number=_serial(d.asset_id),
            model=mid,
            model_category=w.classes[d.cls].label,
            install_status=1,
            substatus="",
            location=location[d.site],
            company=company.get(d.tenant),
            install_date=at,
            warranty_expiration=at + timedelta(days=365),
            quantity=d.q,
            comments=f"Redeployed under {d.id}",
        )
        installed_base.append((d.asset_id, d.cls, d.site, d.tenant, at))

    # ---------------- work orders, tasks and parts
    orders: list[dict] = []  # collected first, numbered by opened_at

    def visit(asset_id, cls, site, tenant, closed, kind, special=None):
        hours = special["hours"] if special else rng.choice([1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.5])
        tech = special["tech"] if special else tech_for(site)
        start = closed - timedelta(hours=hours)
        opened = (start - timedelta(days=rng.randint(1, 6), hours=rng.randint(0, 8))).replace(microsecond=0)
        open_now = closed > as_of - timedelta(hours=2)
        state = 3 if not open_now else rng.choice([16, 2])
        if state == 3 and kind == "Corrective" and rng.random() < 0.05:
            state = 4
        product = w.classes[cls].label.lower()
        short = {
            "Preventive": f"Preventive maintenance - {product}",
            "Corrective": f"Corrective repair - {product} fault",
            "Decommission": f"Remove {product} for return",
        }[kind]
        parts = []
        if kind == "Corrective" or (kind == "Preventive" and rng.random() < 0.5):
            for pn, desc, cost in rng.sample(PARTS[cls], 2 if kind == "Corrective" and rng.random() < 0.4 else 1):
                q = 1 if cost > 3000 else rng.randint(1, 4)
                parts.append((pn, desc, cost, q))
        task = {
            "short": short if kind != "Decommission" else f"Disconnect, remove and pack {product}",
            "state": {3: 3, 4: 4, 16: 16, 2: 2}[state],
            "tech": tech,
            "expected_start": start,
            "start": start if state in (2, 3, 4) else None,
            "end": closed if state in (3, 4) else None,
            "duration": int(hours * 3600) if state in (3, 4) else None,
            "closed": closed if state in (3, 4) else None,
            "close_code": {3: "Completed", 4: "Parts unavailable"}.get(state),
            "notes": {
                3: f"{kind} work completed on {asset_id}; unit tested and handed over",
                4: f"Fault confirmed on {asset_id}; follow-up visit needed",
            }.get(state, ""),
            "parts": parts,
            "consumed": state in (3, 4),
        }
        orders.append(
            {
                "key": f"svc:{asset_id}:{closed:%Y%m%d%H%M}",
                "special": special,
                "opened": opened,
                "updated": closed if state in (3, 4) else min(opened + timedelta(days=1), as_of - timedelta(hours=1)),
                "state": state,
                "priority": 2 if kind == "Corrective" else 4 if kind == "Preventive" else 3,
                "company": tenant,
                "site": site,
                "asset": asset_id,
                "short": short,
                "description": f"{short} at {site}. Asset {asset_id}, serial {_serial(asset_id)}.",
                "work_type": kind,
                "expected_start": start,
                "closed": closed if state in (3, 4) else None,
                "close_notes": task["notes"],
                "correlation": None,
                "model": None,
                "qty": 1,
                "tasks": [task],
            }
        )

    sites = [s.id for s in w.sites]
    for c in seed.cases.values():
        f = c.facts
        if f.cls not in SERVICED_CLASSES:
            continue
        former = rng.choice([s for s in sites if s != f.demand.site])
        installed = f.received - timedelta(days=round(f.age * 365.25))
        removal = (
            HERO_CLOSED
            if f.asset_id == "MTR-2041"
            else (f.received - timedelta(days=rng.randint(2, 6), hours=rng.randint(9, 17))).replace(
                minute=rng.randint(0, 59), second=rng.randint(0, 59)
            )
        )
        earliest = max(installed, removal - timedelta(days=720))
        for _ in range(rng.randint(1, 2)):
            when = earliest + (removal - earliest) * rng.uniform(0.1, 0.9)
            when = when.replace(hour=rng.randint(9, 17), minute=rng.randint(0, 59), second=rng.randint(0, 59), microsecond=0)
            visit(f.asset_id, f.cls, former, f.owner, when, rng.choice(["Preventive", "Corrective"]))
        special = {"hours": 2.5, "tech": "tech.0412"} if f.asset_id == "MTR-2041" else None
        visit(f.asset_id, f.cls, former, f.owner, removal, "Decommission", special)
    for asset_id, cls, site, tenant, at in installed_base:
        for _ in range(rng.choice([0, 1, 1, 2])):
            when = at + (as_of - at) * rng.uniform(0.2, 1.0)
            when = when.replace(hour=rng.randint(9, 17), minute=rng.randint(0, 59), second=rng.randint(0, 59), microsecond=0)
            if when > as_of:
                when = as_of - timedelta(hours=1)
            visit(asset_id, cls, site, tenant, when, rng.choice(["Preventive", "Corrective", "Corrective"]))

    # field service demand: a unit needed at a customer site
    for c in seed.cases.values():
        f = c.facts
        if not f.demand.site or f.demand.site not in location:
            continue
        text_facts = " ".join(f.facts)
        m = re.search(rf"{re.escape(f.demand.site)} in (\d+) days", text_facts)
        days = int(m.group(1)) if m else rng.randint(7, 45)
        so = re.search(r"\bSO-\d+\b", text_facts)
        opened = (as_of - timedelta(days=rng.randint(1, 9), hours=rng.randint(1, 8))).replace(second=0, microsecond=0)
        due = (as_of + timedelta(days=days)).replace(hour=9, minute=0, second=0)
        label = next((r.demand_label for r in f.routes if r.id == "redeploy" and r.demand_label), None)
        product = f.product.lower()
        summary = _spec_summary(f.spec)
        install = f.cls in SERVICED_CLASSES
        verb = "Install replacement" if install else "Deliver replacement"
        short = f"{verb} {product} ({summary})" if summary else f"{verb} {product}"
        confirmed = f.demand.confirmed
        orders.append(
            {
                "key": f"demand:{f.id}",
                "special": None,
                "opened": opened,
                "updated": opened + timedelta(hours=2),
                "state": 10 if confirmed else 1,
                "priority": 2 if confirmed else 3,
                "company": f.owner,
                "site": f.demand.site,
                "asset": None,
                "short": short,
                "description": (label or f"{f.owner} needs a {product} at {f.demand.site}")
                + f". Quantity {f.qty}; needed by {due:%Y-%m-%d}.",
                "work_type": "Install" if install else "Delivery",
                "expected_start": due,
                "closed": None,
                "close_notes": "",
                "correlation": so.group(0) if so else None,
                "model": case_models[f.id],
                "qty": f.qty,
                "tasks": [
                    {
                        "short": f"Install and commission {product}" if install else f"Deliver and hand over {product}",
                        "state": 10 if confirmed else 1,
                        "tech": None,
                        "expected_start": due,
                        "start": None,
                        "end": None,
                        "duration": None,
                        "closed": None,
                        "close_code": None,
                        "notes": "",
                        "parts": [],
                        "consumed": False,
                    }
                ],
            }
        )

    orders.sort(key=lambda o: (o["opened"], o["key"]))
    n = 10001
    task_n, part_n = 10001, 10001
    for o in orders:
        if o["special"]:
            number = HERO_ORDER
        else:
            if f"WO{n:07d}" == HERO_ORDER:
                n += 1
            number, n = f"WO{n:07d}", n + 1
        oid = R.add(
            "wm_order",
            number,
            o["opened"],
            o["updated"],
            by="fsm.dispatcher",
            number=number,
            short_description=o["short"],
            description=o["description"],
            state=o["state"],
            priority=o["priority"],
            company=company.get(o["company"]),
            location=location[o["site"]],
            asset=asset.get(o["asset"]) if o["asset"] else None,
            caller=user["fsm.dispatcher"],
            opened_at=o["opened"],
            expected_start=o["expected_start"],
            closed_at=o["closed"],
            close_notes=o["close_notes"],
            correlation_id=o["correlation"],
            u_work_type=o["work_type"],
            u_model_required=o["model"],
            u_quantity=o["qty"],
        )
        for t in o["tasks"]:
            tnum, task_n = f"WOT{task_n:07d}", task_n + 1
            updated = t["closed"] or o["updated"]
            tid = R.add(
                "wm_task",
                tnum,
                o["opened"],
                updated,
                by=t["tech"] or "fsm.dispatcher",
                number=tnum,
                parent=oid,
                short_description=t["short"],
                state=t["state"],
                priority=o["priority"],
                assigned_to=user[t["tech"]] if t["tech"] and t["state"] != 10 else None,
                company=company.get(o["company"]),
                location=location[o["site"]],
                asset=asset.get(o["asset"]) if o["asset"] else None,
                expected_start=t["expected_start"],
                actual_work_start=t["start"],
                actual_work_end=t["end"],
                work_duration=t["duration"],
                closed_at=t["closed"],
                close_code=t["close_code"],
                close_notes=t["notes"],
                u_labour_rate=LABOUR_RATE,
            )
            for pn, desc, cost, q in t["parts"]:
                pnum, part_n = f"PRQ{part_n:07d}", part_n + 1
                R.add(
                    "sm_part_requirement",
                    pnum,
                    o["opened"],
                    updated,
                    by=t["tech"] or "fsm.dispatcher",
                    number=pnum,
                    task=tid,
                    part_number=pn,
                    short_description=desc,
                    required_quantity=q,
                    consumed_quantity=q if t["consumed"] else 0,
                    unit_cost=Decimal(cost),
                    state="consumed" if t["consumed"] else "requested",
                )

    order = ["core_company", "cmn_location", "sys_user", "cmdb_model", "alm_asset", "wm_order", "wm_task", "sm_part_requirement"]
    for name in order:
        if R.rows[name]:
            conn.execute(insert(TABLES[name]), R.rows[name])
    return {name: len(R.rows[name]) for name in order} | load_service_desk(conn, as_of)


# ---------------------------------------------------------------- the service desk (plan 9, P9-4.1)
# Synthetic: account codes only, no names. Own random source, so the FSM tables above are not touched.
MARKETS = ("DE", "UK", "US", "AU", "FR")
MARKET_WEIGHT = (22, 14, 40, 10, 14)
CURRENCY = {"DE": "EUR", "FR": "EUR", "UK": "GBP", "US": "USD", "AU": "AUD"}
FX = {"USD": 1.0, "EUR": 0.92, "GBP": 0.79, "AUD": 1.52}  # units per USD, as the app's fx_rate
NEW_PRICE = {"CMH": 1450, "BRK": 1900, "DCD": 3200, "CRH": 620, "AGR": 260, "LSR": 1100}
FAULT_TEXT = {
    "MOT": "Motor stalls under load",
    "GBX": "Grinding noise from the gearbox",
    "ELE": "Electronics fault, no power",
    "WEA": "Worn parts, loose fit",
}
OFFER_COUNT = 2400
OFFER_FIRST_DAY = 730  # offers span 24 months back from the as-of date
TAKE_UP_INTERCEPT, TAKE_UP_SLOPE, TAKE_UP_NOISE = -3.2, 9.0, 0.25  # logit of acceptance on credit share, plus noise
SAMPLE_ACCOUNT = "ACC-US-0042"  # 14 offers, 4 accepted
NOMINAL_LIFE_MONTHS = 60  # "past 50% of life" is older than 30 months here; the life model of phase 3 decides later


def _line(serial: str, cls: str, age: int, fault: str, cover: str, until: str) -> dict:
    return {
        "serial": serial,
        "model_class": cls,
        "age_months": age,
        "fault_code": fault,
        "fault_text": FAULT_TEXT.get(fault, ""),
        "cover_type": cover,
        "cover_until": until,
    }


def _tickets(R: _Rows, as_of: datetime) -> None:
    rng = random.Random(20261107)
    classes = list(NEW_PRICE)
    faults = list(FAULT_TEXT)
    for n in range(1, 51):
        number = f"CS{10000 + n:07d}"
        opened = (as_of - timedelta(days=rng.randint(1, 20), hours=rng.randint(0, 9))).replace(minute=0, second=0, microsecond=0)
        market = rng.choices(MARKETS, MARKET_WEIGHT)[0]
        account = f"ACC-{market}-{rng.randint(1, 80):04d}"
        site, batch, role, loaner = f"Site {rng.randint(1, 40)}", "", "Site manager", n % 7 == 0
        cls, age, fault = rng.choice(classes), rng.randint(3, 60), rng.choice(faults + [""])
        cover = rng.choice(["fleet", "warranty", "none", "none"])
        until = {"none": "2025-12-31"}.get(cover, "2027-06-30")
        lines = [_line(f"{cls}-{46000 + n}", cls, age, fault, cover, until)]
        if n == 42:  # the sample ticket: a US CRH motor fault at 18 months under fleet cover
            account, market, site, loaner = SAMPLE_ACCOUNT, "US", "Austin", False
            lines = [_line("CRH-46042", "CRH", 18, "MOT", "fleet", "2027-06-30")]
        if n == 50:  # the sample batch: 22 lines, 9 past 50% of life without cover, 11 under it, 2 covered CRH
            account, market, site, batch, role, loaner = "ACC-US-0057", "US", "Denver", "BATCH-0050", "Fleet desk", False
            lines = []
            for i in range(22):
                serial = f"{classes[i % 6]}-{45000 + i}"
                if i < 9:
                    lines.append(_line(serial, classes[i % 6], 36 + 2 * i, faults[i % 4], "none", "2025-12-31"))
                elif i < 20:
                    fault = "" if i in (9, 14, 19) else faults[i % 4]  # three faults are unclear
                    lines.append(_line(serial, classes[i % 6], 6 + 2 * (i - 9), fault, "none", "2025-12-31"))
                else:
                    lines.append(_line(f"CRH-{45000 + i}", "CRH", 14 + 6 * (i - 20), "MOT", "fleet", "2027-06-30"))
        R.add(
            "sn_customerservice_case",
            number,
            opened,
            opened + timedelta(hours=1),
            by="csm.intake",
            number=number,
            account=account,
            u_market=market,
            u_site=site,
            u_batch_id=batch,
            u_lines=json.dumps(lines),
            u_requester_role=role,
            u_loaner_promised=loaner,
            state=6 if 31 <= n <= 40 else 1,  # ten resolved, forty open
            opened_at=opened,
        )


def _offers(R: _Rows, as_of: datetime) -> None:
    """2,400 offers over 24 months. Acceptance is logistic in the credit share, intercept -3.2 and slope 9.0, plus a
    little noise on the logit from the seeded source; the sample account has 14 offers and 4 accepted."""
    rng = random.Random(20261108)
    classes = list(NEW_PRICE)
    for i in range(OFFER_COUNT):
        if i < 14:
            account, market = SAMPLE_ACCOUNT, "US"
        else:
            market = rng.choices(MARKETS, MARKET_WEIGHT)[0]
            account = f"ACC-{market}-{rng.randint(1, 80):04d}"
            if account == SAMPLE_ACCOUNT:
                account = "ACC-US-0043"
        pct = rng.randint(2, 40) / 100
        cls = rng.choice(classes)
        when = (as_of - timedelta(days=rng.randint(0, OFFER_FIRST_DAY), minutes=rng.randint(0, 600))).replace(microsecond=0)
        logit = TAKE_UP_INTERCEPT + TAKE_UP_SLOPE * pct + rng.gauss(0, TAKE_UP_NOISE)
        accepted = rng.random() < 1 / (1 + math.exp(-logit))
        if account == SAMPLE_ACCOUNT:
            accepted = i < 4
        cur = CURRENCY[market]
        R.add(
            "u_upgrade_offer",
            f"offer:{i}",
            when,
            by="csm.sales",
            account=account,
            u_market=market,
            u_model_class=cls,
            u_offered_at=when,
            u_credit_pct=Decimal(f"{pct:.2f}"),
            u_credit_amount=Decimal(f"{NEW_PRICE[cls] * pct * FX[cur]:.2f}"),
            u_currency=cur,
            u_accepted=accepted,
        )


def load_service_desk(conn: Connection, as_of: datetime) -> dict[str, int]:
    """Seed the service desk tables (tickets and offers); the FSM tables are loaded by `load`."""
    R = _Rows()
    _tickets(R, as_of)
    _offers(R, as_of)
    out = {}
    for name in ("sn_customerservice_case", "u_upgrade_offer"):
        conn.execute(insert(TABLES[name]), R.rows[name])
        out[name] = len(R.rows[name])
    return out


def create(conn: Connection) -> None:
    conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{SCHEMA}"'))
    metadata.create_all(conn)


def reset(conn: Connection, seed: Seed) -> dict[str, int]:
    """Drop and recreate every ServiceNow table, then load the seed."""
    metadata.drop_all(conn)
    create(conn)
    return load(conn, seed)


def ensure(conn: Connection, seed: Seed) -> None:
    """Create the tables and load the seed once (on first start)."""
    create(conn)
    if conn.execute(text(f'SELECT count(*) FROM "{SCHEMA}".wm_order')).scalar_one() == 0:  # noqa: S608 - SCHEMA is a module constant
        load(conn, seed)
    elif conn.execute(text(f'SELECT count(*) FROM "{SCHEMA}".u_upgrade_offer')).scalar_one() == 0:  # noqa: S608 - SCHEMA is a module constant
        load_service_desk(conn, seed.world.as_of)  # a database from before plan 9 gains the service desk
