# ruff: noqa: E501 - long lines in the docstring table and the action declarations
"""Composition actions (plan 9, P9-8.17; G C8, C12; R21): one approvable object made of the description's change set, the
mapping rows the owner accepted and the stage-agent settings, with maker-checker.

    compose.start          act     {org_unit_id, text, pack_key?}   the configuration agent (I-13) drafts the change set
    compose.answer         act     {id, answer}                     re-drafts with the answer to the pack's one question
    compose.editChangeSet  act     {id, ops}                        replaces the typed operations after the overlay validator
    compose.markStep       act     {id, step}                       describe, mapping or agents is done
    compose.get / .list    read    {id} / {org_unit_id?}            a composition; the compositions the person may see
    compose.systems        read    {id}                             the systems the change set names, each joined with the
                                                                    org's sources and the adapter registry (P9-8.18)
    compose.prompts        read    {pack_key}                       the pack's sample prompts, for the Describe step
    compose.packs          read    {}                               every pack with its industry, unit, stages and one sample
                                                                    (Set up's template picker)
    compose.testRun        read    {id, limit?, batch_id?}          (P9-8.19) past items through the draft: where
                                                                    cases stopped, by stage and reason; writes nothing
    compose.submit         act     {id}                             refused with the blocking list; else a snapshot
    compose.setStageAgents act     {id, stages, threshold}          (P9-8.20) the stage-agent settings: `stageAgent.set` operations
                                                                    and one `param.set confidence_threshold`, beside the overlay's
    compose.sendBack       act     {id, step, reason, node_id?}     approve.packs: the reason (15+ characters) on the step
    compose.approve        commit  {id}                             approve.packs: applies the parts as one, or none of them
    compose.publish        commit  {id, region, share?}             (P9-8.20) approve.packs: starts the canary of P9-7.3 as this
                                                                    person (`rollout.startCanary`, through the pipeline); needs
                                                                    the flow in shadow and its replay report
    compose.history        read    {id}                             versions, journal rows, what publishing needs, and the stage
                                                                    rows the agents step shows

`managePacks` makes and submits, `approve.packs` sends back and approves (di.core.policy.EXTRA_PERMS); the composition's org
unit must be in the person's tenants. The maker is never the checker: whoever created, edited or submitted a composition cannot
approve it. Send back, approve and publish (P9-8.20) are in `FORBIDDEN_ACTIONS`; an agent may start, answer, edit and mark
steps (drafts). Approve runs inside the action's one transaction: the overlay goes through the overlay's own save and approve
handlers (`overlays.approve`; this actor the checker, the composition's maker the overlay's maker), then the accepted mapping
rows become a new mapping version per source (`mapping.save_version`), then the stage-agent settings are validated and kept in
the approved snapshot; any failure undoes all of it. Mapping rows come from `steps.mapping.fields` (`{source_id, row, state}`,
filled by P9-8.18); the stage settings from `steps.agents.settings` (`{stage, autonomy, threshold}`). Since 28 Nov 2026 the
stage chain runs with them: for a case of the pack owned by exactly the composition's org unit, the runtime reads the settings
of the newest approved or published composition (`repositories.compositions.approved_stage_settings`) and lays them on the
pack's stages (`chain.stage_defs(pack, settings)`: autonomy, threshold, and the limits of a stage set to act within limits).
With no such composition the chain reads the pack alone, as before.

The agents step and the agent registry (28 Nov 2026): a stage row's `agent_id` is a label (the pack's "Intake", "Condition" …),
not a registry id. The registry agents that run a pack stage are fixed by the chain (`chain.agents_of`: `receive` is
stage-lease, stage-return, stage-transit and stage-intake); `compose.history` lists them per stage as `runs_as`
(`{id, name, enabled, autonomy}`). A composition never writes the registry: an agent's registry autonomy (read, propose, act)
is global and Admin's alone (`agent.update`); the stage autonomy set here (recommend, limits, alone) is per pack and org unit.

P9-8.20: the agents step is written by `compose.setStageAgents` into `steps.agents.settings` (stage, agent_id, autonomy, limits,
threshold) and, as typed records for the audit and the approver's view, into `change_set.stage_ops` (`stageAgent.set` and one
`param.set`): not into `change_set.ops`, which stay the overlay's five operations (I-4; the overlay validator and `parse_ops` do
not know the stage operations). `with_stage_settings` (`di.services.modeler.compose`, re-exported here) applies the settings to a
pack's stages (pure) for the stage chain. Publishing is a person's commit on an approved composition; it never writes rollout rows
itself: `rollout.startCanary` does, run through `invoke` as the same person, so its own maker-checker and replay checks apply.
The one wording, the summary of the replay report, goes through `stop_explainer` (AgentLoop) with `stop_reasons.check_text`.
"""

import json
from collections.abc import Sequence
from typing import Any, cast

from pydantic import ValidationError
from sqlalchemy import text

from di.connectors import lifecycle, mapping
from di.connectors.registry import ADAPTERS
from di.core import policy
from di.core.orgs import subtree
from di.repositories import adapter_registry as adapter_repo
from di.repositories import compositions as repo
from di.repositories import flows as flow_repo
from di.repositories import mapping_decisions
from di.repositories import overlays as overlay_repo
from di.repositories import replay as replay_repo
from di.repositories import rollouts as rollout_repo
from di.repositories.orgs import units
from di.repositories.packs import active_pack
from di.services.actions import overlays
from di.services.actions import rollout as rollout_actions
from di.services.actions.modeler import _boundary, _org_ok
from di.services.actions.pipeline import CallContext, invoke
from di.services.actions.registry import ACTIONS, ActionDef, ActionError, Risk, guard, implement
from di.services.agents import chain
from di.services.agents import registry as agent_registry
from di.services.agents.config_agent import MAX_TEXT, ChangeSet, ChangeSetError, draft_change_set, read_text
from di.services.agents.playbooks import pack_author, stop_explainer
from di.services.cases.decide import Decision, decide_case
from di.services.modeler import compose as core
from di.services.modeler import mapping_choices, stop_reasons
from di.services.modeler.compile import FlowVersion
from di.services.modeler.gates import catalogue
from di.services.modeler.overlay import OverlayError, apply_overlay, ops_json, parse_ops
from di.services.modeler.pack import Pack, load_pack, pack_keys
from di.services.modeler.stages import STAGE_KEYS, STAGE_LABELS
from di.services.policy_standing import decide_threshold
from di.services.replay import history
from di.services.replay import run as replay_run

_MANAGE, _APPROVE = "managePacks", "approve.packs"
MAKER_CHECKER = "Maker-checker: you composed this, so you cannot approve it."
_STR = {"req": True, "t": "string"}
_ID = {"id": {"req": True, "t": "number"}}
_EDITABLE = ("draft", "sent_back")


