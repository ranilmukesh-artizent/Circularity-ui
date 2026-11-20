"""Salesforce Sales Cloud (crm): opportunities, accounts, re-lease contracts (the demo's SOURCES.crm).

REST API v59.0 under the instance URL (the mock's /salesforce), OAuth 2.0 JWT bearer as the connected app's
integration user. Every resource is a SOQL query paged with `nextRecordsUrl`; deltas by `SystemModstamp > <cursor>`.
Salesforce has authority over the opportunity stage (demand.status) and the lessee contact.

Facts
    demand.<Opportunity.Id>   demand_id, kind (replacement | lease), stage, status (Closed Won → confirmed, Closed Lost →
                              lost, any open stage → forecast), probability, need_by (CloseDate), buyer, qty,
                              amount (replacement: the avoided new purchase, USD) or lease_rate (USD / month),
                              ship_to_site, links: case_ref, asset_ref, relase_ref, contract_ref
    asset.<Asset_Id__c>       owner_tenant (the opportunity's account), case_ref, replacement_opportunity_ref,
                              lease_opportunity_ref; from the Contract: relase_ref, relase_contract_ref,
                              relase_contract_status, relase_start, relase_end, relase_term_months, relase_monthly_rate
    Account                   read for the raw record (tenant identity: Id, Name, Tenant_Key__c); its facts arrive
                              through the opportunities, which carry Account.Name in the same query
The demo's mapping (MAPPINGS.crm): Opportunity.StageName Proposal → demand.status forecast ("Stage map: Proposal →
forecast", RT-1048's re-lease opportunity); Account.Id 001Hs00003AbCdE → asset.owner_tenant Customer A ("Tenant key
lookup"); Opportunity.CloseDate → demand.need_by 2026-12-31 ("Date format"; the API returns ISO dates, so the source
value is 2026-12-31, not the demo's 31/12/2026). Not reproduced: Amount 2400 → lease_rate $2,400 / month; the seed
prices LS-5530 at 146.67 USD / month (the lease system's MONTHLY_RENTAL holds the 2,400).
The contract's Name (LS-5530) is the re-lease reference, not the running lease (LC-004417 in the lease system, which
owns asset.lease_ref), so it is recorded as relase_ref.
"""

import base64
import hashlib
import hmac
import json
import time
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime

from di.canonical.store import Fact
from di.connectors.base import Adapter, Record, Resource
from di.connectors.http import Auth, SourceClient, SourceError

API = "/services/data/v59.0"
BATCH = 200  # Sforce-Query-Options batchSize
CLIENT_ID = "3MVG9circularity.demo.northfield.crm.connector"
CLIENT_SECRET = "circularity-demo-salesforce-secret"  # noqa: S105 - the simulator's demo client secret
USERNAME = "integration@northfield.example"
STAGE_STATUS: dict[str | None, str] = {"Closed Won": "confirmed", "Closed Lost": "lost"}  # every open stage is a forecast
KINDS: dict[str | None, str] = {"Replacement": "replacement", "Lease": "lease", "New Business": "new_business"}

ACCOUNT_SOQL = "SELECT Id, Name, AccountNumber, Type, Tenant_Key__c, SystemModstamp FROM Account"
OPPORTUNITY_SOQL = (
    "SELECT Id, Name, Type, StageName, Probability, Amount, CloseDate, TotalOpportunityQuantity, AccountId, "
    "Account.Name, Account.Tenant_Key__c, ContractId, Case_Id__c, Asset_Id__c, Site__c, Lease_Reference__c, "
    "SystemModstamp FROM Opportunity"
)
CONTRACT_SOQL = (
    "SELECT Id, Name, ContractNumber, Status, StartDate, EndDate, ContractTerm, Monthly_Rate__c, AccountId, "
    "Account.Name, Asset_Id__c, Case_Id__c, SystemModstamp FROM Contract"
)


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


