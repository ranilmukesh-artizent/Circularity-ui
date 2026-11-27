"""`workflow.author`: a workflow draft from a sentence (plan 9, P9-8.12; enabler `workflow_author`, R16, golden rule 10).

    workflow.author {prompt, answers?}   risk "draft", perm manageWorkflows, agents may call it

    author(ctx, prompt, answers, loop) -> AuthorResult
        1. The keyword planner (`workflow.plan`'s, without its own model call) reads the sentence. Its questions about the type,
           the system, the delivery or the decision flow go back unchanged (`status: questions`); the questions with a default
           (trigger, blocks, handling, retries, alert) are not asked again here: their defaults are taken, as "Use defaults".
        2. With a model (`playbooks.workflow_author`, router role `author`) the model drafts the graph as typed output. Code
           checks it: the typed shape (`di.workflow.graph_model`: kinds, refs, each block's settings), the structure, the sources
           the caller may read or write, the trigger, and `workflow.validate`'s graph rules with the source's real fields. Every
           error goes back as `(node, field, message)`: at most three repair rounds (four tries), then `handed_over` with the
           errors and no draft. With no model, the planner's graph stands (`by_model: false`).
        3. A valid graph becomes a workflow in status draft (`workflow.create`), is test run dry (`workflow.testRun`) and is
           saved with `workflow.draft.save`, every node `ai: 1`.
Owns: the orchestration and the checks of the chain. Never does: publish (`workflow.publish` is forbidden to agents), run a
workflow for real, or put a record of any source in a prompt. The sentence is data: it reaches only the fenced description of
the prompt. Where the planner cannot find the field a sentence names ("records without a serial"), the filter is left without a
rule and `notes` says so; no field is invented.
"""

import difflib
import re
from dataclasses import asdict, dataclass, field, replace
from typing import Any

from pydantic import BaseModel

from di.repositories.common import SOURCES
from di.services.actions import workflow_builder as wb
from di.services.actions import workflows as wf
from di.services.actions.pipeline import CallContext, invoke
from di.services.actions.registry import ACTIONS, ActionDef, ActionError, guard, implement
from di.services.agents.loop import AgentLoop
from di.services.agents.playbooks.workflow_author import AuthorDraft, ModelDrafter
from di.workflow import blocks, graph_model, live

MAX_TRIES = 4  # the first draft and three repair rounds
ESSENTIAL = frozenset({"type", "system", "delivery", "decision"})  # questions that only a person can answer
ACTIONS.setdefault(
    "workflow.author",
    ActionDef(id="workflow.author", title="Author a workflow draft", verb="draft a workflow", risk="draft",
              perm="manageWorkflows",
              scope="none", input={"prompt": {"req": True, "t": "string"}, "answers": {"req": False, "t": "object"}},
              desc="Draft a workflow from a sentence: checked, test run dry and saved as a draft. It is never published."),
)  # fmt: skip
_FILTER = re.compile(
    r"\b(?:drop|discard|skip|exclude|reject|filter out)\s+(?:all\s+|the\s+)?(?:records|rows|returns|items)\s+"
    r"(?:with no|without|missing|lacking|that lack)\s+(?:an?\s+|the\s+)?"
    r"([a-z][a-z_ ]{1,30}?)(?:\s+(?:and|then|or)\b|[.,;]|$)"
)


