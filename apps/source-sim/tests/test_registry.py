from sim.registry import SYSTEMS

# SOURCES[].id from index.html: every demo source has exactly one mock
DEMO_SOURCE_IDS = {
    "crm", "lease", "erp", "oms", "proc", "eam", "fsm", "plm", "bom", "qms", "eng",
    "wms", "tms", "rl", "insp", "repair", "iot", "mkt", "dlr", "rcy", "esg",
}


def test_every_demo_source_is_mocked_once():
    ids = [s.source_id for s in SYSTEMS]
    assert len(ids) == len(set(ids))
    assert set(ids) == DEMO_SOURCE_IDS


def test_only_erp_and_procurement_are_sap():
    sap = {s.source_id for s in SYSTEMS if s.style.startswith("sap")}
    assert sap == {"erp", "proc"}


def test_schemas_are_unique_identifiers():
    schemas = [s.schema for s in SYSTEMS]
    assert len(schemas) == len(set(schemas))
    assert all(s.isidentifier() and s.islower() for s in schemas)
