"""Safety recall register (recall, plan 9 P9-3.2): the recall notices of the tool fleet. Read only.

Written against source-sim's synthetic recall mock (source-sim/sim/generic/specs/recall_register.py): no real register
is connected. API key in `x-api-key`; offset paging (`items`, `next`, `total`); `?updated_since=` delta reads.

Not one of the demo's 21 sources: it starts unregistered (no source_system row), so every demo screen and count is
unchanged. di.connectors.extra registers it and source.reconnect connects it. It implements no registry entry of its
own: it fills the canonical model `recall`, which the tool-fleet pack's recall gate (GR-12) reads. Nothing is ever
written to the source.

Resources and facts (snake case of the source's camelCase fields)
    notices   recall.<recallId>   recall_id, tool_class, model, serial_from, serial_to, remedy, affected_parts, status,
                                  published_at
"""

from collections.abc import Iterator

from di.connectors.base import Record, Resource
from di.connectors.generic import GenericAdapter, keep
from di.connectors.http import SourceClient
from di.services.canonical.store import Fact

NOTICE = {
    "recallId": "recall_id", "toolClass": "tool_class", "model": "model", "serialFrom": "serial_from",
    "serialTo": "serial_to", "remedy": "remedy", "affectedParts": "affected_parts", "status": "status",
    "publishedAt": "published_at",
}  # fmt: skip


class RecallRegisterAdapter(GenericAdapter):
    source_id = "recall"
    base_path = "/recalls/api"
    auth_kind = "api_key"
    api_key_header = "x-api-key"
    provisioned = False  # no demo source: registered and connected by a person (di.connectors.extra)
    extra = True
    vendor = "Safety recall register (synthetic)"
    source_type = "recall"
    interval = 60
    owner = "Integration Engineering"

    def resources(self):
        def notices(client: SourceClient, since: str | None) -> Iterator[Record]:
            return self.flat(client, "notices", "/notices", "recallId", since)

        return [Resource("notices", notices)]

    def map(self, record: Record) -> list[Fact]:
        p = record.payload
        key = p["recallId"]
        facts = [Fact("recall", key, to, p.get(src), src, p.get(src), "Camel case to snake case") for src, to in NOTICE.items()]
        return keep(facts)


ADAPTER = RecallRegisterAdapter()