_OPS = {"req": True, "t": "array"}
_REASON = {"req": True, "t": "string", "min": 15, "minText": "Add a reason of at least 15 characters."}
# (id, title, description, risk, input, permission)
_DECLARED: tuple[tuple[str, str, str, Risk, dict[str, dict[str, Any]], str | None], ...] = (
    ("compose.start", "Start a composition", "Describe a business: the configuration agent drafts the change set.", "act",
     {"org_unit_id": _STR, "text": _STR, "pack_key": {"t": "string"}}, _MANAGE),
    ("compose.answer", "Answer the composition's question", "Answer the pack's one question; changes are redrafted.",
     "act", {**_ID, "answer": _STR}, _MANAGE),
    ("compose.editChangeSet", "Edit a composition's changes", "Replace the composition's changes, checked against the pack.",
     "act", {**_ID, "ops": _OPS}, _MANAGE),
    ("compose.markStep", "Mark a composition step done", "Mark the describe, mapping or agents step done.", "act",
     {**_ID, "step": _STR}, _MANAGE),
    ("compose.get", "Read a composition", "Read one composition with its steps and change set.", "read", _ID, None),
    ("compose.list", "List compositions", "List the compositions of the org units the person may see.", "read",
     {"org_unit_id": {"t": "string"}}, None),
    ("compose.systems", "Read a composition's systems", "The systems the changes name, with the org's sources and adapters.",
     "read", _ID, None),
    ("compose.prompts", "Read a pack's sample prompts", "The sample descriptions a pack offers to start a composition.", "read",
     {"pack_key": _STR}, None),
    ("compose.packs", "List the template packs", "Every template pack a setup can start from, with what it covers.", "read",
     {}, None),
    ("compose.testRun", "Test run a composition", "Put past items through the draft and see where cases stopped.", "read",
     {**_ID, "limit": {"t": "number"}, "batch_id": {"t": "number"}}, _MANAGE),
    ("compose.submit", "Submit a composition", "Send a finished composition to a different person for approval.", "act",
     _ID, _MANAGE),
    ("compose.setStageAgents", "Set a composition's stage agents", "Set each stage's agent and autonomy, and the confidence threshold.",
     "act", {**_ID, "stages": _OPS, "threshold": {"req": True, "t": "number"}}, _MANAGE),
    ("compose.publish", "Publish a composition", "Start the canary of an approved composition in a region at a share of its cases.",
     "commit", {**_ID, "region": _STR, "share": {"t": "number"}}, _APPROVE),
    ("compose.history", "Read a composition's history", "The versions of a composition, its journal rows, and what publishing needs.",
     "read", _ID, None),
    ("compose.sendBack", "Send a composition back", "Send a submitted composition back to its maker, with the step and a reason.",
     "act", {**_ID, "step": _STR, "node_id": {"t": "string"}, "reason": _REASON}, _APPROVE),
    ("compose.approve", "Approve a composition", "Approve a submitted composition: changes, mapping and settings apply as one.",
     "commit", _ID, _APPROVE),
)  # fmt: skip
for _a in _DECLARED:
    ACTIONS.setdefault(
        _a[0], ActionDef(id=_a[0], title=_a[1], desc=_a[2], risk=_a[3], perm=_a[5], scope="none", input=_a[4], verb=_a[1].lower())
    )


# ---------------------------------------------------------------- helpers
def _row(i: dict[str, Any], ctx: CallContext, for_update: bool = False) -> dict[str, Any]:
    row = repo.get(ctx.session, int(i["id"]), for_update=for_update)
    if row is None:
        raise ActionError("not_found", f"No composition {i['id']}.")
    return row


