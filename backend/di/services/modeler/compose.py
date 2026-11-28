"""The composition's pure core (plan 9, P9-8.17; G C8, C12): step states, the checks before a submit, the snapshot.

    new_steps() -> dict                      every step `todo`
    blocking(steps, ops, pack) -> list[str]  what stops a submit, in plain words; empty when the composition may go
    snapshot(row) -> dict                    what a `composition_version` keeps
    stage_settings(steps) -> list[dict]      the stage-agent settings the agents step holds
    with_stage_settings(pack, settings)      the pack with those settings on its stages (what the stage chain reads)
    stored_draft(pack_key, version, text)    the stored model draft of one of the pack's sample prompts, or None (plan 11, C1)
    write_stored_draft(...)                  adds one to `packs/stored_drafts/<pack_key>.json` (the build script's)

A composition is one approvable object: the change set (typed overlay operations, I-4), the mapping rows the owner accepted
(`steps.mapping.fields`) and the stage-agent settings (`steps.agents.settings`: stage, autonomy, confidence threshold). The five
steps are describe, mapping, agents, approve and publish; only the three before approve are the maker's.
`blocking` takes the pack in force (the overlay validator needs it): every step before approve is done, the operations validate
(`apply_overlay`: tighten only on locked guardrails, no compliance skip), no mapping field is still `asked_owner`, every stage
confidence threshold lies in 0.65 to 0.85 (the range of `di.services.agents.chain`).
Owns: those rules. Never does: touch the database, call a model, or approve anything: the actions
(`di.services.actions.compose`) store, and approval is a person's (rule 10, `FORBIDDEN_ACTIONS`).
"""

import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Literal

from di.services.modeler.overlay import OverlayError, OverlayOp, apply_overlay
from di.services.modeler.pack import PACKS_DIR, Pack

Step = Literal["describe", "mapping", "agents", "approve", "publish"]
STEPS: tuple[Step, ...] = ("describe", "mapping", "agents", "approve", "publish")
MAKER_STEPS: tuple[Step, ...] = ("describe", "mapping", "agents")
THRESHOLD_RANGE = (0.65, 0.85)  # the range of di.services.agents.chain (not imported: that module is the runtime's)


def new_steps() -> dict[str, dict[str, Any]]:
    return {s: {"state": "todo"} for s in STEPS}


def stage_settings(steps: Mapping[str, Any]) -> list[dict[str, Any]]:
    return list((steps.get("agents") or {}).get("settings") or [])


def with_stage_settings(pack: Pack, settings: Sequence[Mapping[str, Any]]) -> Pack:
    """The pack with a composition's stage settings on its stages (agent label, autonomy and confidence threshold): what the
    stage chain reads (`chain.stage_defs`). A stage the settings do not name is as the pack has it. Pure."""
    by = {str(x["stage"]): x for x in settings}

    def threshold(x: Mapping[str, Any], own: float) -> float:
        t = x.get("threshold")
        return float(t) if isinstance(t, int | float) and not isinstance(t, bool) else own

    stages = [
        st.model_copy(update={
            "agent": by[st.key].get("agent_id") or st.agent,
            "autonomy": by[st.key].get("autonomy") or st.autonomy,
            "confidence": threshold(by[st.key], st.confidence),
        }) if st.key in by else st
        for st in pack.stages
    ]  # fmt: skip
    return pack.model_copy(update={"stages": stages})


STORED_DIR = PACKS_DIR / "stored_drafts"


def normalise_prompt(text: str) -> str:
    """The sample-prompt comparison: whitespace trimmed and collapsed, case ignored."""
    return " ".join(text.split()).casefold()


def draft_key(text: str, version: str) -> str:
    """The key of a stored draft: a hash of the normalised prompt and the pack's version (a changed prompt or version misses)."""
    return hashlib.sha256(f"{version}\n{normalise_prompt(text)}".encode()).hexdigest()[:16]


def stored_draft(pack_key: str, version: str, text: str, directory: Path | None = None) -> dict[str, Any] | None:
    """The model draft stored for `text` at this pack version: the `ModelDraft` as a dict, to be checked like a live answer.
    None for any other text, a missing or unreadable file. Pure read."""
    try:
        doc = json.loads(((directory or STORED_DIR) / f"{pack_key}.json").read_text(encoding="utf-8"))
        hit = doc["drafts"][draft_key(text, version)]
    except (OSError, ValueError, KeyError, TypeError):
        return None
    draft = hit.get("draft") if isinstance(hit, dict) else None
    return draft if isinstance(draft, dict) else None


def write_stored_draft(
    pack_key: str, version: str, text: str, draft: Mapping[str, Any], built_at: str, directory: Path | None = None
) -> None:
    """Add (or replace) the stored draft of one sample prompt; other prompts and other versions in the file stay."""
    directory = directory or STORED_DIR
    path = directory / f"{pack_key}.json"
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        doc = {}
    drafts = doc.get("drafts") if isinstance(doc.get("drafts"), dict) else {}
    drafts[draft_key(text, version)] = {
        "prompt": " ".join(text.split()),
        "pack_version": version,
        "built_at": built_at,
        "draft": dict(draft),
    }
    directory.mkdir(parents=True, exist_ok=True)
    note = "Model drafts of the pack's sample prompts, built by scripts/build_stored_drafts.py. Do not edit."
    doc = {"pack": pack_key, "note": note, "drafts": drafts}
    path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _threshold_problems(steps: Mapping[str, Any]) -> list[str]:
    lo, hi = THRESHOLD_RANGE
    out = []
    for s in stage_settings(steps):
        t = s.get("threshold")
        if isinstance(t, int | float) and not lo <= t <= hi:
            out.append(f"The {s.get('stage')} confidence threshold {t:g} is outside {lo:g} to {hi:g}.")
    return out


def _unanswered(steps: Mapping[str, Any]) -> list[str]:
    fields = (steps.get("mapping") or {}).get("fields") or []
    return [
        f"A mapping field ({(f.get('row') or [''])[0]} of {f.get('source_id')}) is still waiting for its owner."
        for f in fields
        if f.get("state") == "asked_owner"
    ]


def _invalid(ops: Sequence[OverlayOp], pack: Pack) -> list[str]:
    try:
        apply_overlay(pack, ops)
    except OverlayError as e:
        return [f"The changes do not validate ({e.op_id}): {e.message}"]
    return []


def blocking(steps: Mapping[str, Any], ops: Sequence[OverlayOp], pack: Pack) -> list[str]:
    """What stops a submit, in this order: unfinished steps, the operations, mapping fields still asked, thresholds."""
    left = [f"Step {s} is not done." for s in MAKER_STEPS if (steps.get(s) or {}).get("state") != "done"]
    return [*left, *_invalid(ops, pack), *_unanswered(steps), *_threshold_problems(steps)]


def snapshot(row: Mapping[str, Any]) -> dict[str, Any]:
    """The state a version keeps: the text, the reading, the change set, the steps (with the mapping rows and stage settings)."""
    return {k: row[k] for k in ("text", "reading", "change_set", "steps", "pack_key", "org_unit_id", "base_version")}
