"""Decontamination log (mr_decon, plan 9 P9-11.3): the cleaning cycles of the medical-device rental company. Read only.

Written against source-sim's synthetic decontamination log mock (source-sim/sim/vendors/decon_log): no real log is
connected. API key in `x-api-key`; a plain JSON array, oldest end first (no paging, so the resource is read in full:
Resource.delta False; a later cycle of the same device is read after an earlier one and its facts replace them).

Not one of the demo's 21 sources: it starts unregistered (no source_system row), so every demo screen and count is
unchanged. di.connectors.extra registers it and source.reconnect connects it. It implements no registry entry of its
own: it fills the canonical model `condition` for a device, keyed by the source's org unit (schema.tag_key), which the
medical rental pack's decontamination gate reads. Nothing is ever written to the source.

Resource and facts (snake case of the source's camelCase fields)
    cycles   condition.<tag key>   decon_started_at (cycleStartedAt), decon_ended_at (cycleEndedAt), decon_record_ref
                                   (cycleId), decon_enhanced (enhanced), decon_result (result)
Two timestamps on purpose (MR-03): the gate uses `decon_ended_at`, the END of the cycle, never the start. `method` and
`operatorRef` (a code) stay in the raw record: no fact.
"""

from collections.abc import Iterator

from sqlalchemy import text

from di.connectors.base import Record, Resource
from di.connectors.generic import GenericAdapter, keep
from di.connectors.http import SourceClient
from di.services.canonical.schema import tag_key
from di.services.canonical.store import Fact

CONDITION = {
    "cycleStartedAt": "decon_started_at", "cycleEndedAt": "decon_ended_at", "cycleId": "decon_record_ref",
    "enhanced": "decon_enhanced", "result": "decon_result",
}  # fmt: skip


def _org(client: SourceClient) -> str | None:
    """The org unit the source is bound to (None: shared)."""
    return client.session.execute(text("SELECT org_unit_id FROM source_system WHERE id = :i"), {"i": client.source_id}).scalar()


class DeconLogAdapter(GenericAdapter):
    source_id = "mr_decon"
    base_path = "/decon-log/api"
    auth_kind = "api_key"
    api_key_header = "x-api-key"
    provisioned = False  # no demo source: registered and connected by a person (di.connectors.extra)
    extra = True
    vendor = "Decontamination log (synthetic)"
    source_type = "decontamination"
    interval = 60
    owner = "Integration Engineering"

    def resources(self):
        def cycles(client: SourceClient, _since: str | None) -> Iterator[Record]:
            org = _org(client)
            rows = client.get_json("/cycles")
            client.note_records(len(rows))
            url = client.url("/cycles")
            for c in rows:
                yield Record("cycles", str(c["cycleId"]), c | {"org_unit_id": org}, url)

        return [Resource("cycles", cycles, delta=False)]

    def map(self, record: Record) -> list[Fact]:
        p = record.payload
        key = tag_key(p.get("org_unit_id"), p["tag"])
        notes = {"cycleEndedAt": "The end of the cycle: what the decontamination gate uses"}
        facts = [
            Fact("condition", key, to, p.get(src), src, p.get(src), notes.get(src, "Camel case to snake case"))
            for src, to in CONDITION.items()
        ]
        return keep(facts)


ADAPTER = DeconLogAdapter()
