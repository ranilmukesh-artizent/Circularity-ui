"""Oracle Lease and Finance Management (the demo's SOURCES.lease): contract end dates, lease rates, lessee and asset
ownership, renewal options. Read: GET /leaseContracts, /leaseAssets, /leaseRenewals. No writes.

Field names follow the demo's MAPPINGS.lease (LEASE_CONTRACT_ID, CONTRACT_END_DATE, LESSEE_NAME, MONTHLY_RENTAL).
- One contract per returned asset, lessee = the owner tenant. Contract numbers run with the case number, so RT-1048
  (MTR-2041) is LC-004417; its end date is the demo's 2026-12-31 and its rental 2400.00 USD (the rate is calibrated
  so that the demo's example comes out: value new x size x quantity x 0.2034, rounded to 10).
- One lease asset per asset (ownership), plus MTR-2077, whose owner the demo's conflict CF-31 takes from here.
- One renewal (re-lease opportunity) per asset with a lease opportunity in the demo (RT-1048: LS-5530, forecast).
"""

import calendar
import re
from datetime import date

from sim.generic.spec import Auth, Paging, Resource, Spec
from sim.generic.specs.assetwise import hash_id, js_round
from sim.seed import Seed
from sim.seed.model import CaseFacts

RATE = 0.2034
TERMS = (24, 36, 48, 60)
FIXED_END = {"LC-004417": date(2026, 12, 31)}  # the demo's MAPPINGS.lease example
EXTRA_ASSETS = [("MTR-2077", "motor", "Customer A")]  # the demo's ownership conflict CF-31: lease says Customer A


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


def seed(s: Seed) -> dict[str, list[dict]]:
    as_of = s.world.as_of.date()
    contracts, assets, renewals = [], [], []
    for case in s.cases.values():
        f = case.facts
        cls = s.world.classes[f.cls]
        cid = contract_id(f)
        h = hash_id(cid)
        term = TERMS[h % len(TERMS)]
        end = FIXED_END.get(cid) or _month_end(as_of.year, as_of.month + 1 + (h >> 4) % 9)
        idx = end.year * 12 + end.month - term  # the month after (end - term), zero-based
        start = date(idx // 12, idx % 12 + 1, 1)
        rental = js_round(cls.pnew * _size(f) * f.qty * RATE / 10) * 10
        contracts.append(
            {
                "LEASE_CONTRACT_ID": cid,
                "CONTRACT_NUMBER": cid,
                "CONTRACT_STATUS": "ACTIVE" if end >= as_of else "EXPIRED",
                "LESSEE_NAME": tenant_key(f.owner),
                "LESSEE_DISPLAY_NAME": f.owner,
                "CONTRACT_START_DATE": start.isoformat(),
                "CONTRACT_END_DATE": end.isoformat(),
                "TERM_MONTHS": term,
                "MONTHLY_RENTAL": float(rental),
                "CURRENCY_CODE": "USD",
                "BILLING_FREQUENCY": "MONTHLY",
                "RENEWAL_OPTION": "RENEW_OR_RETURN" if f.demand.lease else "RETURN",
                "ASSET_NUMBER": f.asset_id,
                "ASSET_COUNT": f.qty,
            }
        )
        assets.append(
            {
                "ASSET_NUMBER": f.asset_id,
                "ASSET_DESCRIPTION": f"{f.product} · {f.mfr}",
                "ASSET_CATEGORY": cls.label.upper().replace(" ", "_"),
                "MANUFACTURER": f.mfr,
                "QUANTITY": f.qty,
                "OWNER_NAME": tenant_key(f.owner),
                "OWNERSHIP_TYPE": "CUSTOMER_OWNED",
                "LEASE_CONTRACT_ID": cid,
                "LESSEE_NAME": tenant_key(f.owner),
                "LEASE_STATUS": "RETURNED",
                "RETURN_DATE": f.received.date().isoformat(),
                "ORIGINAL_COST": round(cls.pnew * _size(f) * f.qty, 2),
                "CURRENCY_CODE": "USD",
                "AGE_YEARS": f.age,
            }
        )
        if f.demand.lease:
            rl = next((r for r in f.routes if r.id == "relase"), None)
            income = next((t for t in rl.terms if t.kind == "lease"), None) if rl else None
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
                    "OPTION_EXPIRY_DATE": contracts[-1]["CONTRACT_END_DATE"],
                }
            )
    for asset_id, cls_id, owner in EXTRA_ASSETS:
        cls = s.world.classes[cls_id]
        assets.append(
            {
                "ASSET_NUMBER": asset_id,
                "ASSET_DESCRIPTION": cls.label,
                "ASSET_CATEGORY": cls.label.upper().replace(" ", "_"),
                "MANUFACTURER": cls.mfr[0],
                "QUANTITY": 1,
                "OWNER_NAME": tenant_key(owner),
                "OWNERSHIP_TYPE": "CUSTOMER_OWNED",
                "LEASE_CONTRACT_ID": None,
                "LESSEE_NAME": tenant_key(owner),
                "LEASE_STATUS": "ON_LEASE",
                "RETURN_DATE": None,
                "ORIGINAL_COST": cls.pnew,
                "CURRENCY_CODE": "USD",
                "AGE_YEARS": None,
            }
        )
    return {"leaseContracts": contracts, "leaseAssets": assets, "leaseRenewals": renewals}


SPEC = Spec(
    source_id="lease",
    title="Oracle Lease and Finance Management",
    schema="oracle_lease",
    base_path="/oracle-lease/fscmRestApi",
    auth=Auth("oauth_cc"),
    paging=Paging("offset", items_key="items", next_key="nextOffset", total_key="totalResults", default_size=25, max_size=500),
    resources=(
        Resource(
            "leaseContracts",
            "/leaseContracts",
            "LEASE_CONTRACT_ID",
            filters=("ASSET_NUMBER", "LESSEE_NAME", "CONTRACT_STATUS", "RENEWAL_OPTION"),
        ),
        Resource(
            "leaseAssets",
            "/leaseAssets",
            "ASSET_NUMBER",
            filters=("OWNER_NAME", "LEASE_CONTRACT_ID", "LEASE_STATUS", "ASSET_CATEGORY"),
        ),
        Resource(
            "leaseRenewals",
            "/leaseRenewals",
            "RENEWAL_ID",
            filters=("ASSET_NUMBER", "LEASE_OPPORTUNITY_ID", "LEASE_CONTRACT_ID", "STATUS"),
        ),
    ),
    seed=seed,
)