@dataclass
class JwtBearer(Auth):
    """OAuth 2.0 JWT bearer flow (urn:ietf:params:oauth:grant-type:jwt-bearer), as Salesforce connected apps use it.

    A real org verifies an RS256 signature with the app's certificate; the mock checks only the claims, so the
    assertion is signed HS256 with the consumer secret as a stand-in.
    """

    token_url: str
    client_id: str
    username: str
    secret: str
    audience: str = "https://login.salesforce.com"
    _token: str | None = None
    _expires: float = 0

    def assertion(self) -> str:
        head = _b64(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
        claims = {"iss": self.client_id, "sub": self.username, "aud": self.audience, "exp": int(time.time()) + 180}
        body = _b64(json.dumps(claims).encode())
        sig = _b64(hmac.new(self.secret.encode(), f"{head}.{body}".encode(), hashlib.sha256).digest())
        return f"{head}.{body}.{sig}"

    def headers(self, client, force_refresh=False):
        if force_refresh or not self._token or self._expires < time.time() + 30:
            form = {"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer", "assertion": self.assertion()}
            r = client.raw("POST", self.token_url, data=form, log_records=False)
            if r.status_code != 200:
                raise SourceError("auth", f"Token request failed: HTTP {r.status_code}", r.status_code)
            self._token = r.json()["access_token"]
            self._expires = time.time() + 3600  # Salesforce sessions last 2 h; no expires_in is returned
        return {"Authorization": "Bearer " + self._token}


def sf_time(v: str | None) -> str | None:
    """'2026-10-06T03:54:00.000+0000' → '2026-10-06T03:54:00.000+00:00' (always milliseconds, so cursors compare)."""
    if not v:
        return None
    return datetime.strptime(v, "%Y-%m-%dT%H:%M:%S.%f%z").astimezone(UTC).isoformat(timespec="milliseconds")


def soql_time(iso: str) -> str:
    """A cursor as a SOQL datetime literal."""
    return datetime.fromisoformat(iso).astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def id15(sfid: str | None) -> str | None:
    """The 15-character (case-sensitive) form of an id, as the Salesforce UI shows it: 001Hs00003AbCdE."""
    return sfid[:15] if sfid else None


class SalesforceAdapter(Adapter):
    source_id = "crm"
    base_path = "/salesforce"  # the instance URL

    def auth(self):
        return JwtBearer("/services/oauth2/token", CLIENT_ID, USERNAME, CLIENT_SECRET)

    def resources(self):
        return [
            Resource("account", self.read_accounts),
            Resource("opportunity", self.read_opportunities),
            Resource("contract", self.read_contracts),
        ]

    # ------------------------------------------------------------- reading
    def _query(self, client: SourceClient, soql: str, since: str | None) -> Iterator[tuple[dict, str]]:
        if since:
            soql += f" WHERE SystemModstamp > {soql_time(since)}"
        soql += " ORDER BY SystemModstamp, Id"
        headers = {"Sforce-Query-Options": f"batchSize={BATCH}"}
        r = client.request("GET", f"{API}/query", params={"q": soql}, headers=headers)
        while True:
            body = r.json()
            client.note_records(len(body["records"]))
            for rec in body["records"]:
                yield rec, str(r.request.url)
            if body.get("done", True) or not body.get("nextRecordsUrl"):
                return
            r = client.request("GET", body["nextRecordsUrl"], headers=headers)

    def _read(self, resource: str, soql: str, client: SourceClient, since: str | None) -> Iterator[Record]:
        for rec, url in self._query(client, soql, since):
            yield Record(resource, rec["Id"], rec, url, sf_time(rec.get("SystemModstamp")))

    def read_accounts(self, client, since):
        return self._read("account", ACCOUNT_SOQL, client, since)

    def read_opportunities(self, client, since):
        return self._read("opportunity", OPPORTUNITY_SOQL, client, since)

    def read_contracts(self, client, since):
        return self._read("contract", CONTRACT_SOQL, client, since)

    # ------------------------------------------------------------- mapping
    def map(self, record: Record) -> list[Fact]:
        if record.resource == "opportunity":
            return self._opportunity(record.payload)
        if record.resource == "contract":
            return self._contract(record.payload)
        return []  # accounts: tenant identity, applied through the opportunities' Account.Name

    def _opportunity(self, p: dict) -> list[Fact]:
        key = p["Id"]
        account = p.get("Account") or {}
        stage = p.get("StageName")
        status = STAGE_STATUS.get(stage, "forecast")
        kind = KINDS.get(p.get("Type"), (p.get("Type") or "").lower() or None)

        def d(field, value, sf, sv, transform="Pass-through"):
            return Fact("demand", key, field, value, sf, sv, transform)

        facts = [
            d("demand_id", key, "Opportunity.Id", key),
            d("kind", kind, "Opportunity.Type", p.get("Type"), "Type map"),
            d("stage", stage, "Opportunity.StageName", stage),
            d("status", status, "Opportunity.StageName", stage, f"Stage map: {stage} → {status}"),
            d("need_by", p.get("CloseDate"), "Opportunity.CloseDate", p.get("CloseDate"), "Date format"),
        ]
        if p.get("Probability") is not None:
            facts.append(d("probability", float(p["Probability"]), "Opportunity.Probability", p["Probability"], "Percent"))
        if account.get("Name"):
            facts.append(d("buyer", account["Name"], "Account.Id", id15(p.get("AccountId")), "Tenant key lookup"))
        if p.get("TotalOpportunityQuantity") is not None:
            q = p["TotalOpportunityQuantity"]
            facts.append(
                d("qty", int(q) if float(q).is_integer() else float(q), "Opportunity.TotalOpportunityQuantity", q, "Integer")
            )
        if p.get("Amount") is not None:
            amt = float(p["Amount"])
            if kind == "lease":
                facts.append(d("lease_rate", amt, "Opportunity.Amount", p["Amount"], "Currency + period normalised"))
            else:
                facts.append(d("amount", amt, "Opportunity.Amount", p["Amount"], "Currency (USD)"))
        for field, src in (
            ("ship_to_site", "Site__c"),
            ("case_ref", "Case_Id__c"),
            ("asset_ref", "Asset_Id__c"),
            ("relase_ref", "Lease_Reference__c"),
            ("contract_ref", "ContractId"),
        ):
            if p.get(src):
                facts.append(d(field, p[src], f"Opportunity.{src}", p[src]))

        asset = p.get("Asset_Id__c")
        if asset:
            if account.get("Name"):
                facts.append(
                    Fact(
                        "asset",
                        asset,
                        "owner_tenant",
                        account["Name"],
                        "Account.Id",
                        id15(p.get("AccountId")),
                        "Tenant key lookup",
                    )
                )
            if p.get("Case_Id__c"):
                facts.append(
                    Fact("asset", asset, "case_ref", p["Case_Id__c"], "Opportunity.Case_Id__c", p["Case_Id__c"], "Pass-through")
                )
            link = "lease_opportunity_ref" if kind == "lease" else "replacement_opportunity_ref"
            facts.append(Fact("asset", asset, link, key, "Opportunity.Id", key, "Pass-through"))
        return facts

    def _contract(self, p: dict) -> list[Fact]:
        asset = p.get("Asset_Id__c")
        if not asset:
            return []

        def a(field, value, sf, sv, transform="Pass-through"):
            return Fact("asset", asset, field, value, sf, sv, transform)

        facts = [
            a("relase_ref", p.get("Name"), "Contract.Name", p.get("Name")),
            a("relase_contract_ref", p["Id"], "Contract.Id", p["Id"]),
            a(
                "relase_contract_status",
                (p.get("Status") or "").lower() or None,
                "Contract.Status",
                p.get("Status"),
                "Lower case",
            ),
            a("relase_start", p.get("StartDate"), "Contract.StartDate", p.get("StartDate"), "ISO date"),
            a("relase_end", p.get("EndDate"), "Contract.EndDate", p.get("EndDate"), "ISO date"),
        ]
        if p.get("ContractTerm") is not None:
            facts.append(a("relase_term_months", int(p["ContractTerm"]), "Contract.ContractTerm", p["ContractTerm"], "Months"))
        if p.get("Monthly_Rate__c") is not None:
            facts.append(
                a(
                    "relase_monthly_rate",
                    float(p["Monthly_Rate__c"]),
                    "Contract.Monthly_Rate__c",
                    p["Monthly_Rate__c"],
                    "Currency + period normalised",
                )
            )
        if p.get("Case_Id__c"):
            facts.append(a("case_ref", p["Case_Id__c"], "Contract.Case_Id__c", p["Case_Id__c"]))
        return facts


ADAPTER = SalesforceAdapter()
