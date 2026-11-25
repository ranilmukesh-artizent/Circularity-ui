"""Connected-tool telematics (tooltel, plan 9 P9-3.2): run hours, load share, events and coverage per tool. Read only.

Written against source-sim's synthetic telematics mock (source-sim/sim/generic/specs/tool_telematics.py): no real
telematics service is connected. OAuth client credentials (bearer token); offset paging (`items`, `next`, `total`).

Not one of the demo's 21 sources: it starts unregistered, so every demo screen and count is unchanged (di.connectors.extra
registers it, source.reconnect connects it). It implements no registry entry of its own: it fills facts of the canonical
model `condition` that the tool-fleet pack's remaining-life work reads. A serial with no telematics has no document and
so no fact. Nothing is ever written to the source.

Resources and facts
    tools   condition.<serial>   run_hours, high_load_share, event_counts (`{overheat, drop, overload}`), telemetry_at
                                 (= lastSeen), telemetry_coverage_pct
"""

from collections.abc import Iterator

from di.connectors.base import Record, Resource
from di.connectors.generic import GenericAdapter, keep
from di.connectors.http import SourceClient
from di.services.canonical.store import Fact

TOOL = {
    "runHours": "run_hours", "highLoadShare": "high_load_share", "events": "event_counts", "lastSeen": "telemetry_at",
    "coveragePct": "telemetry_coverage_pct",
}  # fmt: skip


class ToolTelematicsAdapter(GenericAdapter):
    source_id = "tooltel"
    base_path = "/tooltel/v2"
    auth_kind = "oauth"
    provisioned = False  # no demo source: registered and connected by a person (di.connectors.extra)
    extra = True
    vendor = "Connected-tool telematics (synthetic)"
    source_type = "tooltel"
    interval = 60
    owner = "Integration Engineering"

    def resources(self):
        def tools(client: SourceClient, since: str | None) -> Iterator[Record]:
            return self.flat(client, "tools", "/tools", "serial", since)

        return [Resource("tools", tools)]

    def map(self, record: Record) -> list[Fact]:
        p = record.payload
        serial = p["serial"]
        facts = [
            Fact("condition", serial, to, p.get(src), src, p.get(src), "Camel case to snake case") for src, to in TOOL.items()
        ]
        return keep(facts)


ADAPTER = ToolTelematicsAdapter()
