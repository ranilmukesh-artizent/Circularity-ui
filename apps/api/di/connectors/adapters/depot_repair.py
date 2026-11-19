"""Oracle Depot Repair (repair): receiving inspection and grade, teardown findings, repair orders, operations and hours,
parts, bench test results, release to service (the demo's SOURCES.repair).

Oracle E-Business Suite Integrated SOA Gateway REST under /depot-repair/webservices/rest, HTTP Basic with the EBS
user DI_CONNECTOR. Reads are GET calls of the query service xxcsdroquery (get_repair_orders, get_repair_tasks,
get_test_results) with P_START_INDEX / P_MAX_RECORDS paging until X_HAS_MORE = N; each answer is
{"OutputParameters": {"X_RETURN_STATUS": "S", "X_<NAME>": {"X_<NAME>_ITEM": [...]}}}. Delta reads pass
P_LAST_UPDATE_DATE_FROM = the newest LAST_UPDATE_DATE seen (Record.changed is the record's own stamp). Tasks and test
results are summarised per repair order: a delta read finds the changed rows, then re-reads all rows of those orders.

Facts (repair has authority over grade, inspection_ref, test_result, scope, cost, hours) — as before B5b:
    condition.<serial>     grade, inspection_ref (repair number), inspected_at, inspection_result, photo_count,
                           teardown_findings; test_result (pass / fail / not_run), bench_tests, tested_at
    intervention.<serial>  scope, process, cost (USD), predicted_condition, hours, repair_order_ref, repair_status,
                           repair_type, parts, parts_cost (USD from INR), labour_rate (USD), promise_date,
                           machine_hours, tasks, tasks_complete, released (release to service certificate)
    asset.<serial>         case_ref (ORIGINAL_SOURCE_REFERENCE), repair_order_ref
The demo's mapping (MAPPINGS.repair), for MTR-2041 (RO-61048): REPAIR_COST 1,800.00 USD → intervention.cost 1800
"Currency kept in USD"; SCOPE "Light repair + test" → intervention.process "light repair + test" "Process map";
RESULT_STATE B → intervention.predicted_condition B "Grade table v3". Changed by the real API: EBS returns upper-case
column names, so the source fields are REPAIR_COST, SCOPE, RESULT_STATE (the demo shows them in lower case).
"""

from collections.abc import Iterator
from decimal import Decimal

import httpx

from di.canonical.store import Fact
from di.connectors.base import Adapter, Record, Resource
from di.connectors.generic import utc
from di.connectors.http import Basic, SourceClient, SourceError

INR_PER_USD = Decimal("83.5")
RATE_NOTE = "Currency at 83.5 (rate dated 2026-10-06)"
QUERY = "/xxcsdroquery"
PAGE = 500


def usd(inr: Decimal) -> float:
    return float((inr / INR_PER_USD).quantize(Decimal("0.01")))


