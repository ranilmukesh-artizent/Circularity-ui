"""Oracle Lease and Finance Management (lease): contracts, lease assets, renewals (the demo's SOURCES.lease). Read only.

Oracle E-Business Suite Integrated SOA Gateway REST under /oracle-lease/webservices/rest, HTTP Basic with the EBS
user DI_CONNECTOR. Reads are GET calls of the query service xxoklleasequery (get_contracts, get_lease_assets,
get_renewals) with P_START_INDEX / P_MAX_RECORDS paging until X_HAS_MORE = N; delta reads pass
P_LAST_UPDATE_DATE_FROM = the newest LAST_UPDATE_DATE seen (each record's own stamp is Record.changed).

Facts (lease has authority over ownership, lessee and contract term) — as before B5b:
    asset.<ASSET_NUMBER>   lease_ref, contract_end, contract_start, owner_tenant, lessee (tenant key: CUSTOMER_A →
                           Customer A), lease_rate (USD per month), lease_term_months, contract_status (BOOKED →
                           active; expired, evergreen, terminated), renewal_option; from the lease assets:
                           lease_status, ownership_type, original_cost, returned_on (and the owner of an asset not on
                           a contract)
    demand.<LEASE_OPPORTUNITY_ID>   kind re_lease, asset_ref, lease_ref, need_by (option expiry), status, site,
                           proposed_term_months, proposed_rental
The demo's mapping (MAPPINGS.lease) is unchanged: LEASE_CONTRACT_ID LC-004417 → asset.lease_ref (Pass-through);
CONTRACT_END_DATE 2026-12-31 (ISO date); LESSEE_NAME CUSTOMER_A → asset.owner_tenant Customer A (Tenant key);
MONTHLY_RENTAL 2400.00 USD → $2,400 / month (Currency + period normalised).
"""

from collections.abc import Iterator
from decimal import Decimal

import httpx

from di.canonical.store import Fact
from di.connectors.base import Adapter, Record, Resource
from di.connectors.generic import FX_NOTE, keep, tenant_name, to_usd
from di.connectors.http import Basic, SourceClient, SourceError

QUERY = "/xxoklleasequery"
PAGE = 500
STATUS = {"BOOKED": "active", "EXPIRED": "expired", "EVERGREEN": "evergreen", "TERMINATED": "terminated"}


