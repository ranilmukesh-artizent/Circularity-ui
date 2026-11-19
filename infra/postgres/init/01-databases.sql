-- Runs once, when the Postgres volume is first created.
-- "di"      : the product database (Circularity / Recover). Filled only through the connectors.
-- "sources" : the mocked source systems (SAP S/4HANA, SAP Ariba and generic vendor mocks), one schema per system.
CREATE DATABASE di;
CREATE DATABASE sources;
