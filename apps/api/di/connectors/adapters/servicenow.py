"""ServiceNow Field Service Management (fsm): service demand, dispatch, visit outcomes (the demo's SOURCES.fsm).

Table API under /servicenow/api/now with an OAuth 2.0 client-credentials bearer (runs as di.integration). Each table
is read with sysparm_query (delta: `sys_updated_on>YYYY-MM-DD HH:MM:SS`, UTC), oldest change first, sysparm_limit /
sysparm_offset until a short page, values and display values (sysparm_display_value=all) and dot-walked fields.
Reading oldest change first means that, per asset, the latest work order and visit are applied last and win.
FSM has authority over service demand (demand.service_demand) and dispatch status.

Facts
    asset.<asset_tag>       (alm_asset) source_refs ["FSM:<serial>"], serial_number, model, install_status,
                            substatus, installed_site (units in use at a customer site), install_date,
                            warranty_expiration, case_ref (from the comments: "Returned … (RT-1048)")
                            (wm_order with an asset: service history and removal) work_order_ref, work_order_state,
                            work_order_type
                            (wm_task with an asset, closed) availability (State map: 3 → in_service,
                            4 → needs_service), last_visit_ref
    condition.<asset_tag>   (wm_task with an asset, closed) service_date (closed_at, UTC), service_outcome
                            (close_code), service_hours (work_duration)
    demand.<key>            (wm_order without an asset: install / delivery demand at a customer site; key = the
                            correlated OMS order, e.g. SO-48102, else the work order number) service_demand
                            {work_order, work_type, state, site, due, qty}, service_order_ref, service_state,
                            service_due, ship_to_site, buyer, qty, order_ref (correlation_id)
                            (its wm_task) dispatch_status, dispatch_task_ref, dispatch_tech
The demo's mapping (MAPPINGS.fsm, all reproduced on MTR-2041): wm_order.number WO0010382 → asset.work_order_ref
(Pass-through); alm_asset.serial_number SN-77120-A → asset.source_refs[] FSM:SN-77120-A (Prefixed with system);
wm_task.state 3 → asset.availability in_service (State map: 3 → in_service); wm_task.closed_at 2026-09-30 14:05:11 →
condition.service_date 2026-09-30T14:05:11Z (Local time → UTC).
"""

import re
from collections.abc import Iterator
from datetime import UTC, datetime

from di.canonical.store import Fact
from di.connectors.base import Adapter, Record, Resource
from di.connectors.http import OAuthClientCredentials, SourceClient

API = "/servicenow/api/now/table"
PAGE = 200
TASK_AVAILABILITY = {"3": "in_service", "4": "needs_service"}
CASE_IN_COMMENT = re.compile(r"\(([A-Z]{2,4}-\d+)\)")

FIELDS = {
    "alm_asset": (
        "sys_id,sys_updated_on,asset_tag,serial_number,model,model_category,install_status,substatus,"
        "location,location.u_site_code,company,install_date,warranty_expiration,quantity,comments"
    ),
    "wm_order": (
        "sys_id,sys_updated_on,number,short_description,state,priority,company,location,location.u_site_code,"
        "asset.asset_tag,opened_at,expected_start,closed_at,correlation_id,u_work_type,u_model_required,u_quantity"
    ),
    "wm_task": (
        "sys_id,sys_updated_on,number,parent.number,parent.correlation_id,parent.asset.asset_tag,state,assigned_to,"
        "assigned_to.user_name,asset.asset_tag,expected_start,actual_work_start,actual_work_end,work_duration,"
        "closed_at,close_code"
    ),
}


def value(rec: dict, name: str) -> str:
    v = rec.get(name)
    return (v.get("value") if isinstance(v, dict) else v) or ""


def display(rec: dict, name: str) -> str:
    v = rec.get(name)
    return (v.get("display_value") if isinstance(v, dict) else v) or ""


def sn_utc(v: str) -> str | None:
    """'2026-09-30 14:05:11' (instance time, UTC) → '2026-09-30T14:05:11Z'."""
    return v.replace(" ", "T") + "Z" if v else None


