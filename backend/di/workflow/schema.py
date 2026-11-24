"""The JSON Schema (draft 2020-12) of a workflow export, generated from the block catalogue (plan 9, P9-0.7).

Owns: `workflow_schema()`, the shape the web app's `exportJson` writes and `workflow.import` reads, and the two lists
the schema and the importer share (`STEP_KINDS`, `TRIGGER_KINDS`). A step's `cfg` is checked by one `if / then`
branch per block in `di.workflow.blocks.BLOCKS` (keyed on the step's kind, and on its ref for a transform): each
setting becomes a property, choices an `enum`, numeric bounds `minimum` and `maximum`. Every setting is optional,
because the export keeps only what differs from the defaults. `if / then` rather than `oneOf`, so an error names the
setting (`steps[2].cfg.interval`) and not "no branch matched".

Never does: read the database, check that a source or block exists (the importer does, with the sources as they are
now), or run the graph checks (`workflow.validate`). Output is deterministic: keys sorted.

Implements no registry entry (an enabler, G §6 item 4); P9-1.1's pack files reuse the same library (`jsonschema`).
"""

import json
from typing import Any

from di.workflow.blocks import BLOCKS, CHECKS, FieldSpec

SCHEMA_ID = "https://circularity.example/schemas/workflow-export-1.json"
STEP_KINDS = ("fixed", "conn", "wconn", "act", "xf", "map", "tool")
TRIGGER_KINDS = ("schedule", "event", "approval", "manual", "case", "file")
WORKFLOW_TYPES = ("Ingest", "Outbound", "Decision")
_STR = {"type": "string"}
_NUM = {"type": "number"}


def _field_schema(f: FieldSpec) -> dict[str, Any]:
    """The JSON Schema of one setting; it accepts whatever `blocks.cfg_errors` accepts on shape and bounds."""
    if f.type == "text":
        return dict(_STR)
    if f.type == "number":
        out: dict[str, Any] = {"type": "number"}
        if f.min is not None:
            out["minimum"] = f.min
        if f.max is not None:
            out["maximum"] = f.max
        return out
    if f.type == "bool":
        return {"type": "boolean"}
    if f.type == "select":
        if f.key == "version":  # the mapping version: "latest" or a saved version number
            return {"oneOf": [{"const": "latest"}, {"type": "integer", "minimum": 1}]}
        return {"enum": list(f.choices or []) + ([] if f.required else [""])}
    if f.type in ("multi", "fields"):
        items: dict[str, Any] = {"enum": list(f.choices)} if f.choices is not None else dict(_STR)
        return {"type": "array", "items": items}
    if f.type == "rules":
        return {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"field": _STR, "check": {"enum": list(CHECKS)}, "arg": {"type": ["string", "number", "null"]}},
                "required": ["field", "check"],
            },
        }
    values: dict[str, Any] = {"enum": list(f.choices)} if f.choices is not None else dict(_STR)  # mapping
    return {"type": "object", "additionalProperties": values}


def _cfg_schema(ref: str) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {f.key: _field_schema(f) for f in BLOCKS[ref].fields},
        "additionalProperties": False,
    }


def _applies_to(ref: str) -> dict[str, Any]:
    """The `if` of a block's branch: a step of this kind (a block keyed by a kind), or a transform with this ref."""
    if ref in STEP_KINDS:
        return {"properties": {"kind": {"const": ref}}, "required": ["kind"]}
    return {"properties": {"kind": {"const": "xf"}, "ref": {"const": ref}}, "required": ["kind", "ref"]}


def _block_branches() -> list[dict[str, Any]]:
    return [{"x-block": ref, "if": _applies_to(ref), "then": {"properties": {"cfg": _cfg_schema(ref)}}} for ref in BLOCKS]


def _build() -> dict[str, Any]:
    step: dict[str, Any] = {
        "type": "object",
        "properties": {
            "id": {"type": "string", "minLength": 1},
            "kind": {"enum": list(STEP_KINDS)},
            "ref": {"type": "string", "minLength": 1},
            "label": _STR,
            "x": _NUM,
            "y": _NUM,
            "cfg": {"type": "object"},
        },
        "required": ["id", "kind", "ref"],
        "allOf": _block_branches(),
    }
    link = {
        "type": "object",
        "properties": {"from": _STR, "to": _STR, "fixed": {"type": "boolean"}},
        "required": ["from", "to"],
    }
    trigger = {
        "type": "object",
        "properties": {"t": {"enum": list(TRIGGER_KINDS)}, "min": {"type": "integer", "minimum": 1, "maximum": 1440}},
        "required": ["t"],
    }
    nullable = {"type": ["string", "null"]}
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": SCHEMA_ID,
        "title": "Workflow export v1",
        "type": "object",
        "properties": {
            "id": nullable,
            "name": {"type": "string", "minLength": 1},
            "version": nullable,
            "type": {"enum": list(WORKFLOW_TYPES)},
            "status": nullable,
            "owner": nullable,
            "trigger": trigger,
            "source": nullable,
            "source_id": nullable,
            "description": nullable,
            "steps": {"type": "array", "minItems": 1, "items": step},
            "links": {"type": "array", "items": link},
            "exported_by": nullable,
            "exported_at": nullable,
        },
        "required": ["name", "type", "trigger", "steps", "links"],
    }


def workflow_schema() -> dict[str, Any]:
    """The schema of a workflow export, deterministic (keys sorted; a fresh copy each call)."""
    out: dict[str, Any] = json.loads(json.dumps(_build(), sort_keys=True))
    return out