def _reach(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | None:
    """The refusal for an unknown composition or one of an org the person cannot see."""
    row = repo.get(ctx.session, int(i["id"]))
    if row is None:
        return "not_found", f"No composition {i['id']}."
    return None if _org_ok(ctx, row["org_unit_id"]) else _boundary(row["org_unit_id"])


def _pack(row: dict[str, Any], ctx: CallContext) -> Pack:
    return active_pack(ctx.session, row["pack_key"], row["org_unit_id"])


def _ops(row: dict[str, Any]) -> list[Any]:
    return parse_ops(row["change_set"].get("ops") or [])


def _save(ctx: CallContext, cid: int, **cols: Any) -> None:
    json_cols = {"change_set", "steps", "reading"}
    sets = ", ".join(f"{k} = CAST(:{k} AS jsonb)" if k in json_cols else f"{k} = :{k}" for k in cols)
    vals = {k: json.dumps(v) if k in json_cols else v for k, v in cols.items()}
    sql = f"UPDATE composition SET {sets}, updated_at = :now WHERE id = :id"  # noqa: S608 - column names are this module's; values bound
    ctx.session.execute(text(sql), {**vals, "id": cid, "now": ctx.now})


def _editors(row: dict[str, Any], ctx: CallContext) -> list[str]:
    return sorted({*row["editors"], ctx.actor.id})


def _version(ctx: CallContext, row: dict[str, Any], status: str, **cols: Any) -> int:
    """Move the composition to `status` as a new version with its snapshot (the row's columns changed by `cols` first)."""
    new = {**row, **cols, "status": status}
    ver = row["version"] + 1
    _save(ctx, row["id"], status=status, version=ver, **cols)
    repo.add_version(ctx.session, row["id"], ver, json.dumps(core.snapshot(new)), status, ctx.actor.id, ctx.now)
    return ver


def _may_read(ctx: CallContext) -> bool:
    acct = ctx.actor.account
    return acct is not None and (policy.can(acct, _MANAGE, ctx.actor.ctx) or policy.can(acct, _APPROVE, ctx.actor.ctx))


def _out(row: dict[str, Any]) -> dict[str, Any]:
    return dict(row)


def _wanted(row: dict[str, Any], want: tuple[str, ...], msg: str) -> tuple[str, str] | None:
    return None if row["status"] in want else ("conflict", msg)


def _failed(e: ChangeSetError) -> ActionError:
    return ActionError("validation_error", e.message, {"op_id": e.op_id} if e.op_id else None)


# ---------------------------------------------------------------- start, answer
def _draft(text_: str, org: str, packs: list[Pack], answer: str | None, ctx: CallContext) -> ChangeSet:
    try:
        return draft_change_set(text_, org, packs=packs, answer=answer, drafter=pack_author.make_drafter(ctx))
    except ChangeSetError as e:
        raise _failed(e) from e


@guard("compose.start")
def start_guard(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | None:
    if len(i["text"]) > MAX_TEXT:
        return "validation_error", f"The description is {len(i['text']):,} characters: keep it under {MAX_TEXT:,}."
    if i.get("pack_key") and i["pack_key"] not in pack_keys():
        return "not_found", f"No pack {i['pack_key']}."
    if i["org_unit_id"] not in units(ctx.session):
        return "not_found", f"No org unit {i['org_unit_id']}."
    return None if _org_ok(ctx, i["org_unit_id"]) else _boundary(i["org_unit_id"])


@implement("compose.start")
def start(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    org = i["org_unit_id"]
    keys = [i["pack_key"]] if i.get("pack_key") else pack_keys()
    packs = [active_pack(ctx.session, k, org) for k in keys]
    cs = _draft(i["text"], org, packs, None, ctx)
    reading = read_text(i["text"], packs).model_copy(update={"by_model": cs.by_model})
    cid = ctx.session.execute(
        text(
            "INSERT INTO composition (org_unit_id, pack_key, base_version, text, reading, change_set, steps, status, created_by, "
            "editors, created_at, updated_at) VALUES (:o, :p, :v, :t, CAST(:r AS jsonb), CAST(:c AS jsonb), CAST(:s AS jsonb), "
            "'draft', :by, :ed, :at, :at) RETURNING id"
        ),
        {
            "o": org, "p": cs.pack, "v": cs.base_version, "t": i["text"], "r": reading.model_dump_json(),
            "c": cs.model_dump_json(), "s": json.dumps(core.new_steps()), "by": ctx.actor.id, "ed": [ctx.actor.id], "at": ctx.now,
        },
    ).scalar_one()  # fmt: skip
    return _out(_row({"id": cid}, ctx)) | {"log": f"Started a composition for {cs.pack} at {org}"}


def _editable_guard(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | None:
    if bad := _reach(i, ctx):
        return bad
    return _wanted(_row(i, ctx), _EDITABLE, "A composition that was submitted or approved cannot be changed.")


guard("compose.answer")(_editable_guard)


@implement("compose.answer")
def answer(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    row = _row(i, ctx, for_update=True)
    cs = _draft(row["text"], row["org_unit_id"], [_pack(row, ctx)], i["answer"], ctx)
    kept = {"stage_ops": row["change_set"]["stage_ops"]} if "stage_ops" in row["change_set"] else {}  # the agents step stays
    _save(ctx, row["id"], change_set=cs.model_dump(mode="json") | kept, editors=_editors(row, ctx))
    return _out(_row(i, ctx)) | {"log": f"Answered the question of composition {row['id']}"}


# ---------------------------------------------------------------- edit, mark
@guard("compose.editChangeSet")
def edit_guard(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | tuple[str, str, dict[str, Any]] | None:
    if bad := _editable_guard(i, ctx):
        return bad
    try:
        apply_overlay(_pack(_row(i, ctx), ctx), parse_ops(i["ops"]))
    except ValidationError as e:
        first = e.errors()[0]
        return "validation_error", f"The operations are not valid ({'.'.join(str(p) for p in first['loc'])}): {first['msg']}."
    except ValueError as e:
        if isinstance(e, OverlayError):
            return "validation_error", e.message, {"op_id": e.op_id, "overlay_code": e.code}
        return "validation_error", f"The operations are not valid: {e}."
    return None


@implement("compose.editChangeSet")
def edit(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    row = _row(i, ctx, for_update=True)
    ops = parse_ops(i["ops"])
    kept = {o.id for o in ops}
    cs = {**row["change_set"], "ops": ops_json(ops), "assumed": [a for a in row["change_set"].get("assumed", []) if a in kept]}
    _save(ctx, row["id"], change_set=cs, editors=_editors(row, ctx))
    return _out(_row(i, ctx)) | {"log": f"Changed the operations of composition {row['id']}"}


@guard("compose.markStep")
def mark_guard(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | None:
    if bad := _editable_guard(i, ctx):
        return bad
    return (
        None
        if i["step"] in core.MAKER_STEPS
        else ("validation_error", f"A step to mark is one of {', '.join(core.MAKER_STEPS)}.")
    )


@implement("compose.markStep")
def mark_step(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    row = _row(i, ctx, for_update=True)
    steps = {**row["steps"], i["step"]: {**row["steps"].get(i["step"], {}), "state": "done"}}
    steps[i["step"]].pop("note", None)
    _save(ctx, row["id"], steps=steps, editors=_editors(row, ctx))
    return _out(_row(i, ctx)) | {"log": f"Marked step {i['step']} of composition {row['id']} done"}


# ---------------------------------------------------------------- reads
@guard("compose.get")
def get_guard(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | None:
    if not _may_read(ctx):
        return "out_of_scope", f"The {ctx.actor.role} view cannot read compositions."
    return _reach(i, ctx)


@implement("compose.get")
def get(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    return _row(i, ctx)


@guard("compose.list")
def list_guard(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | None:
    if not _may_read(ctx):
        return "out_of_scope", f"The {ctx.actor.role} view cannot read compositions."
    org = i.get("org_unit_id")
    if org and org not in units(ctx.session):
        return "not_found", f"No org unit {org}."
    return None if not org or _org_ok(ctx, org) else _boundary(org)


@implement("compose.list")
def list_compositions(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    org = i.get("org_unit_id")
    reach = [org] if org else [u for u in units(ctx.session) if _org_ok(ctx, u)]
    return {"compositions": repo.listing(ctx.session, reach)}


# ---------------------------------------------------------------- systems (P9-8.18)
_MAP_KEYS = ("fields", "pre_ticked", "check", "none", "asked_owner")


@guard("compose.prompts")
def prompts_guard(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | None:
    if not _may_read(ctx):
        return "out_of_scope", f"The {ctx.actor.role} view cannot read compositions."
    return None if i["pack_key"] in pack_keys() else ("not_found", f"No pack {i['pack_key']}.")


@implement("compose.prompts")
def prompts(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:  # noqa: ARG001 - a read of the pack file
    return {"pack_key": i["pack_key"], "prompts": [p for p in load_pack(i["pack_key"]).prompts if p]}


@guard("compose.packs")
def packs_guard(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | None:  # noqa: ARG001
    return None if _may_read(ctx) else ("out_of_scope", f"The {ctx.actor.role} view cannot read compositions.")


@implement("compose.packs")
def packs(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:  # noqa: ARG001 - a read of the pack files
    """The template picker of Set up (28 Nov 2026): each pack with its industry, what it handles, its stages and one sample."""
    out = []
    for k in pack_keys():
        p = load_pack(k)
        out.append({
            "key": k, "name": p.name, "industry": p.industry, "unit": p.unit, "version": p.version,
            "stages": [s.label for s in p.stages], "classes": [c.name for c in p.classes][:6],
            "sample": next((x for x in p.prompts if x), ""),
        })  # fmt: skip
    return {"packs": out}


guard("compose.systems")(get_guard)


def _wanted_systems(row: dict[str, Any], pack: Pack) -> list[tuple[str, str, str]]:
    """(name, system type, key) of every system the composition needs: the change set's, then the pack's mapping sources
    (a system the pack reads by its source key, such as the legacy depot repair log) that the change set does not name."""
    types = {s.name: s.type for s in pack.data.systems}
    named = [str(s["name"]) for s in row["change_set"].get("systems") or []]
    out = [(n, types.get(n, "api"), types.get(n, n)) for n in named]
    seen = {t for _, t, _ in out}
    for key in dict.fromkeys(str(m["source"]) for m in pack.data.mappings if m.get("source")):
        if key in seen:
            continue
        name = str(getattr(ADAPTERS.get(key), "vendor", key)).replace(" (synthetic)", "")
        out.append((name, key, key))
    return out


def _sources(s: Any, org: str) -> list[dict[str, Any]]:
    """The org's sources (its own and the shared ones) that are not deleted, with where their connection runs."""
    gone = lifecycle.deleted(s)
    rows = s.execute(
        text(
            "SELECT ss.id, ss.type, ss.vendor, sc.environment, sc.registry_id, sc.registry_version FROM source_system ss "
            "LEFT JOIN source_connection sc ON sc.source_id = ss.id "
            "WHERE ss.org_unit_id IS NULL OR ss.org_unit_id = :o ORDER BY ss.id"
        ),
        {"o": org},
    ).mappings()
    return [dict(r) for r in rows if r["id"] not in gone]


def _match(src: dict[str, Any], key: str, kind: str, reg_type: dict[tuple[str, int], str]) -> int | None:
    """How well a source is this system: 0 its id is the key, 1 its registry entry has the system's type, 2 a source with
    no registry entry has that type; None not at all. A source made from an entry is only ever that entry's system."""
    if src["id"] == key:
        return 0
    if src["registry_id"]:
        return 1 if reg_type.get((src["registry_id"], src["registry_version"])) == kind else None
    return 2 if src["type"] == kind else None


def _mapping_summary(ctx: CallContext, sid: str, vendor: str) -> dict[str, int]:
    """The bands of the suggestions for the source's stored sample, as `mapping.suggest` counts them (no model: a read)."""
    from di.connectors import discover, mapping_suggest
    from di.services.actions.fabric_sources import _family_memory

    s = ctx.session
    canon, memory = mapping_suggest.canonical_fields(), _family_memory(s, sid, vendor)
    counts = dict.fromkeys(_MAP_KEYS, 0)
    for recs in discover._samples(s, sid).values():
        sample = [p for _, p in recs]
        for band, n in _band_counts(sid, sample, canon, memory).items():
            counts["fields"] += n
            counts[band] += n
    counts["asked_owner"] = len(mapping_decisions.open_questions(s, sid))
    return counts


_BANDS_KEPT = 128
_bands_cache: dict[str, dict[str, int]] = {}


def _band_counts(sid: str, sample: list[Any], canon: Any, memory: Any) -> dict[str, int]:
    """How many fields of one stored sample fall in each band. Profiling and scoring a sample is the slow part of the systems
    read (seconds a source), and its answer only changes with the sample, the canonical model or what the vendor family
    accepted before, so it is kept by a digest of those three (the newest 128; a process restart starts empty)."""
    import hashlib

    from di.connectors import mapping_suggest

    key = hashlib.sha256(
        json.dumps([sid, sample, repr(canon), repr(memory)], sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()
    hit = _bands_cache.get(key)
    if hit is None:
        hit = {}
        profiles = [mapping_suggest.profile(sample, f) for f in mapping_suggest.field_paths(sample)]
        for prop in mapping_suggest.suggest(profiles, sample, canon, memory=memory, source_id=sid):
            hit[prop.band] = hit.get(prop.band, 0) + 1
        if len(_bands_cache) >= _BANDS_KEPT:
            _bands_cache.pop(next(iter(_bands_cache)))
        _bands_cache[key] = hit
    return dict(hit)


def _status(ctx: CallContext, src: dict[str, Any], asked: int) -> str:
    """Waiting for the system owner (a pending connection request, or a mapping question), else test or connected."""
    pending = any(a["status"] == "pending" for a in adapter_repo.approvals_of(ctx.session, src["id"]))
    return "awaiting_owner" if asked or pending else ("test_connection" if src["environment"] == "test" else "connected")


@implement("compose.systems")
def systems(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    row = _row(i, ctx)
    s, org = ctx.session, row["org_unit_id"]
    entries = adapter_repo.entries(s, org)
    reg_type = {(e.id, e.version): e.system_type for e in entries}
    sources = _sources(s, org)
    out: list[dict[str, Any]] = []
    for name, kind, key in _wanted_systems(row, _pack(row, ctx)):
        found = sorted(
            ((m, x["id"], x) for x in sources if (m := _match(x, key, kind, reg_type)) is not None), key=lambda t: (t[0], t[1])
        )
        offered = sorted({e.id for e in entries if e.system_type == kind or e.id == key})
        base = {"name": name, "system_type": kind, "registry": offered}
        if not found:
            out.append(base | {"source_id": None, "status": "needs_adapter", "mapping": dict.fromkeys(_MAP_KEYS, 0)})
            continue
        src = found[0][2]
        summary = _mapping_summary(ctx, src["id"], src["vendor"])
        out.append(base | {"source_id": src["id"], "status": _status(ctx, src, summary["asked_owner"]), "mapping": summary})
    return {"id": row["id"], "systems": out}


# ---------------------------------------------------------------- test run (P9-8.19)
DEFAULT_SAMPLE, MAX_SAMPLE = 200, 2000
_HELD_CODES = {
    history.R_DUP: "dup", history.R_DATE: "date", history.R_VALUE: "value", history.R_COST: "cost", history.R_NO_ID: "id",
}  # fmt: skip


def _held_code(reason: str) -> str:
    """The code of a row the import held (its reason text is the history module's)."""
    if reason in _HELD_CODES:
        return _HELD_CODES[reason]
    return "route" if reason.startswith("Route '") else "fact" if reason.startswith("Fact ") else "other"


def _fact_target(fact: str) -> str:
    return f"{fact}.{replay_run.ALIASES.get(fact, fact)}"  # the history column `condition` is the field `condition.grade`


def _mapped_targets(row: dict[str, Any], pack: Pack, ctx: CallContext) -> set[str]:
    """The canonical fields the draft brings in: the rows the owner accepted in the mapping step and the current mapping of
    every source that is one of the systems the composition needs (the join `compose.systems` shows)."""
    out = {
        str(f["row"][2]).strip().removesuffix("[]")
        for f in (row["steps"].get("mapping") or {}).get("fields") or []
        if f.get("state") == "accepted" and len(f.get("row") or []) > 2
    }
    s, org = ctx.session, row["org_unit_id"]
    reg_type = {(e.id, e.version): e.system_type for e in adapter_repo.entries(s, org)}
    sources = _sources(s, org)
    for _name, kind, key in _wanted_systems(row, pack):
        found = sorted((m, x["id"]) for x in sources if (m := _match(x, key, kind, reg_type)) is not None)
        if found:
            out |= {str(r[2]).strip().removesuffix("[]") for r in _current_maps(ctx, found[0][1]) if len(r) > 2}
    return out


def _test_batch(i: dict[str, Any], row: dict[str, Any], ctx: CallContext) -> Any:
    """The batch a test run reads (the one asked for, else the org's newest of the pack with good rows) or the refusal."""
    s = ctx.session
    if i.get("batch_id") is not None:
        found = replay_repo.batches(s, [int(i["batch_id"])])
        if not found:
            return "not_found", f"No history batch {i['batch_id']}."
        if (found[0].pack, found[0].org_unit_id) != (row["pack_key"], row["org_unit_id"]):
            return "conflict", "The batch is not history of this composition's pack and org unit."
        return found[0]
    for b in replay_repo.for_org(s, row["pack_key"], row["org_unit_id"]):
        if b.rows > b.held:
            return b
    return "not_found", f"No past decisions of {row['pack_key']} at {row['org_unit_id']}: import a history batch first."


@guard("compose.testRun")
def test_run_guard(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | None:
    if bad := _reach(i, ctx):
        return bad
    if i.get("limit") is not None and not 1 <= int(i["limit"]) <= MAX_SAMPLE:
        return "validation_error", f"The sample is 1 to {MAX_SAMPLE:,} past items."
    got = _test_batch(i, _row(i, ctx), ctx)
    return got if isinstance(got, tuple) else None


def _trace(item_id: str, d: Decision, stages: Sequence[str], limits: dict[str, float]) -> stop_reasons.Trace:
    """Where a decision stopped (R20 order: gates, then a stage's confidence threshold), or no stop when it chose a route."""
    failed = [g for g in d.gates if not g.passed]
    if failed and (d.hold or d.recommendation is None):
        g = next((x for x in failed if x.effect.hold), failed[0])
        gd = catalogue().get(g.gate_id)
        return stop_reasons.Trace(item_id, gd.stage if gd and gd.stage in stages else "decide", f"guardrail:{g.gate_id}")
    if d.recommendation is None:
        return stop_reasons.Trace(item_id, "decide", "no_route:decide")
    conf = replay_run.confidence_of(d)
    if conf is not None:
        for st in stages:
            if st in limits and conf < limits[st]:
                return stop_reasons.Trace(item_id, st, f"threshold:{st}")
    return stop_reasons.Trace(item_id)


@implement("compose.testRun")
def test_run(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    """Put the batch's items (at most `limit`) through the draft pack: an item the draft cannot give a field stops there, the
    rest are decided by `replay` (I-16, so `decide_case`, R19) and read as traces. Writes no row."""
    row, s = _row(i, ctx), ctx.session
    try:
        draft = apply_overlay(_pack(row, ctx), _ops(row))
    except OverlayError as e:
        raise ActionError("validation_error", f"The changes do not validate ({e.op_id}): {e.message}") from e
    batch = cast(Any, _test_batch(i, row, ctx))
    items = replay_repo.ok_items(s, batch.id)[: int(i.get("limit") or DEFAULT_SAMPLE)]
    stages: list[str] = [st.key for st in draft.stages if st.key in stop_reasons.STAGES] or [*stop_reasons.STAGES]
    labels: dict[str, str] = {st.key: st.agent for st in draft.stages}
    governed = {f"{m['model']}.{f}" for m in draft.data.mappings for f in m.get("fields") or []}
    required = sorted({t for it in items for n in it["facts"] if (t := _fact_target(n)) in governed})
    mapped = _mapped_targets(row, draft, ctx)
    traces: list[stop_reasons.Trace] = []
    ready: list[dict[str, Any]] = []
    for it in items:
        lack = next((t for t in required if t not in mapped or t.partition(".")[0] not in it["facts"]), None)
        if lack is None:
            ready.append(it)
            continue
        stage = lack.partition(".")[0]
        traces.append(stop_reasons.Trace(str(it["item_id"]), stage if stage in stages else "value", f"missing_field:{lack}"))
    held = s.execute(
        text("SELECT item_id, held_reason FROM replay_item WHERE batch_id = :b AND status = 'held' ORDER BY n"), {"b": batch.id}
    ).mappings()
    traces += [stop_reasons.Trace(str(h["item_id"]), "receive", f"held_record:{_held_code(h['held_reason'])}") for h in held]
    limits = {str(x["stage"]): float(x["threshold"]) for x in core.stage_settings(row["steps"]) if x.get("threshold") is not None}
    limits.setdefault("decide", decide_threshold(draft))
    decided: dict[str, Decision] = {}

    def watch(case: Any, pack: Pack, fv: FlowVersion, **kw: Any) -> Decision:
        try:
            d = decide_case(case, pack, fv, **kw)
        except ActionError:  # the valuer refuses the item's facts: `replay` counts it, the trace says where
            traces.append(stop_reasons.Trace(str(case["id"]), "value", "no_route:value"))
            raise
        decided[str(case["id"])] = d
        return d

    if ready:
        replay_run.replay(batch, ready, FlowVersion(None, 0, ()), pack=draft, decide=watch, label="draft")
    traces += [_trace(k, d, stages, limits) for k, d in decided.items()]
    stops = stop_reasons.group(traces, stages)
    n_decided = sum(1 for t in traces if t.stage is None)
    total = len(traces)
    line = stop_reasons.sentence(stops, total, n_decided, labels)
    facts = line + "\n" + "\n".join(
        f"{s_.stage}: reached {s_.reached}, stopped {s_.stopped}; " + ", ".join(f"{r}: {n}" for r, n in s_.reasons)
        for s_ in stops if s_.stopped
    )  # fmt: skip
    choices = mapping_choices.report(items, draft)  # what each choice of an ambiguous mapping would have stopped (P9-11.11)
    facts += "".join(f"\n{c['text']}" for c in choices)
    words = stop_explainer.explain(ctx, facts, lambda t: stop_reasons.check_text(t, facts))
    return {
        "id": row["id"], "batch_id": batch.id, "sample": len(items), "total": total, "decided": n_decided,
        "stages": [s_.view() for s_ in stops], "text": "\n".join([words or line, *(c["text"] for c in choices)]),
        "by_model": words is not None, "mapping_choices": choices,
        "decisions": [{"item_id": t.item_id, "route": decided[t.item_id].route} for t in traces if t.stage is None],
    }  # fmt: skip


# ---------------------------------------------------------------- submit
def _undecided(row: dict[str, Any], pack: Pack, ctx: CallContext) -> list[str]:
    """The mapping fields the pack hints at (a field it knows to be unsure, P9-9.13, UC-03) in the stored sample of a source
    the composition needs, that have no person's choice yet, or whose question the system owner has not answered. Each
    needs a person's choice among the five; the composition cannot be sent for approval before."""
    from di.connectors import discover, mapping_suggest

    s, org = ctx.session, row["org_unit_id"]
    reg_type = {(e.id, e.version): e.system_type for e in adapter_repo.entries(s, org)}
    sources = _sources(s, org)
    out: list[str] = []
    for _name, kind, key in _wanted_systems(row, pack):
        found = sorted((m, x["id"]) for x in sources if (m := _match(x, key, kind, reg_type)) is not None)
        if not found:
            continue
        sid = found[0][1]
        live = {(d["resource"] or "", d["src"]): d for d in mapping_decisions.of_source(s, sid)}
        for res, recs in discover._samples(s, sid).items():
            for f in mapping_suggest.field_paths([p for _, p in recs]):
                if mapping_suggest.hint_of(sid, f) is None:
                    continue
                d = live.get((res, f)) or live.get(("", f))
                if d is None:
                    out.append(
                        f"A mapping field ({f} of {sid}) has no decision yet: accept it, choose another field, accept it "
                        "with a conversion, mark it not needed or ask the system owner."
                    )
                elif d["decision"] == "asked_owner":
                    out.append(f"A mapping field ({f} of {sid}) is still waiting for its owner.")
    return out


@guard("compose.submit")
def submit_guard(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | tuple[str, str, dict[str, Any]] | None:
    if bad := _editable_guard(i, ctx):
        return bad
    row = _row(i, ctx)
    pack = _pack(row, ctx)
    left = [*core.blocking(row["steps"], _ops(row), pack), *_undecided(row, pack, ctx)]
    return ("conflict", "Not ready to submit: " + " ".join(left), {"blocking": left}) if left else None


@implement("compose.submit")
def submit(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    row = _row(i, ctx, for_update=True)
    ver = _version(ctx, row, "submitted", submitted_by=ctx.actor.id)
    return {"id": row["id"], "status": "submitted", "version": ver, "log": f"Submitted composition {row['id']} for approval"}


# ---------------------------------------------------------------- send back
@guard("compose.sendBack")
def send_back_guard(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | None:
    if bad := _reach(i, ctx):
        return bad
    if bad := _wanted(_row(i, ctx), ("submitted",), "The composition is not waiting for approval."):
        return bad
    return (
        None
        if i["step"] in core.MAKER_STEPS
        else ("validation_error", f"A step to send back is one of {', '.join(core.MAKER_STEPS)}.")
    )


@implement("compose.sendBack")
def send_back(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    row = _row(i, ctx, for_update=True)
    if row["status"] != "submitted":  # sent back or approved by someone else between the guard and this lock
        raise ActionError("conflict", "The composition is not waiting for approval.")
    note: dict[str, Any] = {"reason": i["reason"].strip(), "by": ctx.actor.id, "at": ctx.now.isoformat()}
    if i.get("node_id"):
        note["node_id"] = i["node_id"]
    steps = {**row["steps"], i["step"]: {**row["steps"].get(i["step"], {}), "state": "sent_back", "note": note}}
    ver = _version(ctx, row, "sent_back", steps=steps)
    return {
        "id": row["id"],
        "status": "sent_back",
        "version": ver,
        "log": f"Sent composition {row['id']} back at step {i['step']}",
    }


# ---------------------------------------------------------------- approve
@guard("compose.approve")
def approve_guard(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | tuple[str, str, dict[str, Any]] | None:
    if bad := _reach(i, ctx):
        return bad
    row = _row(i, ctx)
    if bad := _wanted(row, ("submitted",), "The composition is not waiting for approval."):
        return bad
    if ctx.actor.id in {row["created_by"], row["submitted_by"], *row["editors"]}:
        return "conflict", MAKER_CHECKER
    left = core.blocking(row["steps"], _ops(row), _pack(row, ctx))
    return ("conflict", "Not ready to approve: " + " ".join(left), {"blocking": left}) if left else None


def _apply_overlay(row: dict[str, Any], ctx: CallContext) -> None:
    ops = [o.model_copy(update={"by": o.by or row["created_by"]}) for o in _ops(row)]
    if not ops:
        return
    ref = {"pack_key": row["pack_key"], "org_unit_id": row["org_unit_id"]}
    cur = overlay_repo.get(ctx.session, row["pack_key"], row["org_unit_id"], for_update=True)
    if cur is not None and cur.status == "review":
        raise ActionError("conflict", "A customer overlay for this pack is waiting for approval: decide it first.")
    overlays.save({**ref, "ops": ops_json(ops)}, ctx)
    ctx.session.execute(  # the composition's maker is the overlay's maker; this actor is its checker
        text("UPDATE customer_overlay SET status = 'review', maker = :m WHERE pack_key = :p AND org_unit_id = :o"),
        {"m": row["created_by"], "p": row["pack_key"], "o": row["org_unit_id"]},
    )
    overlays.approve(ref, ctx)


def _current_maps(ctx: CallContext, source_id: str) -> list[list[str]]:
    stored = ctx.session.execute(
        text("SELECT rows FROM field_mapping WHERE source_id = :s ORDER BY version DESC LIMIT 1"), {"s": source_id}
    ).scalar_one_or_none()
    return [list(r["show"]) for r in stored if r.get("show")] if stored else [list(m) for m in mapping.starting_maps(source_id)]


def _apply_mapping(row: dict[str, Any], ctx: CallContext) -> int:
    accepted: dict[str, list[list[str]]] = {}
    for f in (row["steps"].get("mapping") or {}).get("fields") or []:
        if f.get("state") == "accepted":
            accepted.setdefault(f["source_id"], []).append([str(x) for x in f["row"]])
    for sid, rows in accepted.items():
        taken = {(r[0], r[2]) for r in rows}
        maps = [m for m in _current_maps(ctx, sid) if (str(m[0]), str(m[2])) not in taken] + rows
        try:
            mapping.save_version(ctx.session, sid, maps, ctx.actor.id, f"Composition {row['id']} approved", ctx.now)
        except ValueError as e:
            raise ActionError("validation_error", f"The mapping for {sid} cannot be saved: {e}") from e
    return len(accepted)


@implement("compose.approve")
def approve(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    row = _row(i, ctx, for_update=True)
    if row["status"] != "submitted":  # sent back or approved by someone else between the guard and this lock
        raise ActionError("conflict", "The composition is not waiting for approval.")
    _apply_overlay(row, ctx)
    sources = _apply_mapping(row, ctx)
    steps = {**row["steps"], "approve": {"state": "done"}}
    ver = _version(ctx, row, "approved", steps=steps, approved_by=ctx.actor.id)
    return {
        "id": row["id"], "status": "approved", "version": ver, "mapping_sources": sources,
        "log": f"Approved composition {row['id']} (v{ver}): changes, mapping and stage settings apply together",
    }  # fmt: skip


# ---------------------------------------------------------------- stage agents (P9-8.20)
LEVELS = ("recommend", "limits", "alone")  # the Autonomy of I-7
BOUNDS = "The confidence threshold is between 65 % and 85 %."
DEFAULT_SHARE = 20
DEFAULT_THRESHOLD = 0.75
NEEDS_REPORT = "Run the replay before publishing."
_LIMIT_KEYS = ("value_limit", "bulk_limit")


def _num(v: Any) -> bool:
    return isinstance(v, int | float) and not isinstance(v, bool)


def _stage_keys(row: dict[str, Any], ctx: CallContext) -> list[str]:
    return [st.key for st in _pack(row, ctx).stages] or list(STAGE_KEYS)


def _stage_problem(stages: Any, keys: list[str]) -> str | None:
    """The first thing wrong with the stage rows, in the person's words; None when they are fine."""
    if not isinstance(stages, list) or not stages:
        return "Name at least one stage."
    seen: set[str] = set()
    for r in stages:
        if not isinstance(r, dict):
            return "Each stage is a row with a stage, an agent and an autonomy."
        key = str(r.get("stage"))
        if key not in keys:
            return f"The {key} stage is not one of {', '.join(keys)}."
        if key in seen:
            return f"The {key} stage is set twice."
        seen.add(key)
        if r.get("autonomy") not in LEVELS:
            return f"The autonomy of the {key} stage is one of {', '.join(LEVELS)}."
        agent = r.get("agent_id")
        if not isinstance(agent, str) or not agent.strip() or len(agent) > 80:
            return f"The {key} stage needs an agent."
        limits = r.get("limits")
        if limits is None:
            continue
        if r["autonomy"] != "limits":
            return f"The {key} stage has limits, which apply only to Act within limits."
        if not isinstance(limits, dict) or set(limits) - set(_LIMIT_KEYS) or any(not _num(v) or v < 0 for v in limits.values()):
            return f"The limits of the {key} stage are a value limit and a bulk limit, each zero or more."
    return None


@guard("compose.setStageAgents")
def stage_agents_guard(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | None:
    if bad := _editable_guard(i, ctx):
        return bad
    t, (lo, hi) = i["threshold"], core.THRESHOLD_RANGE
    if not _num(t) or not lo <= t <= hi:
        return "validation_error", BOUNDS
    problem = _stage_problem(i["stages"], _stage_keys(_row(i, ctx), ctx))
    return ("validation_error", problem) if problem else None


@implement("compose.setStageAgents")
def set_stage_agents(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    """Store the stage settings in the composition. `agent_id` is kept as a label only; nothing here writes the agent registry
    (`agent_identity`): its autonomy (read, propose, act) is global and Admin's alone."""
    row = _row(i, ctx, for_update=True)
    th = float(i["threshold"])
    settings, ops = [], []
    for n, r in enumerate(i["stages"], 1):
        limits = {k: r["limits"][k] for k in _LIMIT_KEYS if k in r["limits"]} if r.get("limits") else None
        base = {
            "stage": r["stage"],
            "agent_id": r["agent_id"].strip(),
            "autonomy": r["autonomy"],
            **({"limits": limits} if limits else {}),
        }
        settings.append({**base, "threshold": th})
        ops.append({"id": f"sa-{n}", "op": "stageAgent.set", **base})
    ops.append({"id": f"sa-{len(ops) + 1}", "op": "param.set", "path": "confidence_threshold", "value": th})
    steps = {**row["steps"], "agents": {**row["steps"].get("agents", {}), "settings": settings}}
    _save(ctx, row["id"], change_set={**row["change_set"], "stage_ops": ops}, steps=steps, editors=_editors(row, ctx))
    return _out(_row(i, ctx)) | {"threshold": th, "log": f"Set the agents of {len(settings)} stages of composition {row['id']}"}


with_stage_settings = core.with_stage_settings  # moved to the pure core (28 Nov 2026), where the stage chain reads it


def _runs_as(stage: str, agents: dict[str, Any]) -> list[dict[str, Any]]:
    """The registry agents (`agent_identity`) of the chain stages that take this pack stage's autonomy or threshold. An id the
    registry does not hold is listed without a name, not enabled. `autonomy` is the registry's (read, propose, act): global,
    Admin's, never written from a composition."""
    out = []
    for aid in chain.agents_of(stage):
        a = agents.get(aid)
        out.append({
            "id": aid, "name": a.name if a else None, "enabled": bool(a.enabled) if a else False,
            "autonomy": a.autonomy if a else None,
        })  # fmt: skip
    return out


# ---------------------------------------------------------------- publish (P9-8.20)
def _flow(row: dict[str, Any], ctx: CallContext) -> Any:
    return flow_repo.flow_for(ctx.session, row["pack_key"], row["org_unit_id"])


def _report(f: Any, ctx: CallContext) -> dict[str, Any] | None:
    """The replay report of the flow's draft (I-16 `ReplayReport` as stored), or None before a replay is done."""
    run = rollout_repo.done_replay(ctx.session, f.id, f.dver)
    got = replay_repo.get_run(ctx.session, run) if run is not None else None
    return dict(got["report"]) if got and got["report"] else None


def _share(i: dict[str, Any]) -> tuple[str, str] | None:
    sh = i.get("share")
    if sh is None:
        return None
    if not _num(sh) or int(sh) != sh or not 1 <= sh <= 99:
        return "validation_error", "The share is a whole number from 1 to 99 (the canary widens in the Modeler)."
    return None


def _region(i: dict[str, Any], row: dict[str, Any], ctx: CallContext) -> tuple[str, str] | None:
    region = str(i.get("region") or "").strip()
    if not region:
        return "validation_error", "Name the region the canary runs in."
    every = units(ctx.session)
    # an org unit: inside the composition's own subtree, and one this person sees
    if region in every and (region not in subtree(every, row["org_unit_id"]) or not _org_ok(ctx, region)):
        return _boundary(region)
    return None  # anything else is a market, a case fact


@guard("compose.publish")
def publish_guard(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | None:
    if ctx.preparer:
        return "approval_required", "A composition is published only by a person."
    if bad := _reach(i, ctx):
        return bad
    row = _row(i, ctx)
    if bad := _wanted(row, ("approved",), "Only an approved composition is published, and only once."):
        return bad
    if bad := _share(i) or _region(i, row, ctx):
        return bad
    f = _flow(row, ctx)
    if f is None or f.status != "shadow":
        return "conflict", f"Approve the {row['pack_key']} decision flow of {row['org_unit_id']} into shadow before publishing."
    if _report(f, ctx) is None:
        return "conflict", NEEDS_REPORT
    body = {"flow_id": f.id, "region": str(i["region"]).strip(), "share": int(i.get("share") or DEFAULT_SHARE)}
    return rollout_actions.start_guard(body, ctx)  # the rollout's own refusals (its maker-checker) before anything is written


def _pct(x: Any) -> str:
    return f"{float(x):+.1f} %"


def _report_line(rep: dict[str, Any]) -> str:
    up = rep.get("uplift") or {}
    lo, hi = up.get("band80") or (0, 0)
    return (
        f"Replay of {rep.get('n_items', 0)} past items over {rep.get('days', 0)} days: "
        f"{rep.get('straight_through_pct', 0):g} % went straight through, {rep.get('approvals_per_day', 0):g} approvals and "
        f"{rep.get('exceptions_per_day', 0):g} exceptions a day; modelled uplift {_pct(up.get('conservative', 0))} "
        f"(80 % band {_pct(lo)} to {_pct(hi)})."
    )


def _report_facts(rep: dict[str, Any]) -> str:
    mix = "\n".join(f"{m['route']}: actual {m['actual_pct']:g} %, flow {m['flow_pct']:g} %" for m in rep.get("route_mix") or [])
    return _report_line(rep) + ("\nRoute mix:\n" + mix if mix else "")


_REPORT_KEYS = (
    "run_id", "n_items", "n_decided", "days", "route_mix", "straight_through_pct", "approvals_per_day", "exceptions_per_day", "uplift",
)  # fmt: skip


@implement("compose.publish")
def publish(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    row = _row(i, ctx, for_update=True)
    if row["status"] != "approved":  # published by someone else between the guard and this lock
        raise ActionError("conflict", "Only an approved composition is published, and only once.")
    f = _flow(row, ctx)
    rep = _report(f, ctx) if f is not None else None
    if f is None or rep is None:
        raise ActionError("conflict", NEEDS_REPORT)
    body = {"flow_id": f.id, "region": str(i["region"]).strip(), "share": int(i.get("share") or DEFAULT_SHARE)}
    as_me = CallContext(
        actor=ctx.actor, session=ctx.session, confirmed=ctx.confirmed, now=ctx.now
    )  # the pattern of proposal.accept
    r = invoke("rollout.startCanary", body, as_me)
    if not r["ok"]:
        e = r["error"]
        raise ActionError(e["code"], e["message"], {k: v for k, v in e.items() if k not in ("code", "message")} or None)
    facts = _report_facts(rep)
    words = stop_explainer.explain(ctx, facts, lambda t: stop_reasons.check_text(t, facts))
    steps = {**row["steps"], "publish": {"state": "done"}}
    ver = _version(ctx, row, "published", steps=steps, published_by=ctx.actor.id)
    return {
        "id": row["id"], "status": "published", "version": ver, "rollout": r["output"], "report": {k: rep.get(k) for k in _REPORT_KEYS},
        "text": words or _report_line(rep), "by_model": words is not None,
        "log": f"Published composition {row['id']} (v{ver}): canary in {body['region']} at {body['share']} %",
    }  # fmt: skip


# ---------------------------------------------------------------- history (P9-8.20)
guard("compose.history")(get_guard)


@implement("compose.history")
def history_of(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    row, s = _row(i, ctx), ctx.session
    versions = [
        {"version": v.version, "status": v.status, "by": v.by, "at": v.at.isoformat() if v.at else None}
        for v in s.execute(
            text('SELECT version, status, "by", "at" FROM composition_version WHERE composition_id = :c ORDER BY version'),
            {"c": row["id"]},
        )
    ]  # fmt: skip
    f = _flow(row, ctx)
    rows = s.execute(
        text(
            "SELECT seq, action, actor, at FROM action_journal WHERE NOT undone AND ("
            "(action LIKE 'compose.%' AND (input->>'id' = :c OR output_ref->>'id' = :c)) "
            "OR (CAST(:f AS text) IS NOT NULL AND action LIKE 'rollout.%' AND input->>'flow_id' = CAST(:f AS text))) ORDER BY seq"
        ),
        {"c": str(row["id"]), "f": str(f.id) if f is not None else None},
    )
    journal = [{"seq": r.seq, "action": r.action, "actor": r.actor, "at": r.at.isoformat() if r.at else None} for r in rows]
    rep = _report(f, ctx) if f is not None else None
    live = [rollout_actions._view(r) for r in rollout_repo.rollouts_of(s, f.id, ("canary", "paused"))] if f is not None else []
    publish_info = {
        "flow_id": f.id if f is not None else None, "flow_status": f.status if f is not None else None,
        "flow_stage": rollout_actions.current_stage(s, f) if f is not None else None,
        "report": {k: rep.get(k) for k in _REPORT_KEYS} if rep else None, "rollouts": live,
    }  # fmt: skip
    saved = {str(x["stage"]): x for x in core.stage_settings(row["steps"])}
    agents = {a.id: a for a in agent_registry.all_agents(s)}
    stages = [
        {"stage": st.key, "label": STAGE_LABELS[st.key], "agent_id": saved.get(st.key, {}).get("agent_id", st.agent),
         "autonomy": saved.get(st.key, {}).get("autonomy", st.autonomy), "limits": saved.get(st.key, {}).get("limits"),
         "runs_as": _runs_as(st.key, agents)}
        for st in _pack(row, ctx).stages
    ]  # fmt: skip
    threshold = next((x["threshold"] for x in saved.values() if _num(x.get("threshold"))), DEFAULT_THRESHOLD)
    return {
        "id": row["id"], "status": row["status"], "versions": versions, "journal": journal, "publish": publish_info,
        "stages": stages, "threshold": threshold,
    }  # fmt: skip
