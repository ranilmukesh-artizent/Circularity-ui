"""The workflow block catalogue (plan 6, task C1): the settings every palette block takes, their defaults and their
checks.

A graph node is `{id, k, ref, x, y}` plus, since C2, an optional `cfg`: the settings a person changed. Only settings
that differ from the defaults are stored (`compact_cfg`), so a workflow saved before settings existed, or one whose
settings are all the defaults, keeps exactly the graph it had; `node_cfg` reads a node's settings with the defaults
filled in. The steps (di/workflow/steps, task C4) read `node_cfg(node)`.

Which spec a node uses (`spec_key`): an `xf` node its transform id (x_fx, x_val ...); every other kind its kind
(conn, wconn, map, act, fixed, tool), since their refs are sources, delivery methods, fixed steps or agent tools.
The defaults reproduce what the blocks did before they had settings (USD, delta reads, hold failed records ...).

Field types and the value each holds:
    text      a string                         number   an int or float (within min/max when given)
    select    one of `choices` ("" when not required)                bool     true or false
    multi     a list of strings (from `choices`, or from the connection when `source` says so)
    fields    a list of field names
    rules     a list of {field, check, arg}: check is present | type | regex | range | in; `arg` is what the check
              needs: type → string|number|integer|bool|date, regex → a pattern, range → "min..max" (either side may be
              left out) or a comparison ">0", ">=0", "<5", "<=5", "=3", "!=3", in → comma-separated values
    mapping   an object {field: value}, values from `choices` when given (units, code tables)

`cfg_errors(node, ctx)` returns the problems, each naming the block (ctx["label"], the step's name on the canvas) and
the field. `ctx` may also carry what the source really sends: "fields" (the field names its records carry) and
"resources" (its connection's resources); a check that needs one of them is skipped when it is absent.
"""

import re
from dataclasses import asdict, dataclass
from typing import Any, Literal

FieldType = Literal["text", "number", "select", "multi", "bool", "fields", "rules", "mapping"]


@dataclass(frozen=True)
class FieldSpec:
    key: str
    label: str
    type: FieldType
    default: Any
    required: bool = False
    choices: list | None = None
    help: str = ""
    min: float | None = None
    max: float | None = None
    source: str | None = None  # choices that depend on the node: "resources" (its connection's), "workflows"


@dataclass(frozen=True)
class BlockSpec:
    ref: str
    fields: tuple[FieldSpec, ...] = ()
    readonly: bool = False


CURRENCIES = ["USD", "EUR", "INR"]  # the ISO 4217 codes the rate table has rates for (generic.to_usd)
ZONES = [
    "record", "UTC", "Europe/London", "Europe/Berlin", "America/New_York", "America/Chicago", "America/Los_Angeles",
    "Asia/Kolkata", "Asia/Singapore", "Asia/Tokyo", "Australia/Sydney",
]  # fmt: skip
UNITS = ["W", "kW", "MW", "kWh", "EA", "kg", "t", "lb", "km", "mi", "h", "days", "months", "years"]
CODE_TABLES = ["grade", "status", "location", "condition", "reason"]
MODELS = ["Asset & component", "Condition & eligibility", "Demand opportunity", "Outcome"]
CHECKS = ["present", "type", "regex", "range", "in"]
TYPES = ["string", "number", "integer", "bool", "date"]
_RANGE = re.compile(r"^\s*(?:(-?\d+(?:\.\d+)?)?\s*\.\.\s*(-?\d+(?:\.\d+)?)?|(>=|<=|!=|>|<|=)\s*(-?\d+(?:\.\d+)?))\s*$")


def F(key: str, label: str, type_: FieldType, default: Any, **kw: Any) -> FieldSpec:
    return FieldSpec(key, label, type_, default, **kw)


def _num(key: str, label: str, default: float, lo: float | None = 0, hi: float | None = None, help_: str = "") -> FieldSpec:
    return F(key, label, "number", default, min=lo, max=hi, help=help_)


