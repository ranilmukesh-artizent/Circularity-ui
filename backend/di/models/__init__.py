"""The database schema, declared once on Base.metadata, one module per domain (finding F16).

The migrations (migrations/versions/0001-0010) create these tables; this module declares the same tables so that
`alembic check` (tests/test_models_migrations.py) can prove the two agree, and so that autogenerate starts from the
real schema. The database and the migrations are the source of truth: a change goes into a new migration first and
is mirrored here.

`Job` is a mapped class (di/core/jobs.py uses the ORM); every other table is a Core `Table`, read and written with SQL.

Not metadata (they live in the migrations only, and `alembic check` does not see them):
- the live-update functions and triggers of 0008/0009: stream_put(text, text, jsonb), stream_notify(),
  stream_from_domain_event(), stream_from_state_item(), stream_from_sync_run(), stream_from_instruction(), and the
  triggers stream_event_notify, domain_event_stream, state_item_stream, sync_run_stream, instruction_stream;
- the starting rows of `delegation` (0002).
"""

from di.models.access import delegation, tenant_grant
from di.models.agents import agent_identity, agent_proposal, agent_run, agent_run_step
from di.models.base import Base, metadata
from di.models.canonical import canonical, conflict, failed_record, provenance
from di.models.cases import case_record, case_stage_log
from di.models.compose import composition, composition_version, config_change_set
from di.models.connectors import (
    fetch_log,
    field_mapping,
    raw_record,
    source_connection,
    source_secret,
    source_system,
    sync_cursor,
    sync_run,
    webhook_event,
)
from di.models.device import (
    device_bid,
    device_dispute,
    device_launch,
    device_listing,
    device_price_point,
    device_replacement_demand,
    device_sale,
    device_tradein,
)
from di.models.instructions import instruction
from di.models.jobs import Job
from di.models.journal import action_journal, domain_event, stream_event
from di.models.learning import model_version
from di.models.llm import llm_budget, llm_model
from di.models.market_tables import market_table
from di.models.modeler import decision_flow, decision_flow_version, shadow_decision
from di.models.org import org_unit
from di.models.overlay import customer_overlay
from di.models.packs import pack_version
from di.models.policy import standing_policy, standing_policy_version
from di.models.reference import fx_rate
from di.models.replay import replay_batch, replay_item
from di.models.service_desk import refurb_unit, repair_accuracy, repair_history, service_ticket, upgrade_offer
from di.models.work import work_item
from di.models.workspace import state_item, state_seed

__all__ = [
    "Base",
    "Job",
    "action_journal",
    "agent_identity",
    "agent_proposal",
    "agent_run",
    "agent_run_step",
    "canonical",
    "case_record",
    "case_stage_log",
    "composition",
    "composition_version",
    "config_change_set",
    "conflict",
    "customer_overlay",
    "decision_flow",
    "decision_flow_version",
    "delegation",
    "device_bid",
    "device_dispute",
    "device_launch",
    "device_listing",
    "device_price_point",
    "device_replacement_demand",
    "device_sale",
    "device_tradein",
    "domain_event",
    "failed_record",
    "fetch_log",
    "field_mapping",
    "fx_rate",
    "instruction",
    "llm_budget",
    "llm_model",
    "market_table",
    "metadata",
    "model_version",
    "org_unit",
    "pack_version",
    "provenance",
    "raw_record",
    "refurb_unit",
    "repair_accuracy",
    "repair_history",
    "replay_batch",
    "replay_item",
    "service_ticket",
    "shadow_decision",
    "source_connection",
    "source_secret",
    "source_system",
    "standing_policy",
    "standing_policy_version",
    "state_item",
    "state_seed",
    "stream_event",
    "sync_cursor",
    "sync_run",
    "tenant_grant",
    "upgrade_offer",
    "webhook_event",
    "work_item",
]
