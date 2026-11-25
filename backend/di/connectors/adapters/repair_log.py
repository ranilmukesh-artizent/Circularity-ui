"""Legacy depot repair log (repairlog, plan 9 P9-3.1): the depot's own repair orders and teardown verdicts. Read only.

Written against source-sim's synthetic repair log mock (source-sim/sim/generic/specs/repair_log.py): no real system is
connected. It is not Oracle Depot Repair (source `repair`, a demo source). HTTP Basic; page paging (`?page=&page_size=`,
body `items`, `next`, `total`); `?updated_since=` delta reads.

Not one of the demo's 21 sources: it starts unregistered, so every demo screen and count is unchanged
(di.connectors.extra registers it, source.reconnect connects it). It fills the canonical models `condition` (the grade
of a tool) and `repair_event` that the tool-fleet pack's remaining-life and repair-cost work reads.

Resources and facts
    orders      condition.<serial>       grade, test_result, inspection_ref (the repair order id), graded_at; only for an
                                         order that has been graded (an open order has no grade yet)
                repair_event.<roId>      event_id, ro_id, kind `repair_order`, and every order field; `components` keeps the
                                         list of {name, replaced, runHoursAtReplacement}
    teardowns   repair_event.<tdId>      event_id, td_id, kind `teardown`, serial, tool_class, component, run_hours,
                                         verdict, observed_at
`condition.grade` has Oracle Depot Repair as its authority (schema.FIELD_AUTHORITY): when it also grades the same
serial, a different grade opens a conflict naming `repair`. No tool serial exists in Depot Repair, so none opens.
"""

from collections.abc import Iterator

from di.connectors.base import Record, Resource
from di.connectors.generic import GenericAdapter, keep
from di.connectors.http import SourceClient
from di.services.canonical.store import Fact

ORDER = {
    "serial": "serial", "toolClass": "tool_class", "market": "market", "ageMonths": "age_months", "faultCode": "fault_code",
    "grade": "grade", "testResult": "test_result", "gradedAt": "graded_at", "components": "components",
    "labourHours": "labour_hours", "partsCost": "parts_cost", "labourRate": "labour_rate", "status": "status",
    "closedAt": "closed_at",
}  # fmt: skip
TEARDOWN = {
    "serial": "serial", "toolClass": "tool_class", "component": "component", "runHours": "run_hours", "verdict": "verdict",
    "observedAt": "observed_at",
}  # fmt: skip


class RepairLogAdapter(GenericAdapter):
    source_id = "repairlog"
    base_path = "/repairlog/api"
    auth_kind = "basic"
    next_param = "page"
    size_param = "page_size"
    provisioned = False  # no demo source: registered and connected by a person (di.connectors.extra)
    extra = True
    vendor = "Legacy depot repair log (synthetic)"
    source_type = "repairlog"
    interval = 60
    owner = "Integration Engineering"

    def resources(self):
        def orders(client: SourceClient, since: str | None) -> Iterator[Record]:
            return self.flat(client, "orders", "/repair-orders", "roId", since)

        def teardowns(client: SourceClient, since: str | None) -> Iterator[Record]:
            return self.flat(client, "teardowns", "/teardowns", "tdId", since)

        return [Resource("orders", orders), Resource("teardowns", teardowns)]

    def map(self, record: Record) -> list[Fact]:
        p = record.payload
        if record.resource == "teardowns":
            key = p["tdId"]
            head = [Fact("repair_event", key, "event_id", key, "tdId", key, "Pass-through"),
                    Fact("repair_event", key, "td_id", key, "tdId", key, "Pass-through"),
                    Fact("repair_event", key, "kind", "teardown", "tdId", key, "Teardown row")]  # fmt: skip
            return head + self._fields("repair_event", key, p, TEARDOWN)
        key, out = p["roId"], []
        if p.get("grade"):
            grade = {"grade": "grade", "testResult": "test_result", "roId": "inspection_ref", "gradedAt": "graded_at"}
            out += self._fields("condition", p["serial"], p, grade)
        out += [
            Fact("repair_event", key, "event_id", key, "roId", key, "Pass-through"),
            Fact("repair_event", key, "ro_id", key, "roId", key, "Pass-through"),
            Fact("repair_event", key, "kind", "repair_order", "roId", key, "Repair order row"),
        ]
        return out + self._fields("repair_event", key, p, ORDER)

    @staticmethod
    def _fields(model: str, key: str, doc: dict, names: dict[str, str]) -> list[Fact]:
        facts = [Fact(model, key, to, doc.get(src), src, doc.get(src), "Camel case to snake case") for src, to in names.items()]
        return keep(facts)


ADAPTER = RepairLogAdapter()