class OracleLeaseAdapter(Adapter):
    source_id = "lease"
    base_path = "/oracle-lease/webservices/rest"

    def auth(self):
        return Basic("DI_CONNECTOR", "lease-demo-password")

    def resources(self):
        return [
            Resource("leaseContracts", self.reader("leaseContracts", "get_contracts", "X_CONTRACTS", "LEASE_CONTRACT_ID")),
            Resource("leaseAssets", self.reader("leaseAssets", "get_lease_assets", "X_ASSETS", "ASSET_NUMBER")),
            Resource("leaseRenewals", self.reader("leaseRenewals", "get_renewals", "X_RENEWALS", "RENEWAL_ID")),
        ]

    def pages(self, client: SourceClient, method: str, name: str, since: str | None) -> Iterator[tuple[dict, str]]:
        start = 1
        while True:
            q = {"P_START_INDEX": str(start), "P_MAX_RECORDS": str(PAGE)}
            if since:
                q["P_LAST_UPDATE_DATE_FROM"] = since
            path = f"{QUERY}/{method}/"
            out = client.get_json(path, params=q)["OutputParameters"]
            if out.get("X_RETURN_STATUS") != "S":
                raise SourceError("client", f"lease: {method} returned {out.get('X_RETURN_STATUS')}: {out.get('X_MSG_DATA')}")
            rows = (out.get(name) or {}).get(f"{name}_ITEM") or []
            client.note_records(len(rows))
            url = str(httpx.URL(client.url(path), params=q))
            for row in rows:
                yield row, url
            if out.get("X_HAS_MORE") != "Y" or not rows:
                return
            start += len(rows)

    def reader(self, resource: str, method: str, name: str, id_field: str):
        def read(client: SourceClient, since):
            for row, url in self.pages(client, method, name, since):
                yield Record(resource, str(row[id_field]), row, url, row.get("LAST_UPDATE_DATE"))

        return read

    def map(self, record: Record) -> list[Fact]:
        p = record.payload
        if record.resource == "leaseContracts":
            return keep(self._contract(p))
        if record.resource == "leaseAssets":
            return keep(self._asset(p))
        if record.resource == "leaseRenewals":
            return keep(self._renewal(p))
        return []

    def _contract(self, p: dict) -> list[Fact]:
        key = p["ASSET_NUMBER"]
        cur = p.get("CURRENCY_CODE") or "USD"
        rental = p.get("MONTHLY_RENTAL")
        freq = (p.get("BILLING_FREQUENCY") or "MONTHLY").upper()
        per_month = {"MONTHLY": 1, "QUARTERLY": Decimal(1) / 3, "ANNUAL": Decimal(1) / 12, "YEARLY": Decimal(1) / 12}[freq]
        lessee = p["LESSEE_NAME"]
        status = p.get("CONTRACT_STATUS")
        facts = [
            Fact("asset", key, "lease_ref", p["LEASE_CONTRACT_ID"], "LEASE_CONTRACT_ID", p["LEASE_CONTRACT_ID"], "Pass-through"),
            Fact("asset", key, "contract_end", p["CONTRACT_END_DATE"], "CONTRACT_END_DATE", p["CONTRACT_END_DATE"], "ISO date"),
            Fact(
                "asset",
                key,
                "contract_start",
                p.get("CONTRACT_START_DATE"),
                "CONTRACT_START_DATE",
                p.get("CONTRACT_START_DATE"),
                "ISO date",
            ),
            Fact("asset", key, "owner_tenant", tenant_name(lessee), "LESSEE_NAME", lessee, "Tenant key"),
            Fact("asset", key, "lessee", tenant_name(lessee), "LESSEE_NAME", lessee, "Tenant key"),
            Fact("asset", key, "lease_term_months", p.get("TERM_MONTHS"), "TERM_MONTHS", p.get("TERM_MONTHS"), "Integer"),
            Fact(
                "asset",
                key,
                "contract_status",
                STATUS.get(status or "", (status or "").lower() or None),
                "CONTRACT_STATUS",
                status,
                "Status map",
            ),
            Fact(
                "asset",
                key,
                "renewal_option",
                (p.get("RENEWAL_OPTION") or "").lower() or None,
                "RENEWAL_OPTION",
                p.get("RENEWAL_OPTION"),
                "Option map",
            ),
        ]
        if rental is not None:
            usd = to_usd(Decimal(str(rental)) * per_month, cur)
            facts.append(
                Fact(
                    "asset",
                    key,
                    "lease_rate",
                    usd,
                    "MONTHLY_RENTAL",
                    f"{Decimal(str(rental)):.2f} {cur}",
                    "Currency + period normalised",
                )
            )
        return facts

    def _asset(self, p: dict) -> list[Fact]:
        key = p["ASSET_NUMBER"]
        facts = [
            Fact(
                "asset",
                key,
                "lease_status",
                (p.get("LEASE_STATUS") or "").lower() or None,
                "LEASE_STATUS",
                p.get("LEASE_STATUS"),
                "Status map",
            ),
            Fact(
                "asset",
                key,
                "ownership_type",
                (p.get("OWNERSHIP_TYPE") or "").lower() or None,
                "OWNERSHIP_TYPE",
                p.get("OWNERSHIP_TYPE"),
                "Code map",
            ),
        ]
        if p.get("ORIGINAL_COST") is not None:
            cur = p.get("CURRENCY_CODE") or "USD"
            facts.append(
                Fact(
                    "asset",
                    key,
                    "original_cost",
                    to_usd(p["ORIGINAL_COST"], cur),
                    "ORIGINAL_COST",
                    f"{p['ORIGINAL_COST']} {cur}",
                    "Currency" if cur == "USD" else f"Currency at {FX_NOTE[cur]}",
                )
            )
        if p.get("RETURN_DATE"):
            facts.append(Fact("asset", key, "returned_on", p["RETURN_DATE"], "RETURN_DATE", p["RETURN_DATE"], "ISO date"))
        if not p.get("LEASE_CONTRACT_ID"):
            owner = p.get("OWNER_NAME") or p.get("LESSEE_NAME")
            facts.append(Fact("asset", key, "owner_tenant", tenant_name(owner), "OWNER_NAME", owner, "Tenant key"))
            if p.get("LESSEE_NAME"):
                facts.append(
                    Fact("asset", key, "lessee", tenant_name(p["LESSEE_NAME"]), "LESSEE_NAME", p["LESSEE_NAME"], "Tenant key")
                )
        return facts

    def _renewal(self, p: dict) -> list[Fact]:
        key = p["LEASE_OPPORTUNITY_ID"]
        status = {"FORECAST": "forecast", "CONFIRMED": "confirmed"}.get(p.get("STATUS") or "", (p.get("STATUS") or "").lower())
        facts = [
            Fact("demand", key, "kind", "re_lease", "RENEWAL_TYPE", p.get("RENEWAL_TYPE"), "Renewal type map"),
            Fact("demand", key, "asset_ref", p["ASSET_NUMBER"], "ASSET_NUMBER", p["ASSET_NUMBER"], "Pass-through"),
            Fact("demand", key, "lease_ref", p["LEASE_CONTRACT_ID"], "LEASE_CONTRACT_ID", p["LEASE_CONTRACT_ID"], "Pass-through"),
            Fact(
                "demand",
                key,
                "need_by",
                p.get("OPTION_EXPIRY_DATE"),
                "OPTION_EXPIRY_DATE",
                p.get("OPTION_EXPIRY_DATE"),
                "ISO date",
            ),
            Fact("demand", key, "status", status, "STATUS", p.get("STATUS"), "Status map"),
            Fact("demand", key, "site", p.get("SITE"), "SITE", p.get("SITE"), "Pass-through"),
            Fact(
                "demand",
                key,
                "proposed_term_months",
                p.get("PROPOSED_TERM_MONTHS"),
                "PROPOSED_TERM_MONTHS",
                p.get("PROPOSED_TERM_MONTHS"),
                "Integer",
            ),
        ]
        if p.get("PROPOSED_MONTHLY_RENTAL") is not None:
            cur = p.get("CURRENCY_CODE") or "USD"
            facts.append(
                Fact(
                    "demand",
                    key,
                    "proposed_rental",
                    to_usd(p["PROPOSED_MONTHLY_RENTAL"], cur),
                    "PROPOSED_MONTHLY_RENTAL",
                    f"{Decimal(str(p['PROPOSED_MONTHLY_RENTAL'])):.2f} {cur}",
                    "Currency + period normalised",
                )
            )
        return facts


ADAPTER = OracleLeaseAdapter()