class DepotRepairAdapter(Adapter):
    source_id = "repair"
    base_path = "/depot-repair/webservices/rest"

    def auth(self):
        return Basic("DI_CONNECTOR", "repair-demo-password")

    def resources(self):
        return [
            Resource("repair_orders", self.read_orders),
            Resource("tasks", self.grouped("tasks", "get_repair_tasks", "X_REPAIR_TASKS")),
            Resource("test_results", self.grouped("test_results", "get_test_results", "X_TEST_RESULTS")),
        ]

    def pages(self, client: SourceClient, method: str, name: str, since: str | None, **params) -> Iterator[tuple[dict, str]]:
        start = 1
        while True:
            q = {**params, "P_START_INDEX": str(start), "P_MAX_RECORDS": str(PAGE)}
            if since:
                q["P_LAST_UPDATE_DATE_FROM"] = since
            path = f"{QUERY}/{method}/"
            out = client.get_json(path, params=q)["OutputParameters"]
            if out.get("X_RETURN_STATUS") != "S":
                raise SourceError("client", f"repair: {method} returned {out.get('X_RETURN_STATUS')}: {out.get('X_MSG_DATA')}")
            rows = (out.get(name) or {}).get(f"{name}_ITEM") or []
            client.note_records(len(rows))
            url = str(httpx.URL(client.url(path), params=q))
            for row in rows:
                yield row, url
            if out.get("X_HAS_MORE") != "Y" or not rows:
                return
            start += len(rows)

    def read_orders(self, client: SourceClient, since):
        for doc, url in self.pages(client, "get_repair_orders", "X_REPAIR_ORDERS", since):
            yield Record("repair_orders", doc["REPAIR_NUMBER"], doc, url, doc.get("LAST_UPDATE_DATE"))

    def grouped(self, resource: str, method: str, name: str):
        def read(client: SourceClient, since):
            rows = list(self.pages(client, method, name, since))
            groups: dict[str, list[dict]] = {}
            urls: dict[str, str] = {}
            if since is None:
                for doc, url in rows:
                    groups.setdefault(doc["REPAIR_NUMBER"], []).append(doc)
                    urls[doc["REPAIR_NUMBER"]] = url
            else:
                for rn in sorted({doc["REPAIR_NUMBER"] for doc, _ in rows}):
                    for doc, url in self.pages(client, method, name, None, P_REPAIR_NUMBER=rn):
                        groups.setdefault(rn, []).append(doc)
                        urls[rn] = url
            for rn, docs in groups.items():
                changed = max((d.get("LAST_UPDATE_DATE") or "" for d in docs), default="") or None
                payload = {"REPAIR_NUMBER": rn, "SERIAL_NUMBER": docs[0].get("SERIAL_NUMBER"), "items": docs}
                yield Record(resource, rn, payload, urls[rn], changed)

        return read

    # ------------------------------------------------------------------ mapping
    def map(self, record: Record) -> list[Fact]:
        p = record.payload
        key = p.get("SERIAL_NUMBER")
        if not key:
            return []
        out: list[Fact] = []

        def fact(model, field, value, sf, sv, transform):
            if value is not None:
                out.append(Fact(model, key, field, value, sf, sv, transform))

        if record.resource == "repair_orders":
            self._order(p, fact)
        elif record.resource == "tasks":
            tasks = sorted(p["items"], key=lambda t: t.get("OPERATION_SEQ_NUM") or 0)
            machine = sum(Decimal(str(t.get("PLANNED_HOURS") or 0)) for t in tasks if t.get("TASK_TYPE") == "Machine")
            fact("intervention", "machine_hours", float(machine), "PLANNED_HOURS", None, "Sum of machine operations")
            fact(
                "intervention",
                "tasks",
                [
                    {
                        "seq": t.get("OPERATION_SEQ_NUM"),
                        "description": t.get("DESCRIPTION"),
                        "type": t.get("TASK_TYPE"),
                        "planned_hours": t.get("PLANNED_HOURS"),
                        "status": t.get("STATUS"),
                    }
                    for t in tasks
                ],
                "X_REPAIR_TASKS",
                None,
                "Operations in sequence",
            )
            done = sum(1 for t in tasks if t.get("STATUS") == "COMPLETE")
            fact("intervention", "tasks_complete", f"{done}/{len(tasks)}", "STATUS", None, "Count of COMPLETE tasks")
        elif record.resource == "test_results":
            tests = sorted(p["items"], key=lambda t: (t.get("TEST_DATE") or "", t.get("TEST_RESULT_ID") or ""))
            final = [t for t in tests if t.get("PLAN_NAME") == "Final bench test"]
            tests = final or tests  # after a repair, the final bench test is the result that counts
            results = {t.get("RESULT") for t in tests}
            overall = "fail" if "FAIL" in results else "not_run" if "NOT_RUN" in results or not results else "pass"
            fact(
                "condition",
                "test_result",
                overall,
                "RESULT",
                ",".join(t.get("RESULT") or "" for t in tests),
                "Any FAIL → fail; any NOT_RUN → not_run",
            )
            fact(
                "condition",
                "bench_tests",
                [
                    {
                        "measurement": t.get("CHARACTERISTIC"),
                        "value": t.get("RESULT_VALUE"),
                        "unit": t.get("UOM"),
                        "limit": t.get("SPEC_LIMIT"),
                        "result": t.get("RESULT"),
                    }
                    for t in tests
                ],
                "X_TEST_RESULTS",
                None,
                "Measurements",
            )
            at = max((utc(t["TEST_DATE"]) for t in tests if t.get("TEST_DATE")), default=None)
            fact("condition", "tested_at", at, "TEST_DATE", None, "Latest test, timestamp to UTC")
        return out

    def _order(self, p: dict, fact) -> None:
        rn = p["REPAIR_NUMBER"]
        ri = p.get("RECEIVING_INSPECTION") or {}
        ref = p.get("ORIGINAL_SOURCE_REFERENCE")
        fact("asset", "case_ref", ref, "ORIGINAL_SOURCE_REFERENCE", ref, "Pass-through")
        fact("asset", "repair_order_ref", rn, "REPAIR_NUMBER", rn, "Pass-through")
        fact("condition", "grade", ri.get("GRADE"), "RECEIVING_INSPECTION.GRADE", ri.get("GRADE"), "Grade table v3")
        if ri.get("INSPECTED_AT"):
            fact("condition", "inspection_ref", rn, "REPAIR_NUMBER", rn, "Receiving inspection on the repair order")
            at = ri["INSPECTED_AT"]
            fact("condition", "inspected_at", utc(at), "RECEIVING_INSPECTION.INSPECTED_AT", at, "Timestamp to UTC")
            n = ri.get("PHOTO_COUNT")
            fact("condition", "photo_count", n, "RECEIVING_INSPECTION.PHOTO_COUNT", n, "Integer")
        fact("condition", "inspection_result", ri.get("RESULT"), "RECEIVING_INSPECTION.RESULT", ri.get("RESULT"), "Pass-through")
        findings = (p.get("TEARDOWN_FINDINGS") or {}).get("TEARDOWN_FINDINGS_ITEM") or []
        if findings:
            fact(
                "condition",
                "teardown_findings",
                [{"component": x.get("COMPONENT"), "status": x.get("STATUS"), "action": x.get("ACTION")} for x in findings],
                "TEARDOWN_FINDINGS",
                None,
                "Component findings",
            )
        scope = p.get("SCOPE")
        fact("intervention", "scope", scope, "SCOPE", scope, "Pass-through")
        fact("intervention", "process", scope.lower() if scope else None, "SCOPE", scope, "Process map")
        cost = p.get("REPAIR_COST")
        if cost is not None:
            cur = p.get("CURRENCY_CODE") or "USD"
            fact("intervention", "cost", float(cost), "REPAIR_COST", f"{cost:,.2f} {cur}", "Currency kept in USD")
        rs = p.get("RESULT_STATE")
        fact("intervention", "predicted_condition", rs, "RESULT_STATE", rs, "Grade table v3")
        lab = p.get("LABOUR") or {}
        if scope and lab.get("STANDARD_HOURS") is not None:
            h = lab["STANDARD_HOURS"]
            fact("intervention", "hours", h, "LABOUR.STANDARD_HOURS", h, "Standard hours")
        if lab.get("RATE") is not None:
            rate = Decimal(str(lab["RATE"]))
            fact(
                "intervention",
                "labour_rate",
                usd(rate),
                "LABOUR.RATE",
                f"{rate:.2f} {lab.get('CURRENCY_CODE') or 'INR'}/h",
                RATE_NOTE,
            )
        fact("intervention", "repair_order_ref", rn, "REPAIR_NUMBER", rn, "Pass-through")
        flow = p.get("FLOW_STATUS_CODE")
        fact("intervention", "repair_status", flow, "FLOW_STATUS_CODE", flow, "Pass-through")
        fact("intervention", "repair_type", p.get("REPAIR_TYPE"), "REPAIR_TYPE", p.get("REPAIR_TYPE"), "Pass-through")
        fact("intervention", "promise_date", p.get("PROMISE_DATE"), "PROMISE_DATE", p.get("PROMISE_DATE"), "Date")
        cert = (p.get("RELEASE_TO_SERVICE") or {}).get("CERTIFICATE")
        fact("intervention", "released", cert, "RELEASE_TO_SERVICE.CERTIFICATE", cert, "Release to service")
        parts = (p.get("PARTS") or {}).get("PARTS_ITEM") or []
        if parts:
            inr = sum(Decimal(str(x["UNIT_PRICE"])) * Decimal(str(x["QUANTITY"])) for x in parts)
            fact(
                "intervention",
                "parts",
                [{"part_number": x["PART_NUMBER"], "description": x["DESCRIPTION"], "quantity": x["QUANTITY"]} for x in parts],
                "PARTS",
                None,
                "Part list",
            )
            fact("intervention", "parts_cost", usd(inr), "PARTS[].UNIT_PRICE", f"{inr:.2f} INR", RATE_NOTE)


ADAPTER = DepotRepairAdapter()
