"""SAP S/4HANA mock (docs/backend-steps.md, B3)."""

from sim.core.mock import Mock
from sim.vendors.s4 import routes, seed

MOCK = Mock("erp", routes.router, seed.ensure, seed.reset, "SAP S/4HANA")