@dataclass
class AuthorResult:
    status: str  # drafted, questions, handed_over, blocked, redirect
    graph: dict[str, Any] | None = None
    rounds: int = 0
    errors: list[dict[str, Any]] = field(default_factory=list)
    test_run: dict[str, Any] | None = None
    draft_id: str | None = None
    questions: list[dict[str, Any]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    trigger: dict[str, Any] | None = None
    name: str | None = None
    by_model: bool = False
    workflow_id: str | None = None


def _err(message: str, node: str | None = None, field_: str = "") -> dict[str, Any]:
    return {"node": node, "field": field_, "message": message}


# ---------------------------------------------------------------- the sentence
def named_unreadable(prompt: str, ctx: CallContext) -> list[str]:
    """Names of the systems the sentence names that the workbench can neither read from nor write to."""
    hits, _ = wb._systems(wb._norm(prompt))
    ok = set(wb.readable(ctx)) | set(wb.writable(ctx))
    return [SOURCES[sid]["name"] for sid, _ in hits if sid in SOURCES and sid not in ok]


def _filter_word(prompt: str) -> str | None:
    m = _FILTER.search(wb._norm(prompt))
    return m.group(1).strip() if m else None


def _resolve_field(ctx: CallContext, sid: str | None, word: str) -> str | None:
    """The field of the source's records the word names (the word itself, or its closest match), else None."""
    names = sorted(f for f in (live.fields(ctx.session, sid, live.mappings(ctx.session)) or set()) if "." not in f) if sid else []
    key = word.replace(" ", "_").lower()
    if key in names:
        return key
    low = {n.lower(): n for n in names}
    near = [n for n in low if key in n or n in key] or difflib.get_close_matches(key, list(low), 1, 0.75)
    return low[near[0]] if near else None


# ---------------------------------------------------------------- the checks
def graph_errors(ctx: CallContext, g: dict[str, Any], plan: dict[str, Any]) -> list[dict[str, Any]]:
    """What the caller's own rules say about an engine graph: sources, then `workflow.validate`'s checks."""
    out: list[dict[str, Any]] = []
    read, write = set(wb.readable(ctx)), set(wb.writable(ctx))
    for n in g["nodes"]:
        if n["k"] == "conn" and n["ref"] in SOURCES and n["ref"] not in read:
            out.append(_err(f"{SOURCES[n['ref']]['name']} ({n['ref']}) cannot be read by the caller.", n["id"], "ref"))
        if n["k"] == "wconn" and n["ref"] in SOURCES and n["ref"] not in write:
            out.append(_err(f"{SOURCES[n['ref']]['name']} ({n['ref']}) cannot be written to by the caller.", n["id"], "ref"))
        if n["k"] == "conn" and plan.get("src") and plan["type"] == "ingest" and n["ref"] != plan["src"]:
            out.append(_err(f"The description asks for {plan['src']}, not {n['ref']}.", n["id"], "ref"))
    if out:
        return out
    v = wf.validate(blocks.compact_graph(g), "pipe", ctx.session)
    return [_err(x["msg"], x["id"]) for x in v if x["sev"] == "error"]


def _trigger_errors(plan: dict[str, Any], trig: dict[str, Any]) -> list[dict[str, Any]]:
    if trig["t"] == "schedule" and not trig.get("min"):
        return [_err("A schedule trigger needs `min`, the minutes between runs.", None, "trigger")]
    if not wb._trig_ok(plan["type"], plan.get("src"), trig):
        return [_err(f"{wf.trig_text(trig)} does not fit this workflow.", None, "trigger")]
    return []


def check_draft(ctx: CallContext, d: AuthorDraft, plan: dict[str, Any]) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    """The engine graph of a model's draft and no errors, or None and every error found (the typed shape first)."""
    raw = d.graph.model_dump(mode="json") if isinstance(d.graph, BaseModel) else d.graph
    typed, errs = graph_model.parse(raw)
    if typed is None:
        return None, errs
    errs = graph_model.structure_errors(typed)
    g = graph_model.engine_graph(typed)
    errs += _trigger_errors(plan, d.trigger.model_dump(exclude_none=True))
    errs += [] if errs else graph_errors(ctx, g, plan)
    return (None, errs) if errs else (g, [])


# ---------------------------------------------------------------- the planner's graph
def planner_graph(ctx: CallContext, plan: dict[str, Any], word: str | None, notes: list[str]) -> dict[str, Any]:
    """The planner's graph marked as an assistant's; a filter gets the rule the sentence states, when its field exists."""
    g: dict[str, Any] = {
        "nodes": [dict(n) | {"ai": 1} for n in plan["graph"]["nodes"]],
        "edges": [dict(e) for e in plan["graph"]["edges"]],
    }
    flt = next((n for n in g["nodes"] if n["k"] == "xf" and n["ref"] == "x_filter"), None)
    if flt is not None and word:
        f = _resolve_field(ctx, plan.get("src"), word)
        if f:
            flt["cfg"] = {"condition": [{"field": f, "check": "present"}]}
        else:
            notes.append(
                f"No field called {word} in the records of {plan.get('src')}: the filter has no rule yet. Set it in the "
                "inspector."
            )
    out: dict[str, Any] = blocks.compact_graph(g)
    return out


# ---------------------------------------------------------------- the action
def _sources(ctx: CallContext) -> list[dict[str, str]]:
    ids = sorted(set(wb.readable(ctx)) | set(wb.writable(ctx)))
    return [{"id": i, "name": SOURCES[i]["name"]} for i in ids]


def _reading(plan: dict[str, Any], word: str | None) -> dict[str, Any]:
    return {"type": plan["type"], "source": plan.get("src"), "delivery": plan.get("ch"), "trigger": plan["trigger"],
            "blocks_asked": plan["diff"]["added"], "name": plan["name"], "filter_field": word}  # fmt: skip


def _run(ctx: CallContext, action: str, inp: dict[str, Any]) -> Any:
    r = invoke(action, inp, replace(ctx, idem_key=None))
    if not r["ok"]:
        raise ActionError(r["error"]["code"], r["error"]["message"])
    out = r["output"]
    if isinstance(out, dict) and "held" in out and "reasons" in out:  # a call the pipeline held (a test run has its own `held`)
        raise ActionError("approval_required", f"A person must approve {action} first (proposal {out['held']}).")
    return out


def _test_summary(r: dict[str, Any]) -> dict[str, Any]:
    order, counts = r.get("order") or [], r.get("counts") or {}
    first, last = (order[0], order[-1]) if order else (None, None)
    held = r.get("held")
    return {
        "status": r["status"], "in": counts.get(first, {}).get("out", 0), "out": counts.get(last, {}).get("in", 0),
        "held": held if isinstance(held, int) else len(held or []), "note": r.get("note"),
    }  # fmt: skip


def _save(ctx: CallContext, plan: dict[str, Any], g: dict[str, Any], name: str, trig: dict[str, Any], res: AuthorResult) -> None:
    created = _run(ctx, "workflow.create", {**plan["create"], "name": name, "graph": g})
    res.workflow_id = wid = created["id"]
    try:
        res.test_run = _test_summary(_run(ctx, "workflow.testRun", {"id": wid}))
    except ActionError as e:
        res.notes.append(f"The test run did not start: {e.message}")
    keep = {k: v for k, v in plan["save"].items() if k in ("owner", "retries", "alert")}
    _run(ctx, "workflow.draft.save", {"id": wid, "graph": g, "name": name, "trig": trig, **keep})
    res.draft_id, res.graph, res.trigger, res.name, res.status = wid, g, trig, name, "drafted"


def author(ctx: CallContext, prompt: str, answers: dict[str, Any] | None = None, loop: AgentLoop | None = None) -> AuthorResult:
    ans = dict(answers or {})
    word = _filter_word(prompt)
    if word and "steps" not in ans:
        ans["steps"] = sorted({*wb.read_prompt(prompt)["steps_want"], "x_filter"})
    planned = wb.plan(prompt, ans, ctx, use_model=False)  # the keyword planner first; its questions go back unchanged
    if planned["status"] == "questions":
        if any(q["id"] in ESSENTIAL for q in planned["questions"]):
            return AuthorResult("questions", questions=planned["questions"], notes=planned["notes"])
        planned = wb.plan(prompt, ans | {"_defaults": True}, ctx, use_model=False)
    if planned["redirect"]:
        return AuthorResult("redirect", notes=[planned["redirect"]["reason"]])
    plan = planned["plan"]
    if planned["status"] != "ready" or plan is None:
        return AuthorResult("blocked", errors=[_err(m, None, "plan") for m in planned["notes"]], notes=planned["notes"])
    res = AuthorResult("handed_over", notes=list(planned["notes"]))
    drafter = ModelDrafter(ctx, loop)
    graph: dict[str, Any] | None = None
    name, trig = plan["name"], plan["trigger"]
    try:
        while res.rounds < MAX_TRIES:
            d = drafter.draft(prompt, _reading(plan, word), _sources(ctx), res.errors)
            if d is None:
                break
            res.rounds += 1
            graph, res.errors = check_draft(ctx, d, plan)
            if graph is not None:
                name, trig, res.by_model = d.name, d.trigger.model_dump(exclude_none=True), True
                break
    finally:
        drafter.close()
    if graph is None:
        # the safety net (R16; 27 Nov 2026): no model answered, or every draft of the model failed the checks. The planner's
        # graph goes through the same checks, so a request still ends in a draft; `by_model` stays false and a note says so.
        if res.rounds:
            res.notes.append(
                f"The language model's draft did not pass the checks after {res.rounds} tries, so this draft is the planner's."
            )
        graph = planner_graph(ctx, plan, word, res.notes)
        res.errors = graph_errors(ctx, graph, plan)
        graph = None if res.errors else graph
    if graph is None:
        return res
    _save(ctx, plan, graph, name, trig, res)
    return res


@guard("workflow.author")
def author_guard(i: dict[str, Any], ctx: CallContext):
    if len(i["prompt"]) > 2000:
        return "validation_error", "Keep the description under 2,000 characters."
    if not isinstance(i.get("answers") or {}, dict):
        return "validation_error", '"answers" must be an object.'
    if gone := named_unreadable(i["prompt"], ctx):
        return "validation_error", f"{', '.join(gone)} cannot be read from or written to by the workbench, so no draft is made."
    return None


@implement("workflow.author")
def author_action(i: dict[str, Any], ctx: CallContext):
    return asdict(author(ctx, i["prompt"], i.get("answers") or None))
