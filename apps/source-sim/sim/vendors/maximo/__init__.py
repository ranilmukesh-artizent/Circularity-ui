"""IBM Maximo Manage 8.11 mock (docs/BACKEND_STEPS.md, B5): the demo's EAM source (SOURCES.eam).

REST/OSLC JSON API under /maximo/api (see api.py): object structures mxasset, mxwo, mxfailurereport.
Data in Postgres schema `maximo` (tables.py), seeded from the world (seed.py).

Demo credentials (constants in auth.py):
    apikey header:   circularity-demo-maximo-apikey   (user MXINTADM)
    maxauth header:  base64("MXINTADM:circularity-demo-1")
"""

from sim.mock import Mock
from sim.vendors.maximo.api import router
from sim.vendors.maximo.seed import ensure, reset

MOCK = Mock("eam", router, ensure, reset, "IBM Maximo")
