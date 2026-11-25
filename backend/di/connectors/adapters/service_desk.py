"""Service desk tickets and upgrade offers (sdesk, plan 9 P9-4.1): ServiceNow customer service cases and the upgrade
offers customers were sent. Read only.

Written against source-sim's ServiceNow mock (tables `sn_customerservice_case` and `u_upgrade_offer`), a synthetic
stand-in: no real ServiceNow is connected. Same Table API and OAuth client-credentials sign-in as the field service
adapter (`fsm`, adapters/servicenow.py): `sysparm_query` with a delta on `sys_updated_on`, oldest change first,
`sysparm_limit` / `sysparm_offset` until a short page.

Not one of the demo's 21 sources: it starts unregistered (no source_system row), so every demo screen and count is
unchanged. di.connectors.extra registers it, source.reconnect connects it.

It writes plain tables, not canonical facts (`map` makes none; the sync still keeps every record raw):
    cases    (state New only)  service_ticket  number, account, market, site, batch_id (None for one tool), lines (the
                               JSON of u_lines), requester_role, loaner_promised, opened_at; `case_id` is never touched
                               by a sync (a case opened from the ticket keeps it)
    offers                     upgrade_offer   id (sys_id), account, market, model_class, offered_on, credit_pct,
                               credit_amount, currency, accepted
Rows are landed in the sync's own session as each page is read, so a failed or dry run undoes them with it. They are
idempotent on the source key: reading a record again changes nothing. They belong to the source's org unit (None: shared).
"""

import json
from collections.abc import Iterator

from sqlalchemy import text

from di.connectors.adapters.servicenow import changed, cursor, sn_utc, value
from di.connectors.base import Adapter, Record, Resource
from di.connectors.http import OAuthClientCredentials, SourceClient
from di.services.canonical.store import Fact

API = "/servicenow/api/now/table"
PAGE = 200
OPEN = "1"  # sn_customerservice_case.state New

UPSERT_TICKET = text(
    "INSERT INTO service_ticket (number, org_unit_id, account, market, site, batch_id, lines, requester_role, "
    "loaner_promised, opened_at, source) VALUES (:number, :org, :account, :market, :site, :batch, CAST(:lines AS jsonb), "
    ":role, :loaner, CAST(:opened AS timestamptz), :src) ON CONFLICT (number) DO UPDATE SET "
    "org_unit_id = EXCLUDED.org_unit_id, account = EXCLUDED.account, market = EXCLUDED.market, site = EXCLUDED.site, "
    "batch_id = EXCLUDED.batch_id, lines = EXCLUDED.lines, requester_role = EXCLUDED.requester_role, "
    "loaner_promised = EXCLUDED.loaner_promised, opened_at = EXCLUDED.opened_at, source = EXCLUDED.source"
)
UPSERT_OFFER = text(
    "INSERT INTO upgrade_offer (id, org_unit_id, account, market, model_class, offered_on, credit_pct, credit_amount, "
    "currency, accepted, source) VALUES (:id, :org, :account, :market, :cls, CAST(:on AS date), :pct, :amount, :cur, "
    ":accepted, :src) ON CONFLICT (id) DO UPDATE SET org_unit_id = EXCLUDED.org_unit_id, account = EXCLUDED.account, "
    "market = EXCLUDED.market, model_class = EXCLUDED.model_class, offered_on = EXCLUDED.offered_on, "
    "credit_pct = EXCLUDED.credit_pct, credit_amount = EXCLUDED.credit_amount, currency = EXCLUDED.currency, "
    "accepted = EXCLUDED.accepted, source = EXCLUDED.source"
)


def _org(client: SourceClient) -> str | None:
    """The org unit the source is bound to (None: shared)."""
    return client.session.execute(text("SELECT org_unit_id FROM source_system WHERE id = :i"), {"i": client.source_id}).scalar()


def ticket_params(row: dict, org: str | None, source: str) -> dict:
    return {
        "number": value(row, "number"), "org": org, "account": value(row, "account"), "market": value(row, "u_market"),
        "site": value(row, "u_site"), "batch": value(row, "u_batch_id") or None,
        "lines": json.dumps(json.loads(value(row, "u_lines") or "[]")), "role": value(row, "u_requester_role"),
        "loaner": value(row, "u_loaner_promised") == "true", "opened": sn_utc(value(row, "opened_at")), "src": source,
    }  # fmt: skip


def offer_params(row: dict, org: str | None, source: str) -> dict:
    return {
        "id": value(row, "sys_id"), "org": org, "account": value(row, "account"), "market": value(row, "u_market"),
        "cls": value(row, "u_model_class"), "on": value(row, "u_offered_at")[:10], "pct": value(row, "u_credit_pct") or None,
        "amount": value(row, "u_credit_amount") or None, "cur": value(row, "u_currency"),
        "accepted": value(row, "u_accepted") == "true", "src": source,
    }  # fmt: skip


class ServiceDeskAdapter(Adapter):
    source_id = "sdesk"
    provisioned = False  # no demo source: registered and connected by a person (di.connectors.extra)
    extra = True
    vendor = "ServiceNow Customer Service (synthetic)"
    source_type = "sdesk"
    interval = 60
    owner = "Integration Engineering"

    def auth(self, conn=None, secret=None):  # noqa: ARG002 - conn: the Adapter interface
        return OAuthClientCredentials(
            "/servicenow/oauth_token.do", "circularity-di", secret or "circularity-demo-sn-secret", form=True
        )

    def resources(self):
        return [
            Resource("sn_customerservice_case", lambda client, since: self._table(client, "sn_customerservice_case", since)),
            Resource("u_upgrade_offer", lambda client, since: self._table(client, "u_upgrade_offer", since)),
        ]

    def _table(self, client: SourceClient, table: str, since: str | None) -> Iterator[Record]:
        offers = table == "u_upgrade_offer"
        query = (
            ("" if offers else f"state={OPEN}^") + (f"sys_updated_on>{cursor(since)}^" if since else "") + "ORDERBYsys_updated_on"
        )
        params = {"sysparm_query": query, "sysparm_limit": PAGE}
        org, offset = _org(client), 0
        while True:
            r = client.request("GET", f"{API}/{table}", params=params | {"sysparm_offset": offset})
            rows = r.json()["result"]
            client.note_records(len(rows))
            if rows:
                if offers:
                    client.session.execute(UPSERT_OFFER, [offer_params(x, org, client.source_id) for x in rows])
                else:
                    client.session.execute(UPSERT_TICKET, [ticket_params(x, org, client.source_id) for x in rows])
            for row in rows:
                key = value(row, "sys_id" if offers else "number")
                yield Record(table, key, row, str(r.request.url), changed(value(row, "sys_updated_on")))
            if len(rows) < PAGE:
                return
            offset += PAGE

    def map(self, record: Record) -> list[Fact]:  # noqa: ARG002 - the rows are landed as they are read
        return []


ADAPTER = ServiceDeskAdapter()
