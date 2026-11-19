"""Load the seed (B2) into the Salesforce org, as Sales Operations would hold it at the demo's as-of time.

What Salesforce owns here (the demo's SOURCES.crm: "opportunities, accounts, renewal pipeline, quoted rates";
authority over "Opportunity stage" and "Lessee contact"):
- User         the integration user (the DI connector) and Sales Operations, which owns every record
- Account      one per tenant. Customer A is 001Hs00003AbCdE (the demo's MAPPINGS.crm example), B and C follow it.
               Tenant_Key__c is the lessee key the lease system uses (CUSTOMER_A).
- Contact      one lessee contact per account
- Opportunity  per case with internal demand: the replacement demand (Type 'Replacement'). StageName 'Closed Won'
               when the demand is confirmed, 'Proposal' when it is a forecast (the demo's stage map:
               Proposal → forecast). CloseDate is the need-by date, by the demo's own rule (RT-1048: 2026-10-17,
               otherwise as-of + 12..39 days from the case's hash). Amount is the avoided new purchase (RT-1048: 12,000).
               per case with a lease reference: the re-lease opportunity (Type 'Lease'), its stage from the
               re-lease route's demand status. Amount is the monthly lease rate (lease income ÷ term months), and
               CloseDate the end of the current quarter (2026-12-31), as pipeline opportunities close in Salesforce.
- Contract     per lease reference (RT-1048: LS-5530), Draft while the lease opportunity is open, starting the day
               after the opportunity's close date, with the term and monthly rate of the re-lease route
- Task         one follow-up task per lease opportunity, assigned to Sales Operations
Ids are deterministic (same seed, same ids). Records count as created 20-60 days and last modified 1-6 days before
the as-of time (2026-10-07T09:00Z), so a delta read `WHERE SystemModstamp > 2026-10-07T09:00:00Z` starts empty.
"""

import calendar
import re
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import insert, text
from sqlalchemy.engine import Connection

from sim.seed import Seed
from sim.vendors.salesforce import auth
from sim.vendors.salesforce.schema import POD, STAGE_RULES, TABLES, make_id, metadata, to18

ACCOUNT_TAILS = ("0003AbCdE", "0003AbCdF", "0003AbCdG")  # Customer A, B, C
CONTACTS = (("Priya", "Raman"), ("Arjun", "Mehta"), ("Kavya", "Iyer"))
OWNER = "sales.ops@northfield.example"


def fnv(s: str) -> int:
    """The demo's hashId (32-bit FNV-1a)."""
    h = 2166136261
    for ch in s:
        h ^= ord(ch)
        h = (h * 16777619) & 0xFFFFFFFF
    return h


def need_by(case_id: str, as_of: datetime) -> date:
    """The demo's exDemand().needBy: EX_NEED for RT-1048, else as-of + 12..39 days."""
    if case_id == "RT-1048":
        return date(2026, 10, 17)
    return (as_of + timedelta(days=12 + fnv(case_id + "|ex|nb") % 28)).date()


def quarter_end(d: date) -> date:
    month = (d.month - 1) // 3 * 3 + 3
    return date(d.year, month, calendar.monthrange(d.year, month)[1])


def account_id(i: int) -> str:
    return to18("001" + POD + ACCOUNT_TAILS[i])


def _stamps(key: str, as_of: datetime, owner: str) -> dict:
    h = fnv(key)
    created = as_of - timedelta(days=20 + h % 40, hours=h % 9)
    modified = as_of - timedelta(days=1 + h % 6, minutes=h % 600)
    return {
        "IsDeleted": False,
        "CreatedDate": created,
        "CreatedById": owner,
        "LastModifiedDate": modified,
        "LastModifiedById": owner,
        "SystemModstamp": modified,
        "OwnerId": owner,
    }


def _usd(v: float | Decimal) -> Decimal:
    return Decimal(str(v)).quantize(Decimal("0.01"), ROUND_HALF_UP)


def _stage(stage: str) -> dict:
    prob, cat, closed, won = STAGE_RULES[stage]
    return {"StageName": stage, "Probability": prob, "ForecastCategoryName": cat, "IsClosed": closed, "IsWon": won}


