"""adapter registry, owner approvals and connection environments (plan 9, P9-8.1; registry entry I-18)

`adapter_registry` holds the connector entries a person saved (kinds generic_rest and from_spec; the catalogue's are
code, di.connectors.registry.catalogue_entries). `connection_approval` is the system owner's decision on one request for
an (environment, access) of one source. `source_connection` gains the environment a connection runs in (default
`production`, so the 21 demo sources and every connection made before stay as they are), the named system owner and the
registry entry and version it was made from.

Revision ID: 0053
Revises: 0052
Create Date: 2026-11-25

Idempotent (CREATE ... IF NOT EXISTS, ADD COLUMN IF NOT EXISTS), so `scripts/dev/migrate-reapply.sh 0028` applies it
again on a database that ran the empty placeholder.
"""
# ruff: noqa: E501 - long lines in the SQL

from alembic import op

revision = "0053"
down_revision = "0052"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
CREATE TABLE IF NOT EXISTS adapter_registry (
  id                 text        NOT NULL,
  version            integer     NOT NULL,
  kind               text        NOT NULL CONSTRAINT adapter_registry_kind CHECK (kind IN ('catalogue','generic_rest','from_spec')),
  system_type        text        NOT NULL,
  vendor_family      text        NOT NULL,
  auth_methods       text[]      NOT NULL DEFAULT '{}',
  resources          jsonb       NOT NULL DEFAULT '[]',
  canonical_entities text[]      NOT NULL DEFAULT '{}',
  write_actions      text[]      NOT NULL DEFAULT '{}',
  mapping_templates  jsonb       NOT NULL DEFAULT '{}',
  status             text        NOT NULL CONSTRAINT adapter_registry_status CHECK (status IN ('draft','tested','released','deprecated')),
  maintainer         text,
  source_licence     text,
  spec               jsonb       NOT NULL DEFAULT '{}',
  org_unit_id        text,
  created_by         text        NOT NULL,
  released_by        text,
  created_at         timestamptz DEFAULT now(),
  PRIMARY KEY (id, version)
);
CREATE TABLE IF NOT EXISTS connection_approval (
  id           bigserial   PRIMARY KEY,
  source_id    text        NOT NULL,
  environment  text        NOT NULL CONSTRAINT connection_approval_environment CHECK (environment IN ('test','production')),
  access       text        NOT NULL CONSTRAINT connection_approval_access CHECK (access IN ('read','read_write')),
  requested_by text        NOT NULL,
  owner        text        NOT NULL,
  status       text        NOT NULL CONSTRAINT connection_approval_status CHECK (status IN ('pending','approved','declined')),
  reason       text,
  decided_by   text,
  decided_at   timestamptz,
  created_at   timestamptz DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_connection_approval_source_status ON connection_approval (source_id, status);
ALTER TABLE source_connection ADD COLUMN IF NOT EXISTS environment text NOT NULL DEFAULT 'production';
ALTER TABLE source_connection ADD COLUMN IF NOT EXISTS system_owner text;
ALTER TABLE source_connection ADD COLUMN IF NOT EXISTS registry_id text;
ALTER TABLE source_connection ADD COLUMN IF NOT EXISTS registry_version integer;
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'source_connection_environment') THEN
    ALTER TABLE source_connection ADD CONSTRAINT source_connection_environment CHECK (environment IN ('test','production'));
  END IF;
END
$$;
"""
    )


def downgrade() -> None:
    op.execute(
        """
ALTER TABLE source_connection DROP CONSTRAINT IF EXISTS source_connection_environment;
ALTER TABLE source_connection DROP COLUMN IF EXISTS registry_version;
ALTER TABLE source_connection DROP COLUMN IF EXISTS registry_id;
ALTER TABLE source_connection DROP COLUMN IF EXISTS system_owner;
ALTER TABLE source_connection DROP COLUMN IF EXISTS environment;
DROP TABLE IF EXISTS connection_approval;
DROP TABLE IF EXISTS adapter_registry;
"""
    )
