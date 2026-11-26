"""Decommission tracker (tn_decom, plan 9 P9-10.2): the removal jobs of a telecom operator's sites and the demand of sites
for equipment. Read only.

Written against source-sim's synthetic tracker mock (source-sim/sim/vendors/decommission_tracker): no real tracker is
connected. API key in `x-api-key`; the two lists are not paged and have no change stamps (Resource.delta False).

Not one of the demo's 21 sources: it starts unregistered, so every demo screen and count is unchanged.
di.connectors.extra registers it and source.reconnect connects it. It implements no registry entry of its own. The field
service app stays the existing `fsm` source; this tracker carries the removal jobs.

Resources and facts
    removal_jobs  asset.<serial key>      one record per removed unit (id `<jobId>:<serial>`): serial, model, removal_job
                                          (jobId), removed_at, programme. The unit's site is the inventory's fact, not this.
    site_demand   demand.<demandId>       site_demand: the whole demand document (object); no org unit in the key
"""

from collections.abc import Iterator
from typing import Any

from sqlalchemy import text

from di.connectors.base import Record, Resource
from di.connectors.generic import GenericAdapter, keep
from di.connectors.http import SourceClient
from di.services.canonical.schema import serial_key
from di.services.canonical.store import Fact

ASSET = {"serial": "serial", "model": "model", "jobId": "removal_job", "removedAt": "removed_at", "programme": "programme"}


def _org(client: SourceClient) -> str | None:
    """The org unit the source is bound to (None: shared)."""
    return client.session.execute(text("SELECT org_unit_id FROM source_system WHERE id = :i"), {"i": client.source_id}).scalar()


class DecommissionTrackerAdapter(GenericAdapter):
    source_id = "tn_decom"
    base_path = "/decommission/api/v2"
    auth_kind = "api_key"
    api_key_header = "x-api-key"
    provisioned = False  # no demo source: registered and connected by a person (di.connectors.extra)
    extra = True
    vendor = "Decommission tracker (synthetic)"
    source_type = "decommission_tracker"
    interval = 60
    owner = "Integration Engineering"

    def resources(self):
        def removal_jobs(client: SourceClient, _since: str | None) -> Iterator[Record]:
            org, url = _org(client), client.url("/removal-jobs")
            jobs = client.get_json("/removal-jobs")["jobs"]
            client.note_records(sum(len(j["units"]) for j in jobs))
            for j in jobs:
                for u in j["units"]:
                    payload = {
                        "jobId": j["jobId"], "siteId": u.get("siteId") or j["siteId"], "removedAt": j["removedAt"],
                        "programme": j["programme"], "serial": u["serial"], "model": u["model"], "org_unit_id": org,
                    }  # fmt: skip
                    yield Record("removal_jobs", f"{j['jobId']}:{u['serial']}", payload, url)

        def site_demand(client: SourceClient, _since: str | None) -> Iterator[Record]:
            rows = client.get_json("/site-demand")
            client.note_records(len(rows))
            for d in rows:
                yield Record("site_demand", str(d["demandId"]), d, client.url("/site-demand"))

        return [Resource("removal_jobs", removal_jobs, delta=False), Resource("site_demand", site_demand, delta=False)]

    def map(self, record: Record) -> list[Fact]:
        p: dict[str, Any] = record.payload
        if record.resource == "site_demand":
            return [Fact("demand", str(p["demandId"]), "site_demand", dict(p), "site-demand", p, "The demand document, whole")]
        key = serial_key(p.get("org_unit_id"), p["serial"])
        facts = [Fact("asset", key, to, p.get(src), src, p.get(src), "Camel case to snake case") for src, to in ASSET.items()]
        return keep(facts)


ADAPTER = DecommissionTrackerAdapter()