def load(conn: Connection, seed: Seed) -> dict[str, int]:
    w = seed.world
    as_of = w.as_of
    owner = auth.user_id(OWNER)
    rows: dict[str, list[dict]] = {name: [] for name in TABLES}

    for username, (_, first, last, title) in auth.USERS.items():
        uid = auth.user_id(username)
        rows["User"].append(
            _stamps(username, as_of, uid)
            | {"Id": uid, "Username": username, "Name": f"{first} {last}", "FirstName": first, "LastName": last}
            | {"Email": username, "Alias": (first[0] + last)[:8].lower(), "Title": title, "IsActive": True}
        )
    for r in rows["User"]:
        r.pop("OwnerId")

    accounts, contacts = {}, {}
    for i, tenant in enumerate(w.tenants):
        aid = account_id(i)
        accounts[tenant] = aid
        letter = tenant.split()[-1]
        rows["Account"].append(
            _stamps(aid, as_of, owner)
            | {"Id": aid, "Name": tenant, "AccountNumber": f"CUST-{letter}", "Type": "Customer - Direct"}
            | {"Industry": "Manufacturing", "BillingCountry": "India", "Tenant_Key__c": tenant.upper().replace(" ", "_")}
        )
        cid = make_id("003", 1 + i)
        contacts[tenant] = cid
        first, last = CONTACTS[i % len(CONTACTS)]
        rows["Contact"].append(
            _stamps(cid, as_of, owner)
            | {"Id": cid, "AccountId": aid, "FirstName": first, "LastName": last, "Name": f"{first} {last}"}
            | {
                "Title": "Lessee contact · Procurement",
                "Email": f"{first.lower()}.{last.lower()}@customer-{letter.lower()}.example",
            }
        )

    close_pipeline = quarter_end(as_of.date())
    for case in sorted(seed.cases.values(), key=lambda c: c.facts.id):
        f = case.facts
        num = int(f.id.split("-")[1])
        aid = accounts[f.owner]
        common = {"AccountId": aid, "Case_Id__c": f.id, "Asset_Id__c": f.asset_id, "TotalOpportunityQuantity": f.qty}
        if f.demand.internal:
            oid = make_id("006", num * 10 + 1)
            site = f.demand.site or f.location
            purchase = max((t.amt for r in f.routes for t in r.terms if t.kind == "purchase"), default=0)
            redeploy = next((r for r in f.routes if r.id == "redeploy"), None)
            rows["Opportunity"].append(
                _stamps(oid, as_of, owner)
                | common
                | _stage("Closed Won" if f.demand.confirmed else "Proposal")
                | {
                    "Id": oid,
                    "Name": f"{f.owner} · {site} · replacement {f.product.lower()}",
                    "Type": "Replacement",
                    "Amount": _usd(purchase) if purchase else None,
                    "CloseDate": need_by(f.id, as_of),
                    "Site__c": site,
                    "Description": redeploy.demand_label if redeploy else None,
                }
            )
        if f.demand.lease:
            lease = f.demand.lease
            relase = next((r for r in f.routes if r.id == "relase"), None)
            status = (relase.demand_status if relase else None) or "forecast"
            lease_terms = [t for t in relase.terms if t.kind == "lease"] if relase else []
            m = re.search(r"over (\d+) months", lease_terms[0].label) if lease_terms else None
            months = int(m.group(1)) if m else 30
            monthly = _usd(Decimal(str(sum(t.amt for t in lease_terms))) / months) if lease_terms else None
            confirmed = status == "confirmed"
            close = as_of.date() if confirmed else close_pipeline
            start = close + timedelta(days=1)
            end_month = start.month - 1 + months
            end = date(start.year + end_month // 12, end_month % 12 + 1, 1) - timedelta(days=1)
            kid = make_id("800", num)
            oid = make_id("006", num * 10 + 2)
            rows["Contract"].append(
                _stamps(kid, as_of, owner)
                | {
                    "Id": kid,
                    "AccountId": aid,
                    "Name": lease,
                    "ContractNumber": f"{num:08d}",
                    "Status": "Activated" if confirmed else "Draft",
                    "StartDate": start,
                    "ContractTerm": months,
                    "EndDate": end,
                    "Description": f"Re-lease of {f.asset_id} ({f.product.lower()}) to {f.owner}",
                    "Asset_Id__c": f.asset_id,
                    "Case_Id__c": f.id,
                    "Monthly_Rate__c": monthly,
                }
            )
            rows["Opportunity"].append(
                _stamps(oid, as_of, owner)
                | common
                | _stage("Closed Won" if confirmed else "Proposal")
                | {
                    "Id": oid,
                    "Name": f"{f.owner} · re-lease {f.asset_id} ({lease})",
                    "Type": "Lease",
                    "Amount": monthly,
                    "CloseDate": close,
                    "ContractId": kid,
                    "Lease_Reference__c": lease,
                    "Description": f"Amount is the monthly lease rate in USD over {months} months. "
                    + (relase.demand_label if relase and relase.demand_label else ""),
                }
            )
            tid = make_id("00T", num)
            rows["Task"].append(
                _stamps(tid, as_of, owner)
                | {
                    "Id": tid,
                    "Subject": f"Follow up lease proposal {lease}",
                    "Status": "Completed" if confirmed else "Not Started",
                    "Priority": "Normal",
                    "Type": "Call",
                    "ActivityDate": (as_of + timedelta(days=7)).date(),
                    "WhatId": oid,
                    "WhoId": contacts[f.owner],
                    "AccountId": aid,
                    "IsClosed": confirmed,
                }
            )
    for name, table in TABLES.items():
        if rows[name]:
            conn.execute(insert(table), [{c: r.get(c) for c in table.c.keys()} for r in rows[name]])
    return {name: len(r) for name, r in rows.items()}


def create(conn: Connection) -> None:
    conn.execute(text("CREATE SCHEMA IF NOT EXISTS salesforce"))
    metadata.create_all(conn)


def reset(conn: Connection, seed: Seed) -> dict[str, int]:
    metadata.drop_all(conn)
    create(conn)
    return load(conn, seed)


def ensure(conn: Connection, seed: Seed) -> None:
    create(conn)
    if conn.execute(text("SELECT count(*) FROM salesforce.account")).scalar_one() == 0:
        load(conn, seed)
