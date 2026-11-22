"""IBM Maximo Manage 8.11 mock (docs/backend-steps.md, B5): the demo's EAM source (SOURCES.eam).

REST/OSLC JSON API under /maximo/api (see routes.py): object structures mxasset, mxwo, mxfailurereport.
Data in Postgres schema `maximo` (models.py), seeded from the world (seed.py).

Demo credentials (constants in auth.py):
    apikey header:   circularity-demo-maximo-apikey   (user MXINTADM)
    maxauth header:  base64("MXINTADM:circularity-demo-1")
"""

from sim.core.mock import Mock
from sim.vendors.maximo.routes import router
from sim.vendors.maximo.seed import ensure, reset

MOCK = Mock("eam", router, ensure, reset, "IBM Maximo")
