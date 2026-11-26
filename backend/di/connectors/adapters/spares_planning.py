"""Spares planning (tn_spares, plan 9 P9-10.4): the spares catalogue, stock targets, six-month need, spares pool and open
purchase requisitions of a telecom operator. Read only.

Written against source-sim's synthetic spares planning mock (source-sim/sim/vendors/spares_planning): no real planning
system is connected. API key in `x-api-key`; the five lists are not paged and have no change stamps (Resource.delta
False). The mock also takes `POST /requisitions/{reqId}/reduce` (idempotent on `Idempotency-Key`); this adapter never
calls it, a person's action would.

Not one of the demo's 21 sources: it starts unregistered, so every demo screen and count is unchanged.
di.connectors.extra registers it and source.reconnect connects it. It implements no registry entry of its own.

ASSUMPTION: the catalogue's `newPrice` stands in for the ERP purchase-order price (the demo's S/4HANA seed stays
untouched), so it fills `market.new_price`.

Resources and facts (keys carry the source's org unit, `shared` when it has none)
    catalogue     market.<org>:<model>          new_price, generation (the list price and the model's generation)
    targets       demand.<org>:<region>:<model> spares_target (target), use_probability (useProbability12m)
    forecast6m    demand.<org>:<region>:<model> need_6m (need)
    requisitions  demand.<org>:<region>:<model> requisitions: the open requisitions of the cell as a list (one record
                                                per cell, id `<region>:<model>`)
    stock         asset.<serial key>            idle_days (idleDays), with serial, part_number (model) and region
`failureRate12m` and the cell's `stock` count stay in the raw record: the pool's units are the stock.
"""

from collections.abc import Iterator
from typing import Any

from sqlalchemy import text

from di.connectors.base import Record, Resource
from di.connectors.generic import GenericAdapter, keep
from di.connectors.http import SourceClient
from di.services.canonical.schema import SHARED_ORG, serial_key
from di.services.canonical.store import Fact

CATALOGUE = (("newPrice", "new_price"), ("generation", "generation"))
CELL = {"targets": (("target", "spares_target"), ("useProbability12m", "use_probability")), "forecast6m": (("need", "need_6m"),)}
UNIT = (("idleDays", "idle_days"), ("serial", "serial"), ("model", "part_number"), ("region", "region"))


def _org(client: SourceClient) -> str | None:
    """The org unit the source is bound to (None: shared)."""
    return client.session.execute(text("SELECT org_unit_id FROM source_system WHERE id = :i"), {"i": client.source_id}).scalar()


class SparesPlanningAdapter(GenericAdapter):
    source_id = "tn_spares"
    base_path = "/spares-planning/api"
    auth_kind = "api_key"
    api_key_header = "x-api-key"
    provisioned = False  # no demo source: registered and connected by a person (di.connectors.extra)
    extra = True
    vendor = "Spares planning (synthetic)"
    source_type = "spares_planning"
    interval = 60
    owner = "Integration Engineering"

    def resources(self):
        def listing(name: str, id_of) -> Resource:
            def read(client: SourceClient, _since: str | None) -> Iterator[Record]:
                org, url = _org(client), client.url(f"/{name}")
                rows = client.get_json(f"/{name}")
                client.note_records(len(rows))
                for d in rows:
                    yield Record(name, id_of(d), d | {"org_unit_id": org}, url)

            return Resource(name, read, delta=False)

        def requisitions(client: SourceClient, _since: str | None) -> Iterator[Record]:
            org, url = _org(client), client.url("/requisitions")
            cells: dict[str, dict[str, Any]] = {}
            for r in client.get_json("/requisitions"):
                cell = cells.setdefault(
                    f"{r['region']}:{r['model']}",
                    {"region": r["region"], "model": r["model"], "requisitions": [], "org_unit_id": org},
                )
                cell["requisitions"].append({k: r[k] for k in ("reqId", "quantity", "status", "createdAt")})
            client.note_records(len(cells))
            for rid, cell in cells.items():
                yield Record("requisitions", rid, cell, url)

        cell_id = lambda d: f"{d['region']}:{d['model']}"  # noqa: E731
        return [
            listing("catalogue", lambda d: d["model"]),
            listing("targets", cell_id),
            listing("forecast6m", cell_id),
            Resource("requisitions", requisitions, delta=False),
            listing("stock", lambda d: d["serial"]),
        ]

    def map(self, record: Record) -> list[Fact]:
        p: dict[str, Any] = record.payload
        org = p.get("org_unit_id")
        pairs: tuple[tuple[str, str], ...]
        if record.resource == "catalogue":
            pairs, model, key = CATALOGUE, "market", f"{org or SHARED_ORG}:{p['model']}"
        elif record.resource == "stock":
            pairs, model, key = UNIT, "asset", serial_key(org, p["serial"])
        elif record.resource in CELL:
            pairs, model, key = CELL[record.resource], "demand", f"{org or SHARED_ORG}:{p['region']}:{p['model']}"
        elif record.resource == "requisitions":
            pairs, model, key = (("requisitions", "requisitions"),), "demand", f"{org or SHARED_ORG}:{p['region']}:{p['model']}"
        else:
            return []
        return keep([Fact(model, key, to, p.get(src), src, p.get(src), "Pass-through") for src, to in pairs])


ADAPTER = SparesPlanningAdapter()
