"""Oracle Depot Repair (repair): receiving inspection and grade, teardown findings, repair orders, operations and hours,
parts, bench test results (SOURCES.repair).

OAuth 2.0 client credentials; offset paging (?limit=&offset=, body {items, nextOffset, totalResults}); ?updated_since=
for delta reads. The demo's /repair-orders/{id}/tasks and /test-results are served as /repair-tasks and
/repair-test-results (?repair_number=). Tasks and test results are summarised per repair order: a delta read finds the
changed rows, then re-reads all rows of those repair orders.

Facts (repair has authority over grade, inspection_ref, test_result, scope, cost, hours)
    condition.<serial>     grade, inspection_ref (repair number), inspected_at, inspection_result, photo_count,
                           teardown_findings; test_result (pass / fail / not_run), bench_tests, tested_at
    intervention.<serial>  scope, process, cost (USD), predicted_condition, hours, repair_order_ref, repair_status,
                           repair_type, parts, parts_cost (USD from INR), labour_rate (USD), promise_date,
                           machine_hours, tasks, tasks_complete
    asset.<serial>         case_ref (return_reference), repair_order_ref
The demo's mapping (MAPPINGS.repair), reproduced for MTR-2041 (RO-61048): repair_cost 1,800.00 USD →
intervention.cost 1800 "Currency kept in USD"; scope "Light repair + test" → intervention.process
"light repair + test" "Process map"; result_state B → intervention.predicted_condition B "Grade table v3".
"""

from decimal import Decimal

from di.canonical.store import Fact
from di.connectors.base import Adapter, Record, Resource
from di.connectors.generic import generic_pages, source_clock, utc
from di.connectors.http import OAuthClientCredentials, SourceClient

INR_PER_USD = Decimal("83.5")
RATE_NOTE = "Currency at 83.5 (rate dated 2026-10-06)"


def usd(inr: Decimal) -> float:
    return float((inr / INR_PER_USD).quantize(Decimal("0.01")))


