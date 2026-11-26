"""Parts supplier portal mock (plan 9, P9-11.5): what a replacement part costs, how long it takes and what a harvested one is
worth, for the medical-device rental company's device models. Synthetic.

Not a demo source: it is registered in sim/core/registry.py EXTRA_SYSTEMS (source id `mr_parts`, schema `parts_portal`), so
the demo's 21 systems, its screens and its counts stay as they were. di reads it through its adapter
(backend/di/connectors/adapters/parts_portal.py), which maps the parts of a device model to `market.part_prices` and
`market.harvest_values`, keyed by the model. It reads like an ordinary JSON API (camelCase); no real supplier is behind it.

    GET /parts-portal/api/parts?model=   [{partNo, label, price, leadDays, harvestValue, model}]
                                          one device model's parts, or every model's without the parameter; 404 for an
                                          unknown model

Auth: API key in `x-api-key` (demo key `mr_parts-demo-key`); 401 with an error body otherwise. Errors are
`{"error": {"code", "message"}}`. The list is a plain JSON array (no paging).

Data in Postgres schema `parts_portal` (models.py, seed.py): the 8 device models of the asset management mock, 2 or 3 parts
each, fixed (no randomness). Both infusion pumps ("Synthetic Volumetric Pump V2" and "Synthetic Smart Pump S4") have a
pump motor at 240 (lead 5 days) and a controller at 310 (lead 9 days).

ASSUMPTION: the spec's `{partNo, label, price, leadDays, harvestValue}` gets a `model` field too, so a read without the
    parameter can be told apart per model.
ASSUMPTION: "pump motor 240, controller 310" are the new-part prices; a harvested part is worth 70 % of its price.
ASSUMPTION: the other models' parts and prices are invented (nothing in the spec); part numbers are `PRT-<model code>-<part>`.
"""

from sim.core.mock import Mock
from sim.vendors.parts_portal import routes, seed

MOCK = Mock("mr_parts", routes.router, seed.ensure, seed.reset, "Parts supplier portal (synthetic)")