_S = BlockSpec
BLOCKS: dict[str, BlockSpec] = {
    s.ref: s
    for s in (
        # ---- sources and targets
        _S("conn", (
            F("resources", "Resources", "multi", [], source="resources", help="None ticked: every resource."),
            F("mode", "Mode", "select", "delta", required=True, choices=["delta", "full"],
              help="Delta reads what changed since the last sync; full reads everything."),
            _num("lookback_days", "Lookback (days)", 0, 0, 365, "Re-read this many days before the cursor."),
        )),
        _S("wconn", (F("operation", "Target operation", "text", "", help="Empty: the operation the delivery method uses."),)),
        _S("map", (F("version", "Mapping version", "select", "latest", required=True, choices=["latest"],
                     help="latest, or a saved version number."),)),
        _S("act", (_num("timeout_s", "Timeout (s)", 30, 1, 600), _num("retries", "Retries", 3, 0, 5))),
        _S("fixed", (), True),
        _S("tool", (), True),
        # ---- ingestion
        _S("x_gw", (_num("rate_limit_per_min", "Rate limit (per min)", 0, 0, 100000, "0: no limit."),
                    _num("timeout_s", "Timeout (s)", 30, 1, 600))),
        _S("x_evt", (F("ordering_key", "Ordering key", "text", "", help="Events with the same key are kept in order."),
                     _num("replay_window_min", "Replay window (min)", 60, 0, 10080))),
        _S("x_file", (F("path", "Path", "text", "", help="Folder or object prefix; empty: the source's own."),
                      F("checksum_required", "Checksum required", "bool", True))),
        _S("x_val", (
            F("required", "Required fields", "fields", []),
            F("rules", "Rules", "rules", []),
            F("on_failure", "On failure", "select", "hold", required=True, choices=["hold", "reject"],
              help="Hold keeps failed records for reprocessing; reject drops them."),
        )),
        # ---- file steps
        _S("x_trig", (F("pattern", "File pattern", "text", "", help="Empty: any file."),
                      _num("poll_min", "Poll every (min)", 5, 1, 1440))),
        _S("x_unzip", (F("format", "Format", "select", "auto", required=True, choices=["auto", "zip", "gzip", "none"]),)),
        _S("x_chunk", (_num("rows", "Rows per chunk", 10000, 1, 1000000),)),
        _S("x_man", (F("checksum", "Include checksums", "bool", True),)),
        _S("x_cb", (_num("timeout_min", "Wait for the log (min)", 30, 1, 1440),)),
        _S("x_notify", (F("team", "Notify", "text", "", help="Empty: the workflow's owner."),)),
        # ---- transforms
        _S("x_units", (F("units", "Field units", "mapping", {}, choices=UNITS, help="Field → the unit to convert to."),)),
        _S("x_fx", (
            F("currency", "Target currency", "select", "USD", required=True, choices=CURRENCIES),
            F("rate_date", "Rate date", "select", "record", required=True, choices=["record", "run"],
              help="The rate of the record's date, or of the run's."),
            F("rate_table", "Rate table", "select", "fx_rate", required=True, choices=["fx_rate"]),
        )),
        _S("x_utc", (F("fields", "Fields", "fields", [], help="Empty: every timestamp field."),
                     F("source_zone", "Source zone", "select", "record", required=True, choices=ZONES,
                       help="record: the offset the record carries."))),
        _S("x_lookup", (F("tables", "Code tables", "mapping", {}, choices=CODE_TABLES, help="Field → code table."),)),
        _S("x_ident", (F("keys", "Identity keys", "fields", [], help="Matched within the tenant only."),)),
        _S("x_late", (
            F("keys", "Key fields", "fields", [], help="Records with the same key are de-duplicated."),
            F("newest_by", "Newest wins by", "text", "", help="Empty: the source's change time."),
            _num("late_window_min", "Late window (min)", 1440, 0, 43200),
        )),
        _S("x_env", ()),
        _S("x_flag", (F("notify", "Notify", "text", "", help="Empty: the workshop lead."),)),
        _S("x_enrich", (F("model", "Lookup model", "select", "", choices=MODELS), F("key", "Key", "text", ""))),
        _S("x_filter", (F("condition", "Condition", "rules", [], help="Rows that pass every rule are kept."),)),
        _S("x_agg", (F("group_by", "Group by", "fields", []), F("totals", "Totals", "fields", []))),
        _S("x_expr", (F("target", "Target field", "text", ""), F("expression", "Expression", "text", ""))),
        _S("x_join", (F("input", "Second input", "text", "", help="The step id of the other input."),
                      F("key", "Join key", "text", ""))),
        # ---- orchestration
        _S("x_sched", (_num("interval_min", "Interval (min)", 60, 1, 10080),)),
        _S("x_evtrig", (F("event_type", "Event type", "text", "", help="Empty: any event from the source."),)),
        _S("x_branch", (F("condition", "Condition", "rules", [], help="Rows that pass go on; the rest take the else path."),)),
        _S("x_loop", (F("items_path", "Items path", "text", "", help="Empty: each record."),)),
        _S("x_call", (F("workflow", "Workflow", "text", "", source="workflows"),)),
        _S("x_wait", (_num("duration_min", "Duration (min)", 0, 0, 10080), F("until", "Until", "text", ""))),
        # ---- branches
        _S("x_err", (F("action", "Failed records", "select", "hold", required=True, choices=["hold", "drop"]),)),
        _S("x_audit", (F("level", "Level", "select", "info", required=True, choices=["info", "warn", "debug"]),)),
        _S("x_pub", (F("topic", "Topic", "text", "model.updated", required=True),)),
    )
}  # fmt: skip
# a pair of settings that only make sense together: (block, field, needs)
_PAIRS = (("x_expr", "target", "expression"), ("x_expr", "expression", "target"), ("x_join", "input", "key"))


