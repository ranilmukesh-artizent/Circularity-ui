"""Configuration agent actions (plan 9, P9-2.7; registry entry I-13; story X-02): describe a business, get a change set.

    config.read   read  {text, org_unit_id}                  the reading log, the matched pack and its one question
    config.draft  act   {text, org_unit_id, answer?}         the change set, stored, and its overlay draft held as one proposal

Both need `managePacks` and the org unit in the person's tenants; agents may call them. `config.draft` needs the answer to the
pack's question (an option id or `skip`). It stores the change set (`config_change_set`) and saves it as the org's overlay draft
through `overlay.save` prepared by the agent `recover-config` (autonomy `propose`), so the pipeline holds it as one proposal
(`agent_proposal`). Accepting it (`proposal.accept`, by a person other than the one who asked) saves the draft as that person;
submit, approve and publish are the overlay's maker-checker, which no agent may run (rule 10). A text over 4,000 characters is
refused. The text is data: only the typed controls it states reach an operation (`di.services.agents.config_agent`).
"""

import json
from typing import Any

from sqlalchemy import text

from di.repositories.orgs import units
from di.repositories.packs import active_pack
from di.services.actions.modeler import _boundary, _org_ok
from di.services.actions.pipeline import CallContext, invoke
from di.services.actions.registry import ACTIONS, ActionDef, ActionError, guard, implement
from di.services.agents.config_agent import (
    MAX_TEXT,
    ChangeSet,
    ChangeSetError,
    PackMatch,
    Reading,
    draft_change_set,
    match_pack,
    read_text,
)
from di.services.agents.playbooks import pack_author
from di.services.modeler.overlay import ops_json
from di.services.modeler.pack import Pack, pack_keys

_IN = {"text": {"req": True, "t": "string"}, "org_unit_id": {"req": True, "t": "string"}}
ACTIONS.setdefault(
    "config.read",
    ActionDef(id="config.read", title="Read a business description", verb="read a business description",
              desc="Read a description of a business: the controls it states, the closest pack and the one question to answer.",
              risk="read", perm="managePacks", scope="none", input=_IN),
)  # fmt: skip
ACTIONS.setdefault(
    "config.draft",
    ActionDef(id="config.draft", title="Draft a pack change set", verb="draft a pack change set",
              desc="Draft the customer changes a description asks for, as typed overlay operations held for a person to approve.",
              risk="act", perm="managePacks", scope="none", input={**_IN, "answer": {"t": "string"}}),
)  # fmt: skip


def _packs(ctx: CallContext, org: str) -> list[Pack]:
    return [active_pack(ctx.session, k, org) for k in pack_keys()]


def _refusal(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | None:
    if len(i["text"]) > MAX_TEXT:
        return "validation_error", f"The description is {len(i['text']):,} characters: keep it under {MAX_TEXT:,}."
    org = i["org_unit_id"]
    if org not in units(ctx.session):
        return "not_found", f"No org unit {org}."
    return None if _org_ok(ctx, org) else _boundary(org)


guard("config.read")(_refusal)
guard("config.draft")(_refusal)


def _failed(e: ChangeSetError) -> ActionError:
    return ActionError("validation_error", e.message, {"op_id": e.op_id} if e.op_id else None)


@implement("config.read")
def read(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    packs = _packs(ctx, i["org_unit_id"])
    try:
        cs = draft_change_set(i["text"], i["org_unit_id"], packs=packs, answer=None, drafter=pack_author.make_drafter(ctx))
    except ChangeSetError as e:
        raise _failed(e) from e
    reading = read_text(i["text"], packs).model_copy(update={"by_model": cs.by_model})
    match = match_pack(reading, i["text"], packs)
    if cs.by_model and match.key != cs.pack:  # the model chose the pack; the score shown is the text's against the best
        match = PackMatch(
            key=cs.pack,
            score=match.score,
            nearest_only=match.nearest_only,
            name=next((p.name for p in packs if p.key == cs.pack), ""),
        )
    return {"reading": reading.model_dump(mode="json"), "match": match.model_dump(mode="json"),
            "pack_names": {p.key: p.name for p in packs},
            "question": cs.question.model_dump(mode="json") if cs.question else None}  # fmt: skip


def _store(i: dict[str, Any], ctx: CallContext, reading: Reading, cs: ChangeSet) -> int:
    new_id: int = ctx.session.execute(
        text(
            "INSERT INTO config_change_set (org_unit_id, pack, base_version, reading, question, answer, ops, assumed, blocked, "
            "systems, kpis, created_by, created_at) VALUES (:o, :p, :v, CAST(:r AS jsonb), NULL, :a, CAST(:ops AS jsonb), "
            "CAST(:as AS jsonb), CAST(:b AS jsonb), CAST(:s AS jsonb), CAST(:k AS jsonb), :by, :at) RETURNING id"
        ),
        {
            "o": i["org_unit_id"], "p": cs.pack, "v": cs.base_version, "r": reading.model_dump_json(), "a": cs.answer,
            "ops": json.dumps(ops_json(cs.ops)), "as": json.dumps(cs.assumed),
            "b": json.dumps([b.model_dump() for b in cs.blocked]), "s": json.dumps([s.model_dump() for s in cs.systems]),
            "k": json.dumps(cs.kpis), "by": ctx.actor.id, "at": ctx.now,
        },
    ).scalar_one()  # fmt: skip
    return new_id


@implement("config.draft")
def draft(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    packs = _packs(ctx, i["org_unit_id"])
    try:
        cs = draft_change_set(
            i["text"], i["org_unit_id"], packs=packs, answer=i.get("answer") or None, drafter=pack_author.make_drafter(ctx)
        )
    except ChangeSetError as e:
        raise _failed(e) from e
    reading = read_text(i["text"], packs).model_copy(update={"by_model": cs.by_model})
    if cs.question is not None:
        raise ActionError("validation_error", "Answer the pack's question first (choose an option or skip).")
    if not cs.ops:
        raise ActionError("validation_error", "Nothing to propose: the description states no change to this pack.")
    cid = _store(i, ctx, reading, cs)
    n = (len(cs.ops), len(cs.assumed), len(cs.blocked))
    note = f"Drafted from a description for {cs.pack}: {n[0]} change(s), {n[1]} assumed, {n[2]} blocked."
    agent = CallContext(actor=ctx.actor, session=ctx.session, preparer=pack_author.AGENT_ID, now=ctx.now)
    r = invoke(
        "overlay.save", {"pack_key": cs.pack, "org_unit_id": i["org_unit_id"], "ops": ops_json(cs.ops), "note": note}, agent
    )
    if not r["ok"]:
        err = r["error"]
        raise ActionError(err["code"], err["message"], {k: v for k, v in err.items() if k not in ("code", "message")} or None)
    held = r["output"].get("held") if isinstance(r["output"], dict) else None
    ctx.session.execute(text("UPDATE config_change_set SET proposal_id = :p WHERE id = :i"), {"p": held, "i": cid})
    return {"change_set_id": cid, "proposal_id": held, "change_set": cs.model_dump(mode="json"),
            "log": f"Drafted {len(cs.ops)} change(s) for {cs.pack} at {i['org_unit_id']} and held them for approval"}  # fmt: skip
