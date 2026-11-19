"""ServiceNow Field Service Management mock (demo source `fsm`, schema `servicenow`; docs/BACKEND_STEPS.md, B5).

Base path /servicenow/api/now (the Table API); OAuth at /servicenow/oauth_token.do. See api.py for the surface,
seed.py for the data and schema.py for the tables.

Demo credentials (constants in auth.py; nothing real is protected):
    Basic auth          di.integration / Circularity-demo-sn-1   (also admin / Circularity-demo-sn-admin)
    OAuth client        client_id circularity-di, client_secret circularity-demo-sn-secret
                        grant_type=client_credentials (runs as di.integration), password, refresh_token
"""

from sim.mock import Mock
from sim.vendors.servicenow.api import router
from sim.vendors.servicenow.seed import ensure, reset

MOCK = Mock("fsm", router, ensure, reset, "ServiceNow Field Service Management")