def spec_key(node: dict) -> str:
    """The catalogue key of a node: its transform id for an xf node, else its kind."""
    return node["ref"] if node.get("k") == "xf" else str(node.get("k"))


def spec_for(node: dict) -> BlockSpec | None:
    return BLOCKS.get(spec_key(node))


def default_cfg(ref: str) -> dict:
    """The default settings of a catalogue entry (a spec key: x_fx, conn, act ...)."""
    s = BLOCKS.get(ref)
    return {f.key: _copy(f.default) for f in s.fields} if s else {}


def node_cfg(node: dict) -> dict:
    """A node's settings with the defaults filled in for those it does not store."""
    return default_cfg(spec_key(node)) | dict(node.get("cfg") or {})


def compact_cfg(node: dict) -> dict:
    """The node as stored: `cfg` keeps only the settings that differ from the defaults, and goes when none does."""
    out = {k: v for k, v in node.items() if k != "cfg"}
    d = default_cfg(spec_key(node))
    cfg = node.get("cfg")
    if isinstance(cfg, dict):
        keep = {k: v for k, v in cfg.items() if k not in d or d[k] != v}
        if keep:
            out["cfg"] = keep
    elif cfg is not None:
        out["cfg"] = cfg  # not an object: kept so the checks can report it
    return out


def compact_graph(g: dict) -> dict:
    return g | {"nodes": [compact_cfg(n) for n in g.get("nodes") or []]}


def catalogue() -> list[dict]:
    """The catalogue as the endpoint serves it."""
    return [{"ref": s.ref, "readonly": s.readonly, "fields": [asdict(f) for f in s.fields]} for s in BLOCKS.values()]


def _copy(v: Any) -> Any:
    return list(v) if isinstance(v, list) else dict(v) if isinstance(v, dict) else v


def _is_num(v: Any) -> bool:
    return isinstance(v, int | float) and not isinstance(v, bool)


def _strs(v: Any) -> bool:
    return isinstance(v, list) and all(isinstance(x, str) for x in v)


def _rule_errors(f: FieldSpec, rules: Any) -> list[str]:
    if not isinstance(rules, list) or not all(isinstance(r, dict) for r in rules):
        return [f"{f.label} must be a list of rules."]
    out = []
    for i, r in enumerate(rules, 1):
        at = f"{f.label} rule {i}"
        fld, check, arg = r.get("field"), r.get("check"), r.get("arg")
        arg = "" if arg is None else str(arg)
        if not isinstance(fld, str) or not fld.strip():
            out.append(f"{at} has no field.")
            continue
        if check not in CHECKS:
            out.append(f"{at} has an unknown check {check} (present, type, regex, range or in).")
        elif check == "type" and arg not in TYPES:
            out.append(f"{at} needs a type: {', '.join(TYPES)}.")
        elif check == "regex":
            try:
                re.compile(arg)
            except re.error as e:
                out.append(f"{at} has a pattern that does not compile ({e}).")
            else:
                if not arg:
                    out.append(f"{at} needs a pattern.")
        elif check == "range" and not ((m := _RANGE.match(arg)) and (m.group(1) or m.group(2) or m.group(4))):
            out.append(f"{at} needs a range such as 0..100, >0 or <=5.")
        elif check == "in" and not [x for x in arg.split(",") if x.strip()]:
            out.append(f"{at} needs the values it accepts, separated by commas.")
    return out


