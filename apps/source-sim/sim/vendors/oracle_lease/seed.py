"""Load the seed (B2) into the Oracle Lease and Finance Management mock (schema oracle_lease), as at the demo's as-of.

Same values as the retired generic mock (field names as the demo's MAPPINGS.lease: LEASE_CONTRACT_ID,
CONTRACT_END_DATE, LESSEE_NAME, MONTHLY_RENTAL):
- one lease contract per returned asset, lessee = the owner tenant. Contract numbers run with the case number, so
  RT-1048 (MTR-2041) is LC-004417, ending 2026-12-31, MONTHLY_RENTAL 2400.00 USD (value new x size x quantity x 0.2034,
  rounded to 10). Booked contracts have CONTRACT_STATUS BOOKED (OKL's status of a live contract).
- one lease asset (contract asset line, KLE_ID) per contract; returned assets are RETURNED with an asset return
  record (ARS_CODE RETURNED) on the day the depot received them
- MTR-2077 (the demo's ownership conflict CF-31: the lease system says Customer A) is still on lease, on its own
  contract LC-005077
- one renewal (re-lease opportunity) per asset with a lease opportunity in the demo (RT-1048: LS-5530, forecast)
"""

import calendar
import re
from datetime import date, datetime, time, timedelta

from sqlalchemy import insert, text
from sqlalchemy.engine import Connection

from sim.seed import Seed
from sim.seed.model import CaseFacts
from sim.vendors.depot_repair.isg import IST
from sim.vendors.oracle_lease import tables as t
from sim.vendors.otm.demo import hash_id, jround

RATE = 0.2034
TERMS = (24, 36, 48, 60)
FIXED_END = {"LC-004417": date(2026, 12, 31)}  # the demo's MAPPINGS.lease example
EXTRA = {
    "asset": "MTR-2077",
    "cls": "motor",
    "owner": "Customer A",
    "contract": "LC-005077",
    "end": date(2027, 3, 31),
    "term": 36,
}


def tenant_key(name: str) -> str:
    return re.sub(r"\W+", "_", name.strip()).upper()


def contract_id(f: CaseFacts) -> str:
    return f"LC-{4369 + int(f.id.split('-')[1]) - 1000:06d}"


def _size(f: CaseFacts) -> float:
    if f.cls != "motor":
        return 1.0
    kw = float(re.search(r"[\d.]+", f.spec.get("Rated power", "22")).group(0))
    return min(1.4, max(0.25, kw / 55))


def _month_end(y: int, m: int) -> date:
    y, m = y + (m - 1) // 12, (m - 1) % 12 + 1
    return date(y, m, calendar.monthrange(y, m)[1])


