"""PTC Windchill (plm_wc, plan 8 MVP-9.3): PLM parts and their structures, read only. No demo source.

Written against source-sim's Windchill mock (source-sim/sim/vendors/windchill, MVP-9.2), a synthetic stand-in: no real
Windchill is connected. Windchill REST Services, ProdMgmt domain (OData v4), HTTP Basic:
1. GET Parts, following `@odata.nextLink` (the server's paging) â†’ one `parts` record per part;
2. for every part, POST Parts('<ID>')/PTC.ProdMgmt.GetPartStructure â†’ one `structures` record per part that uses
   other parts (an assembly), with the state of each used part from step 1.
Neither resource has a change time, so both are read in full (Resource.delta False).

Not one of the demo's 21 sources: it starts unregistered, so every demo screen and count is unchanged (as AWS IoT
starts not provisioned). di.connectors.extra registers it (status disconnected, optionally bound to an org unit) and
source.reconnect connects it. A second instance (plm_wc_2, plm_wc_3 ...) reads with the same adapter
(registry.python_adapter â†’ instance()), bound to another org unit.

Facts, keyed per the source's org unit (schema.part_key, bom_key: two org units never collide)
    part.<org>:<Number>                       number, name, revision (Version; the provenance keeps Version.Iteration),
                                              state (released, in_work, obsolete), unit_cost, org_unit_id
    bom.<org>:<parent>@<revision>><child>     parent, child, qty, parent_revision, harvestable
ASSUMPTION: a used part is harvestable when it was released (Released or Obsolete); an In Work part is no spare part.
"""

import copy
from collections.abc import Iterator
from typing import Any
from urllib.parse import quote

from sqlalchemy import text

from di.connectors.base import Adapter, Record, Resource
from di.connectors.generic import keep
from di.connectors.http import Basic, SourceClient
from di.services.canonical.schema import bom_key, part_key
from di.services.canonical.store import Fact

PARTS = "/ProdMgmt/Parts"
STATES = {"RELEASED": "released", "INWORK": "in_work", "OBSOLETE": "obsolete"}
HARVESTABLE = {"RELEASED", "OBSOLETE"}


def _org(client: SourceClient) -> str | None:
    """The org unit the source is bound to (None: shared)."""
    return client.session.execute(text("SELECT org_unit_id FROM source_system WHERE id = :i"), {"i": client.source_id}).scalar()


class WindchillAdapter(Adapter):
    source_id = "plm_wc"
    base_path = "/Windchill/servlet/odata"
    provisioned = False  # no demo source: registered and connected by a person (di.connectors.extra)
    extra = True
    vendor = "PTC Windchill"
    source_type = "plm"
    interval = 60
    owner = "Integration Engineering"

    def instance(self, source_id: str) -> "WindchillAdapter":
        """The adapter of another Windchill instance (plm_wc_2 ...)."""
        a = copy.copy(self)
        a.source_id = source_id
        return a

    def auth(self, conn=None, secret=None):  # noqa: ARG002 - conn: the Adapter interface
        return Basic("di_connector", secret or "Circularity-demo-wc-1")

    def resources(self):
        return [Resource("parts", self.read_parts, delta=False), Resource("structures", self.read_structures, delta=False)]

    # ------------------------------------------------------------- reading
    def all_parts(self, client: SourceClient) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        url: str | None = PARTS
        while url:
            body = client.get_json(url)
            out += body["value"]
            client.note_records(len(body["value"]))
            url = body.get("@odata.nextLink")
        return out

    def read_parts(self, client: SourceClient, since: str | None) -> Iterator[Record]:  # noqa: ARG002 - always in full
        org = _org(client)
        for p in self.all_parts(client):
            yield Record("parts", p["ID"], p | {"org_unit_id": org}, client.url(PARTS))

    def read_structures(self, client: SourceClient, since: str | None) -> Iterator[Record]:  # noqa: ARG002 - in full
        org = _org(client)
        parts = self.all_parts(client)
        state = {p["Number"]: (p.get("State") or {}).get("Value") for p in parts}
        for p in parts:
            path = f"{PARTS}('{quote(p['ID'], safe=':.')}')/PTC.ProdMgmt.GetPartStructure"
            value = client.request("POST", path, json={}).json()["value"]
            uses = [u | {"State": state.get(u["Part"]["Number"])} for v in value for u in v.get("Uses") or []]
            if uses:
                payload = {"Number": p["Number"], "Version": p["Version"], "Uses": uses, "org_unit_id": org}
                yield Record("structures", p["ID"], payload, client.url(path))

    # ------------------------------------------------------------- mapping
    def map(self, record: Record) -> list[Fact]:
        p, org = record.payload, record.payload.get("org_unit_id")
        if record.resource == "structures":
            return [fact for u in p["Uses"] for fact in self._line(org, p, u)]
        key, st = part_key(org, p["Number"]), (p.get("State") or {}).get("Value")
        return keep(
            [
                Fact("part", key, "number", p["Number"], "Number", p["Number"], "Pass-through"),
                Fact("part", key, "name", p.get("Name"), "Name", p.get("Name"), "Pass-through"),
                Fact("part", key, "revision", p.get("Version"), "Version", f"{p.get('Version')}.{p.get('Iteration')}",
                     "Version without iteration"),
                Fact("part", key, "state", STATES.get(st or ""), "State", st, "Status map"),
                Fact("part", key, "unit_cost", p.get("UnitCost"), "UnitCost", p.get("UnitCost"), "Pass-through"),
                Fact("part", key, "org_unit_id", org, "source org unit", org, "Source binding"),
            ]
        )  # fmt: skip

    @staticmethod
    def _line(org: str | None, p: dict[str, Any], u: dict[str, Any]) -> list[Fact]:
        child, rev = u["Part"]["Number"], p["Version"]
        key = bom_key(org, p["Number"], rev, child)
        return keep(
            [
                Fact("bom", key, "parent", p["Number"], "Number", p["Number"], "Pass-through"),
                Fact("bom", key, "child", child, "Uses.Part.Number", child, "Pass-through"),
                Fact("bom", key, "qty", u.get("Quantity"), "Uses.Quantity", u.get("Quantity"), "Pass-through"),
                Fact("bom", key, "parent_revision", rev, "Version", rev, "Pass-through"),
                Fact("bom", key, "harvestable", u.get("State") in HARVESTABLE, "Uses.Part.State", u.get("State"),
                     "Released or obsolete â†’ harvestable"),
            ]
        )  # fmt: skip


ADAPTER = WindchillAdapter()