def changed(v: str) -> str | None:
    """sys_updated_on → the delta cursor, ISO 8601 UTC."""
    return datetime.strptime(v, "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC).isoformat() if v else None


def cursor(iso: str) -> str:
    return datetime.fromisoformat(iso).astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S")


def hours(duration: str) -> float | None:
    """'1970-01-01 02:30:00' → 2.5."""
    m = re.match(r"^1970-01-(\d\d) (\d+):(\d\d):(\d\d)$", duration or "")
    if not m:
        return None
    return round(((int(m[1]) - 1) * 86400 + int(m[2]) * 3600 + int(m[3]) * 60 + int(m[4])) / 3600, 2)


class ServiceNowAdapter(Adapter):
    source_id = "fsm"

    def auth(self, conn=None, secret=None):  # noqa: ARG002 - conn: the Adapter interface
        return OAuthClientCredentials(
            "/servicenow/oauth_token.do", "circularity-di", secret or "circularity-demo-sn-secret", form=True
        )

    def resources(self):
        return [
            Resource("alm_asset", self.read_assets),
            Resource("wm_order", self.read_orders),
            Resource("wm_task", self.read_tasks),
        ]

    # ------------------------------------------------------------- reading
    def _table(self, client: SourceClient, table: str, since: str | None) -> Iterator[Record]:
        query = (f"sys_updated_on>{cursor(since)}^" if since else "") + "ORDERBYsys_updated_on"
        params = {
            "sysparm_query": query,
            "sysparm_fields": FIELDS[table],
            "sysparm_display_value": "all",
            "sysparm_exclude_reference_link": "true",
            "sysparm_limit": PAGE,
        }
        offset = 0
        while True:
            r = client.request("GET", f"{API}/{table}", params=params | {"sysparm_offset": offset})
            rows = r.json()["result"]
            client.note_records(len(rows))
            for row in rows:
                yield Record(table, value(row, "sys_id"), row, str(r.request.url), changed(value(row, "sys_updated_on")))
            if len(rows) < PAGE:
                return
            offset += PAGE

    def read_assets(self, client, since):
        return self._table(client, "alm_asset", since)

    def read_orders(self, client, since):
        return self._table(client, "wm_order", since)

    def read_tasks(self, client, since):
        return self._table(client, "wm_task", since)

    # ------------------------------------------------------------- mapping
    def map(self, record: Record) -> list[Fact]:
        fn = {"alm_asset": self._asset, "wm_order": self._order, "wm_task": self._task}.get(record.resource)
        return fn(record.payload) if fn else []

    def _asset(self, p: dict) -> list[Fact]:
        tag = value(p, "asset_tag")
        if not tag:
            return []

        def a(field, v, sf, sv, transform="Pass-through"):
            return Fact("asset", tag, field, v, sf, sv, transform)

        facts = [
            a(
                "install_status",
                display(p, "install_status"),
                "alm_asset.install_status",
                value(p, "install_status"),
                "Choice label",
            ),
            a("model", display(p, "model") or None, "alm_asset.model", display(p, "model") or None),
        ]
        serial = value(p, "serial_number")
        if serial:
            facts += [
                a("source_refs", [f"FSM:{serial}"], "alm_asset.serial_number", serial, "Prefixed with system"),
                a("serial_number", serial, "alm_asset.serial_number", serial),
            ]
        if value(p, "substatus"):
            facts.append(a("substatus", value(p, "substatus"), "alm_asset.substatus", value(p, "substatus")))
        if value(p, "install_status") == "1" and value(p, "location.u_site_code"):
            site = value(p, "location.u_site_code")
            facts.append(a("installed_site", site, "alm_asset.location", display(p, "location"), "Location → site code"))
        if value(p, "install_date"):
            v = value(p, "install_date")
            facts.append(a("install_date", v[:10], "alm_asset.install_date", v, "Date to ISO"))
        if value(p, "warranty_expiration"):
            v = value(p, "warranty_expiration")
            facts.append(a("warranty_expiration", v, "alm_asset.warranty_expiration", v, "ISO date"))
        m = CASE_IN_COMMENT.search(value(p, "comments"))
        if m:
            facts.append(a("case_ref", m[1], "alm_asset.comments", value(p, "comments"), "Case reference from comments"))
        return facts

    def _order(self, p: dict) -> list[Fact]:
        num = value(p, "number")
        tag = value(p, "asset.asset_tag")
        state, state_label = value(p, "state"), display(p, "state")
        if tag:  # service history or removal of a unit
            return [
                Fact("asset", tag, "work_order_ref", num, "wm_order.number", num, "Pass-through"),
                Fact("asset", tag, "work_order_state", state_label, "wm_order.state", state, "Choice label"),
                Fact("asset", tag, "work_order_type", value(p, "u_work_type"), "wm_order.u_work_type", value(p, "u_work_type")),
            ]
        corr = value(p, "correlation_id")
        key = corr or num
        site = value(p, "location.u_site_code")
        due = sn_utc(value(p, "expected_start"))
        qty = int(value(p, "u_quantity")) if value(p, "u_quantity") else None

        def d(field, v, sf, sv, transform="Pass-through"):
            return Fact("demand", key, field, v, sf, sv, transform)

        summary = {
            "work_order": num,
            "work_type": value(p, "u_work_type") or None,
            "state": state_label,
            "site": site or None,
            "due": due,
            "qty": qty,
        }
        facts = [
            d("service_demand", summary, "wm_order.number", num, "Work order summarised"),
            d("service_order_ref", num, "wm_order.number", num),
            d("service_state", state_label, "wm_order.state", state, "Choice label"),
            d("service_due", due, "wm_order.expected_start", value(p, "expected_start"), "Local time → UTC"),
        ]
        if site:
            facts.append(d("ship_to_site", site, "wm_order.location", display(p, "location"), "Location → site code"))
        if display(p, "company"):
            facts.append(d("buyer", display(p, "company"), "wm_order.company", display(p, "company"), "Company name"))
        if qty is not None:
            facts.append(d("qty", qty, "wm_order.u_quantity", value(p, "u_quantity"), "Integer"))
        if corr:
            facts.append(d("order_ref", corr, "wm_order.correlation_id", corr))
        return facts

    def _task(self, p: dict) -> list[Fact]:
        num, state, state_label = value(p, "number"), value(p, "state"), display(p, "state")
        tag = value(p, "asset.asset_tag") or value(p, "parent.asset.asset_tag")
        if tag:
            if state not in TASK_AVAILABILITY:
                return []  # an open visit says nothing yet about the unit
            facts = [
                Fact(
                    "asset",
                    tag,
                    "availability",
                    TASK_AVAILABILITY[state],
                    "wm_task.state",
                    state,
                    f"State map: {state} → {TASK_AVAILABILITY[state]}",
                ),
                Fact("asset", tag, "last_visit_ref", num, "wm_task.number", num, "Pass-through"),
            ]
            if value(p, "closed_at"):
                v = value(p, "closed_at")
                facts.append(Fact("condition", tag, "service_date", sn_utc(v), "wm_task.closed_at", v, "Local time → UTC"))
            if value(p, "close_code"):
                facts.append(
                    Fact(
                        "condition",
                        tag,
                        "service_outcome",
                        value(p, "close_code"),
                        "wm_task.close_code",
                        value(p, "close_code"),
                        "Pass-through",
                    )
                )
            h = hours(value(p, "work_duration"))
            if h is not None:
                facts.append(
                    Fact(
                        "condition",
                        tag,
                        "service_hours",
                        h,
                        "wm_task.work_duration",
                        value(p, "work_duration"),
                        "Duration → hours",
                    )
                )
            return facts
        parent = value(p, "parent.number")
        if not parent:
            return []
        key = value(p, "parent.correlation_id") or parent
        facts = [
            Fact("demand", key, "dispatch_status", state_label, "wm_task.state", state, "Choice label"),
            Fact("demand", key, "dispatch_task_ref", num, "wm_task.number", num, "Pass-through"),
        ]
        tech = value(p, "assigned_to.user_name")
        facts.append(
            Fact(
                "demand",
                key,
                "dispatch_tech",
                tech or None,
                "wm_task.assigned_to",
                display(p, "assigned_to") or None,
                "User name",
            )
        )
        return facts


ADAPTER = ServiceNowAdapter()
