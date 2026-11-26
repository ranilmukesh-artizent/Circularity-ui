"""Core returns system (core_ret, plan 9 P9-12.8): the automotive cores dealers send back, their inspection checks and the
dealers' return history. Read only.

Written against source-sim's synthetic core returns mock (source-sim/sim/vendors/core_returns): no real core program is
connected. API key in `x-api-key`; two unpaged lists, read in full (Resource.delta False).

Not one of the demo's 21 sources: it starts unregistered (di.connectors.extra registers it). It fills the canonical models the
automotive cores pack reads (`auto_core`: the acceptance gate CORE-ACCEPT and the X-15 fraud rules); nothing is written to it.

Resource and facts, keyed by the source's org unit (schema.serial_key) and the core id
    cores   asset.declared_part_number (declaredPartNumber), asset.observed_part_number (observedPartNumber),
            asset.dealer_id (dealerId), market.core_deposit (deposit), condition.core_checks (checks, whole),
            condition.dealer_rejects (from /dealer-history: `{"30": n, "90": n}`, the dealer's rejected returns in the 30 and 90
            days before the core was received, this core not counted)
ASSUMPTION: the windows are counted back from the core's `receivedAt`, not from the clock, so a sync of an old core does not
change its count.
"""

from collections.abc import Iterator
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import text

from di.connectors.base import Record, Resource
from di.connectors.generic import GenericAdapter, keep
from di.connectors.http import SourceClient
from di.services.canonical.schema import serial_key
from di.services.canonical.store import Fact

FIELDS = (  # (model, canonical field, source field, note)
    ("asset", "declared_part_number", "declaredPartNumber", "The part number the dealer declared"),
    ("asset", "observed_part_number", "observedPartNumber", "The part number seen at inspection"),
    ("asset", "dealer_id", "dealerId", "The returning dealer (a code)"),
    ("market", "core_deposit", "deposit", "The deposit paid on the core"),
    ("condition", "core_checks", "checks", "The inspection checks, whole"),
    ("condition", "dealer_rejects", "dealerRejects", "Rejected returns of the dealer before this core, by window in days"),
)

WINDOWS = (30, 90)  # days the dealer's rejects are counted in


def parse_time(v: Any) -> datetime | None:
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except ValueError:
        return None


def _org(client: SourceClient) -> str | None:
    """The org unit the source is bound to (None: shared)."""
    return client.session.execute(text("SELECT org_unit_id FROM source_system WHERE id = :i"), {"i": client.source_id}).scalar()


def dealer_rejects(history: list[dict[str, Any]], core: dict[str, Any]) -> dict[str, int]:
    """`{"<days>": rejected returns of the core's dealer in that many days before the core was received}`."""
    at = parse_time(core.get("receivedAt"))
    out = {str(d): 0 for d in WINDOWS}
    if at is None:
        return out
    for e in history:
        when = parse_time(e.get("at"))
        if e.get("dealerId") != core.get("dealerId") or e.get("coreId") == core.get("coreId") or e.get("outcome") != "rejected":
            continue
        if when is not None and at - timedelta(days=max(WINDOWS)) <= when < at:
            for d in WINDOWS:
                out[str(d)] += when >= at - timedelta(days=d)
    return out


class CoreReturnsAdapter(GenericAdapter):
    source_id = "core_ret"
    base_path = "/core-returns/api"
    auth_kind = "api_key"
    api_key_header = "x-api-key"
    provisioned = False  # no demo source: registered and connected by a person (di.connectors.extra)
    extra = True
    vendor = "Core returns system (synthetic)"
    source_type = "core_returns"
    interval = 60
    owner = "Integration Engineering"

    def resources(self):
        def cores(client: SourceClient, _since: str | None) -> Iterator[Record]:
            org, url = _org(client), client.url("/cores")
            rows, history = client.get_json("/cores"), client.get_json("/dealer-history")
            client.note_records(len(rows))
            for c in rows:
                yield Record(
                    "cores", str(c["coreId"]), c | {"dealerRejects": dealer_rejects(history, c), "org_unit_id": org}, url
                )

        return [Resource("cores", cores, delta=False)]

    def map(self, record: Record) -> list[Fact]:
        p: dict[str, Any] = record.payload
        key = serial_key(p.get("org_unit_id"), p["coreId"])
        facts = [Fact(model, key, name, p.get(src), src, p.get(src), note) for model, name, src, note in FIELDS]
        return keep(facts)


ADAPTER = CoreReturnsAdapter()