class DepotRepairAdapter(Adapter):
    source_id = "repair"
    base_path = "/depot-repair/webservices/rest/csd"

    def auth(self):
        return OAuthClientCredentials("/oauth/token", "di-connector", "repair-demo-secret")

    def resources(self):
        return [
            Resource("repair_orders", self.read_orders),
            Resource("tasks", self.grouped("tasks", "/repair-tasks")),
            Resource("test_results", self.grouped("test_results", "/repair-test-results")),
        ]

    def _pages(self, client, path, since, params=None):
        return generic_pages(
            client,
            path,
            since,
            items_key="items",
            next_key="nextOffset",
            next_param="offset",
            size_param="limit",
            params=params,
        )

    def read_orders(self, client: SourceClient, since):
        stamp = source_clock(client)
        for doc, url in self._pages(client, "/repair-orders", since):
            yield Record("repair_orders", doc["repair_number"], doc, url, stamp)

    def grouped(self, name: str, path: str):
        def read(client: SourceClient, since):
            stamp = source_clock(client)
            groups: dict[str, list[dict]] = {}
            urls: dict[str, str] = {}
            rows = list(self._pages(client, path, since))
            if since is None:
                for doc, url in rows:
                    groups.setdefault(doc["repair_number"], []).append(doc)
                    urls[doc["repair_number"]] = url
            else:
                for rn in sorted({doc["repair_number"] for doc, _ in rows}):
                    for doc, url in self._pages(client, path, None, {"repair_number": rn}):
                        groups.setdefault(rn, []).append(doc)
                        urls[rn] = url
            for rn, docs in groups.items():
                yield Record(name, rn, {"repair_number": rn, "serial": docs[0].get("serial"), name: docs}, urls[rn], stamp)

        return read

    # ------------------------------------------------------------------ mapping
    def map(self, record: Record) -> list[Fact]:
        p = record.payload
        key = p.get("serial")
        if not key:
            return []
        out: list[Fact] = []

        def fact(model, field, value, sf, sv, transform):
            if value is not None:
                out.append(Fact(model, key, field, value, sf, sv, transform))

        if record.resource == "repair_orders":
            rn = p["repair_number"]
            ri = p.get("receiving_inspection") or {}
            fact("asset", "case_ref", p.get("return_reference"), "return_reference", p.get("return_reference"), "Pass-through")
            fact("asset", "repair_order_ref", rn, "repair_number", rn, "Pass-through")
            fact("condition", "grade", ri.get("grade"), "receiving_inspection.grade", ri.get("grade"), "Grade table v3")
            if ri.get("inspected_at"):
                fact("condition", "inspection_ref", rn, "repair_number", rn, "Receiving inspection on the repair order")
                fact(
                    "condition",
                    "inspected_at",
                    utc(ri["inspected_at"]),
                    "receiving_inspection.inspected_at",
                    ri["inspected_at"],
                    "Timestamp to UTC",
                )
            fact(
                "condition",
                "inspection_result",
                ri.get("result"),
                "receiving_inspection.result",
                ri.get("result"),
                "Pass-through",
            )
            if ri.get("inspected_at"):
                fact(
                    "condition",
                    "photo_count",
                    ri.get("photo_count"),
                    "receiving_inspection.photo_count",
                    ri.get("photo_count"),
                    "Integer",
                )
            if p.get("teardown_findings"):
                fact("condition", "teardown_findings", p["teardown_findings"], "teardown_findings", None, "Component findings")
            scope = p.get("scope")
            fact("intervention", "scope", scope, "scope", scope, "Pass-through")
            fact("intervention", "process", scope.lower() if scope else None, "scope", scope, "Process map")
            cost = p.get("repair_cost")
            if cost is not None:
                cur = p.get("repair_cost_currency") or "USD"
                fact("intervention", "cost", float(cost), "repair_cost", f"{cost:,.2f} {cur}", "Currency kept in USD")
            rs = p.get("result_state")
            fact("intervention", "predicted_condition", rs, "result_state", rs, "Grade table v3")
            lab = p.get("labour") or {}
            if scope and lab.get("standard_hours") is not None:
                fact(
                    "intervention",
                    "hours",
                    lab["standard_hours"],
                    "labour.standard_hours",
                    lab["standard_hours"],
                    "Standard hours",
                )
            if lab.get("rate") is not None:
                rate = Decimal(str(lab["rate"]))
                fact(
                    "intervention",
                    "labour_rate",
                    usd(rate),
                    "labour.rate",
                    f"{rate:.2f} {lab.get('currency_code') or 'INR'}/h",
                    RATE_NOTE,
                )
            fact("intervention", "repair_order_ref", rn, "repair_number", rn, "Pass-through")
            fact("intervention", "repair_status", p.get("flow_status"), "flow_status", p.get("flow_status"), "Pass-through")
            fact("intervention", "repair_type", p.get("repair_type"), "repair_type", p.get("repair_type"), "Pass-through")
            fact("intervention", "promise_date", p.get("promise_date"), "promise_date", p.get("promise_date"), "Date")
            parts = p.get("parts") or []
            if parts:
                inr = sum(Decimal(str(x["unit_price"])) * Decimal(str(x["quantity"])) for x in parts)
                fact(
                    "intervention",
                    "parts",
                    [
                        {"part_number": x["part_number"], "description": x["description"], "quantity": x["quantity"]}
                        for x in parts
                    ],
                    "parts",
                    None,
                    "Part list",
                )
                fact("intervention", "parts_cost", usd(inr), "parts[].unit_price", f"{inr:.2f} INR", RATE_NOTE)
        elif record.resource == "tasks":
            tasks = sorted(p["tasks"], key=lambda t: t.get("operation_seq") or 0)
            machine = sum(Decimal(str(t.get("planned_hours") or 0)) for t in tasks if t.get("task_type") == "Machine")
            fact("intervention", "machine_hours", float(machine), "planned_hours", None, "Sum of machine operations")
            fact(
                "intervention",
                "tasks",
                [
                    {
                        "seq": t.get("operation_seq"),
                        "description": t.get("description"),
                        "type": t.get("task_type"),
                        "planned_hours": t.get("planned_hours"),
                        "status": t.get("status"),
                    }
                    for t in tasks
                ],
                "tasks",
                None,
                "Operations in sequence",
            )
            done = sum(1 for t in tasks if t.get("status") == "COMPLETE")
            fact("intervention", "tasks_complete", f"{done}/{len(tasks)}", "status", None, "Count of COMPLETE tasks")
        elif record.resource == "test_results":
            tests = sorted(p["test_results"], key=lambda t: t.get("test_result_id") or "")
            results = {t.get("result") for t in tests}
            overall = "fail" if "FAIL" in results else "not_run" if "NOT_RUN" in results or not results else "pass"
            fact(
                "condition",
                "test_result",
                overall,
                "result",
                ",".join(t.get("result") or "" for t in tests),
                "Any FAIL → fail; any NOT_RUN → not_run",
            )
            fact(
                "condition",
                "bench_tests",
                [{k: t.get(k) for k in ("measurement", "value", "unit", "limit", "result")} for t in tests],
                "test_results",
                None,
                "Measurements",
            )
            at = max((utc(t["tested_at"]) for t in tests if t.get("tested_at")), default=None)
            fact("condition", "tested_at", at, "tested_at", None, "Latest test, timestamp to UTC")
        return out


ADAPTER = DepotRepairAdapter()
