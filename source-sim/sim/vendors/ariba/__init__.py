"""SAP Ariba mock (docs/backend-steps.md, B4)."""

from sim.core.mock import Mock
from sim.vendors.ariba import routes, seed

MOCK = Mock("proc", routes.router, seed.ensure, seed.reset, "SAP Ariba")
