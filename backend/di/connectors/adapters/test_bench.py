"""Test bench (tn_bench, plan 9 P9-10.3): the bench results of returned telecom network equipment. Read only.

Written against source-sim's synthetic bench mock (source-sim/sim/vendors/test_bench): no real bench system is connected.
API key in `x-api-key`; offset paging (`results`, `next`). The mock has no change stamps, so the one resource is read in
full (Resource.delta False). Nothing is ever written to the source here (its three write routes are for later tasks).

Not one of the demo's 21 sources: it starts unregistered (no source_system row), so every demo screen and count is
unchanged. di.connectors.extra registers it and source.reconnect connects it. It implements no registry entry of its own:
it fills the canonical model `condition` for a unit, keyed by the source's org unit (schema.serial_key), and `asset.weight_kg`.

Resource and facts (the source's camelCase fields in snake case)
    results   condition.<serial key>   bench_passed, bench_total (tests), firmware, firmware_latest, firmware_major_gap
                                       (latest major version minus the unit's), wipe_status (verified | failed | none),
                                       wipe_attempts, wipe_scope (list), wipe_certificate_ref, wipe_verified_at, boards
                                       (list of {boardId, partNumber, health}), battery_chemistry, battery_damaged
              asset.<serial key>       weight_kg
A fact the source left empty (no certificate on a failed wipe, no battery on a router) is not written.
"""

from collections.abc import Iterator
from typing import Any

from sqlalchemy import text

from di.connectors.base import Record, Resource
from di.connectors.generic import GenericAdapter, keep
from di.connectors.http import SourceClient
from di.services.canonical.schema import serial_key
from di.services.canonical.store import Fact


def _org(client: SourceClient) -> str | None:
    """The org unit the source is bound to (None: shared)."""
    return client.session.execute(text("SELECT org_unit_id FROM source_system WHERE id = :i"), {"i": client.source_id}).scalar()


def _major(version: Any) -> int | None:
    """The major number of a firmware version (`5.2` is 5), None when the source gave none or a non-numeric one."""
    head = str(version or "").split(".")[0]
    return int(head) if head.isdigit() else None


def major_gap(firmware: Any, latest: Any) -> int | None:
    unit, newest = _major(firmware), _major(latest)
    return None if unit is None or newest is None else max(newest - unit, 0)


class TestBenchAdapter(GenericAdapter):
    __test__ = False  # not a pytest class, whatever the name says

    source_id = "tn_bench"
    base_path = "/test-bench/api"
    auth_kind = "api_key"
    api_key_header = "x-api-key"
    items_key = "results"
    provisioned = False  # no demo source: registered and connected by a person (di.connectors.extra)
    extra = True
    vendor = "Test bench (synthetic)"
    source_type = "test_bench"
    interval = 60
    owner = "Integration Engineering"

    def resources(self):
        def results(client: SourceClient, _since: str | None) -> Iterator[Record]:
            org = _org(client)
            for row, url in self.pages(client, "/results"):
                yield Record("results", str(row["serial"]), row | {"org_unit_id": org}, url)

        return [Resource("results", results, delta=False)]

    def map(self, record: Record) -> list[Fact]:
        p: dict[str, Any] = record.payload
        key = serial_key(p.get("org_unit_id"), p["serial"])
        tests, wipe, battery = p.get("tests") or {}, p.get("wipe") or {}, p.get("battery") or {}
        values = [  # (field, value, source field)
            ("bench_passed", tests.get("passed"), "tests.passed"),
            ("bench_total", tests.get("total"), "tests.total"),
            ("firmware", p.get("firmware"), "firmware"),
            ("firmware_latest", p.get("firmwareLatest"), "firmwareLatest"),
            ("firmware_major_gap", major_gap(p.get("firmware"), p.get("firmwareLatest")), "firmware, firmwareLatest"),
            ("wipe_status", wipe.get("status"), "wipe.status"),
            ("wipe_attempts", wipe.get("attempts"), "wipe.attempts"),
            ("wipe_scope", wipe.get("scope"), "wipe.scope"),
            ("wipe_certificate_ref", wipe.get("certificateRef"), "wipe.certificateRef"),
            ("wipe_verified_at", wipe.get("verifiedAt"), "wipe.verifiedAt"),
            ("boards", p.get("boards"), "boards"),
            ("battery_chemistry", battery.get("chemistry"), "battery.chemistry"),
            ("battery_damaged", battery.get("damaged"), "battery.damaged"),
        ]  # fmt: skip
        facts = [Fact("condition", key, f, v, src, v, "Nested field to flat fact") for f, v, src in values]
        weight = p.get("weightKg")
        facts.append(Fact("asset", key, "weight_kg", weight, "weightKg", weight, "Camel case to snake case"))
        return keep(facts)


ADAPTER = TestBenchAdapter()
