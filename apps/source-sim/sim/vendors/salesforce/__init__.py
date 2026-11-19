"""Salesforce Sales Cloud mock (source `crm`, schema `salesforce`; docs/BACKEND_STEPS.md, B5).

A vendor-faithful slice of the Salesforce REST API v59.0 under /salesforce: OAuth 2.0 (JWT bearer and client
credentials), SOQL queries with nextRecordsUrl paging, sObject describe, retrieve, create and patch (Task and
Opportunity), and Salesforce error arrays. The HTTP surface is described in api.py, the SOQL subset in soql.py,
the data and how it maps from the demo's world in seed.py.

Demo credentials (constants in auth.py; nothing real is protected):
    client_id (consumer key)   3MVG9circularity.demo.northfield.crm.connector
    client_secret              circularity-demo-salesforce-secret
    users (JWT sub)            integration@northfield.example (client credentials run as this user),
                               sales.ops@northfield.example
    JWT aud                    https://login.salesforce.com or https://test.salesforce.com
"""

from sim.mock import Mock
from sim.vendors.salesforce.api import router
from sim.vendors.salesforce.seed import ensure, reset

MOCK = Mock("crm", router, ensure, reset, "Salesforce Sales Cloud")
