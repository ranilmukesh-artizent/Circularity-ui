"""Asset management mock (plan 9, P9-11.2): the medical-device rental company's device register, synthetic.

Not a demo source: it is registered in sim/core/registry.py EXTRA_SYSTEMS (source id `mr_assets`, schema
`medical_asset_mgmt`), so the demo's 21 systems, its screens and its counts stay as they were. di reads it through its
adapter (backend/di/connectors/adapters/medical_asset_mgmt.py), which maps a device to `asset.*` facts and
`market.residual_sale_value`, keyed by device tag. It reads like an ordinary JSON API (camelCase); there is no real asset
system behind it.

    GET /asset-management/api/devices?deviceClass=   [{tag, serial, model, deviceClass, manufacturerCode, inServiceDate,
                                                        bookValue, residualSaleValue, hasPatientData}]
    GET /asset-management/api/devices/{tag}          one device

Auth: API key in `x-api-key` (demo key `mr_assets-demo-key`); 401 with an error body otherwise. Errors are
`{"error": {"code", "message"}}`. The list is a plain JSON array (80 devices, no paging).

Data in Postgres schema `medical_asset_mgmt` (models.py, seed.py): 80 devices, fixed (no randomness). Tags are
`SYN-MR-<class code>-<n>`: infusion pumps IP 1-50, patient monitors PM 1-8, electric beds EB 1-8, syringe drivers SD 1-6,
transport ventilators TV 1-4, pulse oximeters PO 1-4. `SYN-MR-IP-0001` is 3 years old (in service since 7 Oct 2023, the
demo's as-of date less three years) with book value 1,150 and residual sale value 1,100. Only patient monitors hold
patient data.

ASSUMPTION: the other devices' age, book value (a straight-line fall of 10 % of the class price a year) and residual sale
    value (90 % of book value) are computed from the tag's number, so a reset gives the same JSON again.
ASSUMPTION: no manufacturer name, only a code (`MFR-A` to `MFR-C`).
"""

from sim.core.mock import Mock
from sim.vendors.medical_asset_mgmt import routes, seed

MOCK = Mock("mr_assets", routes.router, seed.ensure, seed.reset, "Asset management (synthetic)")