def _start(end: date, term: int) -> date:
    idx = end.year * 12 + end.month - term  # the month after (end - term), zero-based
    return date(idx // 12, idx % 12 + 1, 1)


def day_end(d: date) -> datetime:
    """The end of a contract day in EBS time: the contract runs through its end date."""
    return datetime.combine(d + timedelta(days=1), time(0, 0), tzinfo=IST)


def contract_doc(
    cid: str, kle: int, asset: str, qty: int, owner: str, start: date, end: date, term: int, rental: float, renew: str
):
    return {
        "LEASE_CONTRACT_ID": cid,
        "CONTRACT_NUMBER": cid,
        "CHR_ID": 100000 + int(cid[3:]),
        "CONTRACT_STATUS": "BOOKED",
        "DEAL_TYPE": "LEASEOP",
        "LESSEE_NAME": tenant_key(owner),
        "LESSEE_DISPLAY_NAME": owner,
        "CONTRACT_START_DATE": start.isoformat(),
        "CONTRACT_END_DATE": end.isoformat(),
        "TERM_MONTHS": term,
        "MONTHLY_RENTAL": float(rental),
        "CURRENCY_CODE": "USD",
        "BILLING_FREQUENCY": "MONTHLY",
        "RENEWAL_OPTION": renew,
        "ASSET_NUMBER": asset,
        "KLE_ID": kle,
        "ASSET_COUNT": qty,
        "DATE_TERMINATED": None,
    }


def load(conn: Connection, seed: Seed) -> dict[str, int]:
    as_of = seed.world.as_of
    stamp = as_of - timedelta(hours=1)
    contracts, assets, renewals, returns = [], [], [], []
    for n, case in enumerate(seed.cases.values()):
        f = case.facts
        cls = seed.world.classes[f.cls]
        cid = contract_id(f)
        h = hash_id(cid)
        h = int(h, 16) if isinstance(h, str) else h
        term = TERMS[h % len(TERMS)]
        end = FIXED_END.get(cid) or _month_end(as_of.year, as_of.month + 1 + (h >> 4) % 9)
        rental = jround(cls.pnew * _size(f) * f.qty * RATE / 10) * 10
        kle = 500000 + n
        doc = contract_doc(
            cid,
            kle,
            f.asset_id,
            f.qty,
            f.owner,
            _start(end, term),
            end,
            term,
            rental,
            "RENEW_OR_RETURN" if f.demand.lease else "RETURN",
        )
        contracts.append(doc)
        returned = f.received.date()
        assets.append(
            {
                "ASSET_NUMBER": f.asset_id,
                "KLE_ID": kle,
                "ASSET_DESCRIPTION": f"{f.product} · {f.mfr}",
                "ASSET_CATEGORY": cls.label.upper().replace(" ", "_"),
                "MANUFACTURER": f.mfr,
                "QUANTITY": f.qty,
                "OWNER_NAME": tenant_key(f.owner),
                "OWNERSHIP_TYPE": "CUSTOMER_OWNED",
                "LEASE_CONTRACT_ID": cid,
                "LESSEE_NAME": tenant_key(f.owner),
                "LEASE_STATUS": "RETURNED",
                "RETURN_DATE": returned.isoformat(),
                "ORIGINAL_COST": round(cls.pnew * _size(f) * f.qty, 2),
                "CURRENCY_CODE": "USD",
                "AGE_YEARS": f.age,
            }
        )
        returns.append(
            {
                "KLE_ID": kle,
                "ASSET_NUMBER": f.asset_id,
                "CONTRACT_NUMBER": cid,
                "ARS_CODE": "RETURNED",
                "ART1_CODE": "EARLY_TERMINATION" if returned < end else "TERM_EXPIRATION",
                "DATE_RETURNED": returned.isoformat(),
                "COMMENTS": "Received at the repair depot",
            }
        )
        if f.demand.lease:
            rl = next((r for r in f.routes if r.id == "relase"), None)
            income = next((x for x in rl.terms if x.kind == "lease"), None) if rl else None
            months = int(m.group(1)) if income and (m := re.search(r"(\d+) months", income.label)) else 30
            renewals.append(
                {
                    "RENEWAL_ID": f"RN-{f.asset_id}",
                    "LEASE_OPPORTUNITY_ID": f.demand.lease,
                    "LEASE_CONTRACT_ID": cid,
                    "ASSET_NUMBER": f.asset_id,
                    "RENEWAL_TYPE": "RE_LEASE",
                    "STATUS": "CONFIRMED" if rl and rl.demand_status == "confirmed" else "FORECAST",
                    "PROPOSED_TERM_MONTHS": months,
                    "PROPOSED_MONTHLY_RENTAL": round(income.amt / months, 2) if income else None,
                    "CURRENCY_CODE": "USD",
                    "SITE": f.demand.site,
                    "OPTION_EXPIRY_DATE": end.isoformat(),
                }
            )
    cls = seed.world.classes[EXTRA["cls"]]
    kle = 500000 + len(contracts)
    contracts.append(
        contract_doc(
            EXTRA["contract"],
            kle,
            EXTRA["asset"],
            1,
            EXTRA["owner"],
            _start(EXTRA["end"], EXTRA["term"]),
            EXTRA["end"],
            EXTRA["term"],
            jround(cls.pnew * RATE / 10) * 10,
            "RETURN",
        )
    )
    assets.append(
        {
            "ASSET_NUMBER": EXTRA["asset"],
            "KLE_ID": kle,
            "ASSET_DESCRIPTION": cls.label,
            "ASSET_CATEGORY": cls.label.upper().replace(" ", "_"),
            "MANUFACTURER": cls.mfr[0],
            "QUANTITY": 1,
            "OWNER_NAME": tenant_key(EXTRA["owner"]),
            "OWNERSHIP_TYPE": "CUSTOMER_OWNED",
            "LEASE_CONTRACT_ID": EXTRA["contract"],
            "LESSEE_NAME": tenant_key(EXTRA["owner"]),
            "LEASE_STATUS": "ON_LEASE",
            "RETURN_DATE": None,
            "ORIGINAL_COST": cls.pnew,
            "CURRENCY_CODE": "USD",
            "AGE_YEARS": None,
        }
    )
    conn.execute(
        insert(t.CONTRACTS), [{"contract_number": c["CONTRACT_NUMBER"], "doc": c, "last_update_date": stamp} for c in contracts]
    )
    conn.execute(insert(t.ASSETS), [{"asset_number": a["ASSET_NUMBER"], "doc": a, "last_update_date": stamp} for a in assets])
    conn.execute(insert(t.RENEWALS), [{"renewal_id": r["RENEWAL_ID"], "doc": r, "last_update_date": stamp} for r in renewals])
    conn.execute(insert(t.ASSET_RETURNS), [{"kle_id": r["KLE_ID"], "doc": r, "last_update_date": stamp} for r in returns])
    return {"contracts": len(contracts), "assets": len(assets), "renewals": len(renewals), "asset_returns": len(returns)}


def create(conn: Connection) -> None:
    conn.execute(text("CREATE SCHEMA IF NOT EXISTS oracle_lease"))
    t.metadata.create_all(conn)


def reset(conn: Connection, seed: Seed) -> dict[str, int]:
    t.metadata.drop_all(conn)
    create(conn)
    return load(conn, seed)


def ensure(conn: Connection, seed: Seed) -> None:
    create(conn)
    if conn.execute(text("SELECT count(*) FROM oracle_lease.contracts")).scalar_one() == 0:
        load(conn, seed)