def _field_errors(f: FieldSpec, v: Any, ctx: dict) -> list[str]:
    lb = f.label
    if f.type == "text":
        if not isinstance(v, str):
            return [f"{lb} must be text."]
        return [f"{lb} is needed."] if f.required and not v.strip() else []
    if f.type == "number":
        if not _is_num(v):
            return [f"{lb} must be a number."]
        if f.min is not None and v < f.min:
            return [f"{lb} must be at least {f.min:g}."]
        if f.max is not None and v > f.max:
            return [f"{lb} must be at most {f.max:g}."]
        return []
    if f.type == "bool":
        return [] if isinstance(v, bool) else [f"{lb} must be yes or no."]
    if f.type == "select":
        if f.key == "version" and (v == "latest" or (_is_num(v) and int(v) == v and v >= 1)):
            return []
        if f.key == "version":
            return [f"{lb} must be latest or a version number."]
        if v == "" and not f.required:
            return []
        if v == "" or v is None:
            return [f"{lb} is needed."]
        return [] if v in (f.choices or []) else [f"{lb} {v} is not one of {', '.join(f.choices or [])}."]
    if f.type in ("multi", "fields"):
        if not _strs(v):
            return [f"{lb} must be a list of {'field names' if f.type == 'fields' else 'values'}."]
        if f.required and not v:
            return [f"{lb} needs at least one."]
        out = []
        if f.choices is not None:
            out += [f"{lb} {x} is not one of {', '.join(f.choices)}." for x in v if x not in f.choices]
        if f.source == "resources" and ctx.get("resources") is not None:
            out += [f"{lb} {x} is not a resource of this connection." for x in v if x not in ctx["resources"]]
        if f.type == "fields" and ctx.get("fields") is not None:
            out += [f"{lb} {x} is not a field the records carry." for x in v if x not in ctx["fields"]]
        return out
    if f.type == "rules":
        errs = _rule_errors(f, v)
        if not errs and f.required and not v:
            errs = [f"{lb} needs at least one rule."]
        if not errs and ctx.get("fields") is not None:
            errs = [f"{lb} rule {i}: {r['field']} is not a field the records carry."
                    for i, r in enumerate(v, 1) if r["field"] not in ctx["fields"]]  # fmt: skip
        return errs
    if f.type == "mapping":
        if not isinstance(v, dict) or not all(isinstance(k, str) and isinstance(x, str) for k, x in v.items()):
            return [f"{lb} must pair each field with a value."]
        out = [f"{lb}: a field name is empty." for k in v if not k.strip()][:1]
        if f.choices is not None:
            out += [f"{lb}: {x} is not one of {', '.join(f.choices)}." for x in v.values() if x not in f.choices]
        if ctx.get("fields") is not None:
            out += [f"{lb}: {k} is not a field the records carry." for k in v if k.strip() and k not in ctx["fields"]]
        return out
    return []


def cfg_errors(node: dict, ctx: dict | None = None) -> list[str]:
    """The problems with a node's settings, each "<block>: <field> <problem>"; [] when there are none (the defaults
    always pass). `ctx`: "label" (the block's name), and optionally "fields" and "resources" (see the module doc)."""
    ctx = ctx or {}
    s = spec_for(node)
    label = ctx.get("label") or node.get("ref") or "This step"
    raw = node.get("cfg")
    if raw is None or s is None:
        return []
    if not isinstance(raw, dict):
        return [f"{label}: the settings must be an object."]
    if s.readonly and raw:
        return [f"{label}: this step has no settings to change."]
    keys = {f.key for f in s.fields}
    out = [f"{k} is not a setting of this block." for k in raw if k not in keys]
    cfg = default_cfg(s.ref) | raw
    for f in s.fields:
        out += _field_errors(f, cfg[f.key], ctx)
    for ref, a, b in _PAIRS:
        fa = next((f for f in s.fields if f.key == a), None)
        fb = next((f for f in s.fields if f.key == b), None)
        if s.ref == ref and fa and fb and isinstance(cfg[a], str) and isinstance(cfg[b], str):
            if cfg[a].strip() and not cfg[b].strip():
                out.append(f"{fb.label} is needed with {fa.label}.")
    return [f"{label}: {m}" for m in out]


__all__ = [
    "BLOCKS", "BlockSpec", "FieldSpec", "catalogue", "cfg_errors", "compact_cfg", "compact_graph", "default_cfg",
    "node_cfg", "spec_for", "spec_key",
]  # fmt: skip
