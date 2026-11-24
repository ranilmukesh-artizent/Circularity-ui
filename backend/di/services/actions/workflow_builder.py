"""Workflow Studio's AI workflow builder: the demo's draft (workflow.draft) and a guided planner (workflow.plan).

    workflow.draft  (the catalog's, risk "draft")  the demo's afWfDraft: the generated ingest graph for a source, with
                    the palette steps the description asks for (AF_WF_KW) inserted before the field mapping, checked
                    with the workflow checks; the steps (fixed or new) are the demo's `wfdiff` card. Nothing is saved.
    workflow.plan   (declared here, risk "read", no permission)  a person describes a workflow in words; the planner
                    reads what it can from the description, asks follow-up questions for what is missing or ambiguous,
                    and, once every slot is settled, returns a complete plan: a graph built from the blocks the
                    workflow needs to run (MINIMAL below) plus exactly the blocks the person asked for, wired where they
                    belong; its checks (always 0 errors), the trigger and run settings, a tailored name and description,
                    and every step with why it is there (required to run, or asked for). It does not start from the
                    standard template: optional blocks (a second ingestion channel, the source type's usual transform,
                    the error handler, audit log, event stream) are offered, never added unasked.

**MINIMAL, the blocks a workflow needs to run with 0 errors and 0 warnings:**
    ingest      the source's connector, one ingestion channel it delivers by (API gateway or event ingestion; the file
                steps for a file-only source), Validation & enrichment, the source's field mapping, the canonical model
                and the evidence snapshot (both fixed: Circularity places them)
    outbound    decision and human approval (fixed), the instruction envelope, the delivery method, a manifest for a
                file delivery, the target's write connector and the outcome (fixed)
    decision    the chosen decision flow's agent tools and fixed steps

**Agents never write** (AGENTS.md rule 10). The planner only proposes: it computes and returns; it saves nothing, so it
is a read (not journaled, no live-stream event per question). The person's own click on Create workflow runs
workflow.create and workflow.save through the pipeline with their permissions (manageWorkflows); `plan.create` and
`plan.save` are those two inputs.

**The planner's slots** (each question has id, text, kind, choices [{value, label, hint}], multi, default):
    type        ingest | out | dec | blank
    system      ingest: a readable source with a connected feed; out: a source Circularity writes to
    delivery    out: one of the channels the target accepts (DELIVER)
    decision    dec: standard | pool | gap (the three decision graphs)
    channels    ingest from a source that delivers by API and events: api | event | both (default: one channel)
    trigger     schedule:<min> | event | file | approval | case | manual, the valid ones per type, a default per type
    steps       palette transforms and branches relevant to the source (multi), ticked only from the description
                (the source type's usual transform is offered, marked as such, not added)
    handling    error handler, audit log, event stream (ingest); audit log, import log (outbound) (multi; none by
                default: none is needed to run)
    retries     0 | 1 | 3 | 5        alert   the four alert rules (di.services.actions.workflows.ALERTS)
    name, owner text, defaulting to the tailored name and the source's owner
Questions come in rounds: the type, then the system (and delivery or decision flow), then every unsettled detail at
once with its default; `answers._defaults` true accepts the defaults for the rest. A slot the description settled
unambiguously is never asked; a system it names that is not connected (or cannot be read or written as asked) is
said so in `notes`, with the closest real choices offered.

**Understanding the description** is deterministic (keywords and fuzzy matching over the real source names, vendors,
types, delivery methods, trigger words and step keywords). When GROQ_API_KEY is set (and ASK_PROVIDER is not none), a
language model is also asked to read the description into the same slots (one short JSON request through the groq SDK,
as di.services.ask.groq_model does); its answer only resolves what the keywords found but could not settle (see _merge_model),
never a slot the description does not mention, and every value is checked against the allowed choices. Any failure is
ignored. The key is never logged or returned.

Graph builders, the checks and the labels are di.services.actions.workflows' (not edited here): build() for the standard
template, validate() for the checks, label() for step names.
"""

import copy
import difflib
import json
import logging
import re
from typing import Any

from sqlalchemy import text

from di.repositories import workflows as studio
from di.repositories.common import SOURCES
from di.repositories.constants import MAP_TARGET, MAPPINGS, SRC_TYPES
from di.repositories.reference import channels
from di.services.actions import workflows as wf
from di.services.actions.pipeline import CallContext
from di.services.actions.registry import ACTIONS, ActionDef, guard, implement
from di.workflow import blocks

log = logging.getLogger("di.workflow_builder")

ACTIONS.setdefault(
    "workflow.plan",
    ActionDef(
        id="workflow.plan", title="Plan a workflow", risk="read", perm=None, scope="none", verb=None,
        desc="Read a workflow described in words, ask the follow-up questions it needs, and propose a complete, checked "
        "workflow. A proposal; nothing is saved.",
        input={"prompt": {"req": True, "t": "string"}, "answers": {"req": False, "t": "object"}},
    ),
)  # fmt: skip

# ---------------------------------------------------------------- the demo's draft (afWfDraft)
AF_WF_KW = [
    ("x_val", re.compile(r"valid|clean|check")),
    ("x_fx", re.compile(r"currenc|fx|inr|eur")),
    ("x_units", re.compile(r"unit|kw|weight")),
    ("x_utc", re.compile(r"utc|time ?zone|timestamp")),
    ("x_lookup", re.compile(r"code|grade|status map|lookup")),
    ("x_ident", re.compile(r"identit|match asset")),
    ("x_late", re.compile(r"late|order|duplicate|dedup")),
]


def af_wf_draft(src_id: str, desc: str | None) -> dict | None:
    """afWfDraft: the generated ingest with the asked-for steps between the step before the mapping and the mapping."""
    s = wf.src(src_id)
    if not s:
        return None
    g = wf.build({"k": "ingest", "src": src_id})
    d = str(desc or "").lower()
    want = [k for k, rx in AF_WF_KW if rx.search(d)]
    have = {n["ref"] for n in g["nodes"] if n["k"] == "xf"}
    for i, x in enumerate([x for x in want if x not in have and x != "x_val"]):
        m = next(n for n in g["nodes"] if n["k"] == "map")
        prev_e = next(e for e in g["edges"] if e["b"] == m["id"])
        nid = f"ai{i}"
        g["nodes"].append(wf._n(nid, "xf", x, m["x"], m["y"] + 90 + i * 80))
        prev_e["b"] = nid
        g["edges"].append({"id": f"ea{i}", "a": nid, "b": m["id"], "locked": False})
    for n in g["nodes"]:
        if n["k"] != "fixed":
            n["ai"] = 1
    v = wf.validate(g, "pipe")
    return {
        "src": src_id,
        "name": f"Ingest · {s['vendor']} (AI draft)",
        "graph": g,
        "steps": [{"id": n["id"], "label": wf.label(n), "kind": n["k"], "fixed": n["k"] == "fixed"} for n in g["nodes"]],
        "errors": [x["msg"] for x in v if x["sev"] == "error"],
        "warnings": [x["msg"] for x in v if x["sev"] == "warn"],
    }


def draft_text(src_id: str, d: dict) -> str:
    """The demo's answer under the wfdiff card (AF_INTENT_RUN['workflow.draft'])."""
    new, ne = len([s for s in d["steps"] if not s["fixed"]]), len(d["errors"])
    return (
        f"Drafted an ingest for {SOURCES[src_id]['name']} with {new} new steps from the palette; checks show {ne} "
        f"error{'' if ne == 1 else 's'}. Accepting creates a draft; it is never published by the agent."
    )


@guard("workflow.draft")
def draft_guard(i: dict[str, Any], ctx: CallContext):  # noqa: ARG001 - every guard takes (input, context)
    return None if wf.src(i["source_id"]) else ("not_found", "No source.")


@implement("workflow.draft")
def draft(i: dict[str, Any], ctx: CallContext):
    """The demo's output ({source_id, steps, errors}) plus the draft itself (the wfdiff card's data)."""
    d: Any = af_wf_draft(i["source_id"], i.get("desc"))
    d["prep"] = ctx.preparer
    return {"source_id": i["source_id"], "steps": len(d["steps"]), "errors": len(d["errors"]), "draft": d}


# ---------------------------------------------------------------- the planner: vocabulary
TYPES = {
    "ingest": ("Ingest pipeline", "One source system into a canonical model"),
    "out": ("Outbound instruction", "An approved decision sent to one target system"),
    "dec": ("Decision workflow (demo, read only)", "Business rules live in the Modeler"),
    "blank": ("Blank pipeline", "An empty canvas you wire yourself"),
}
DECISIONS = {
    "standard": ("Standard six-gate decision", "Evidence, gates, eligible routes and predictions, then a person approves."),
    "pool": ("Pool allocation", "Predictions for every eligible asset, then the pool optimiser allocates before approval."),
    "gap": ("Evidence gaps first", "Requests missing evidence and finds demand before the gates run."),
}
CH_LABEL = {"api": "Outbound API call", "event": "Event trigger", "file": "Interface file", "proc": "Process orchestration"}
CH_HINT = {
    "api": "A REST or SOAP request to the target",
    "event": "A webhook or queue message the target subscribes to",
    "file": "An interface file with a manifest; the import log is fetched afterwards",
    "proc": "Starts a workflow or approval task in the target",
}
CH_BY = {"api": "by API", "event": "as events", "file": "by file", "proc": "by process orchestration"}
ARRIVE = {
    "api": ("API only", "Polls the API through the API gateway"),
    "event": ("Events only", "Webhooks and queue events through event ingestion"),
    "both": ("API and events", "API gateway and event ingestion side by side"),
}
INTERVALS = (5, 15, 30, 60, 240, 1440)
TRIG_OK = {
    "ingest": ("schedule", "event", "file", "manual"),
    "out": ("approval", "event", "manual"),
    "dec": ("case", "event", "manual"),
    "blank": ("manual", "schedule", "event"),
}
TRIG_HINT = {
    "event": "Runs when the system sends an event",
    "file": "Runs when a file lands",
    "approval": "Runs when a person approves a decision",
    "case": "Runs for each case that asks for a decision",
    "manual": "Runs only when someone presses Run now",
}

# the palette steps the builder can add, in the order they run between validation and the field mapping (ingest) or
# between the instruction envelope and the delivery (outbound), each with the words that ask for it and a short phrase
STEP_ORDER = (
    "x_filter", "x_late", "x_ident", "x_utc", "x_units", "x_fx", "x_lookup", "x_enrich", "x_join", "x_expr", "x_agg",
    "x_flag", "x_branch",
)  # fmt: skip
STEP_KW: dict[str, re.Pattern] = {
    "x_filter": re.compile(r"\bfilter|\bonly (keep|rows|records)\b|\bexclude (rows|records)|\bkeep only\b"),
    "x_late": re.compile(r"\blate\b|out[- ]of[- ]order|duplicat|\bde-?dup|\breplay"),
    "x_ident": re.compile(r"identit|match (the )?assets?|asset match|resolve (the )?asset"),
    "x_utc": re.compile(r"\butc\b|time ?zones?|timestamps?"),
    "x_units": re.compile(r"\bunits?\b(?! of)|\bkw\b|\bweights?\b|unit conversion|normali[sz]e (the )?(units|measures)"),
    "x_fx": re.compile(r"currenc|\bfx\b|exchange rates?|\b(inr|eur|gbp|jpy)\b|to usd"),
    "x_lookup": re.compile(r"code[- ]?tables?|\blookups?\b|look up|\bcodes?\b|\bgrades?\b|status map"),
    "x_enrich": re.compile(r"enrich|master data|reference data"),
    "x_join": re.compile(r"\bjoin|\bcombine"),
    "x_expr": re.compile(r"expression|derived (field|value)|calculat|\bcompute"),
    "x_agg": re.compile(r"aggregat|group by|\btotals?\b|\bsum\b|roll ?up"),
    "x_flag": re.compile(r"bench[- ]?tests?|failed tests?|flag (failed|units)"),
    "x_branch": re.compile(r"\bbranch|if ?/ ?else|if-else|split (the )?(records|rows|flow)"),
}
PHRASE = {
    "x_filter": "filtering", "x_late": "de-duplication", "x_ident": "identity resolution", "x_utc": "UTC timestamps",
    "x_units": "unit normalisation", "x_fx": "currency conversion", "x_lookup": "code lookups", "x_enrich": "enrichment",
    "x_join": "a join", "x_expr": "derived fields", "x_agg": "aggregation", "x_flag": "bench-test flags",
    "x_branch": "a branch",
}  # fmt: skip
OUT_STEPS = ("x_filter", "x_lookup", "x_units", "x_fx", "x_utc", "x_expr")
HANDLING_KW = {
    "x_err": re.compile(r"error handl|\berrors?\b|invalid|reject|dead[- ]letter|failed records|bad (rows|records)"),
    "x_audit": re.compile(r"\baudit"),
    "x_pub": re.compile(r"event stream|\bpublish|\bkafka|model[- ]updated"),
    "x_cb": re.compile(r"import log|callback|notify|notification"),
}
HANDLING_LABEL = {
    "x_err": ("Error handler", "Holds records that fail validation, with the rule they broke, for reprocessing"),
    "x_audit": ("Audit log", "Writes run status, counts and timings to the audit log"),
    "x_pub": ("Publish to event stream", "Announces each model update so subscribers pick it up"),
    "x_cb": ("Import log and notification", "Fetches the target's import log, then tells the owning team"),
}
NEG = re.compile(
    r"\b(no|without|skip|skipping|drop|remove|exclude|excluding|not|don'?t (need|want|add|use)|never)\b"
    r"(?:(?!\b(?:with|and|but|plus|then|keep)\b)[\w\s/&-]){0,24}$"
)
GENERIC = {
    "a", "an", "the", "our", "my", "this", "that", "source", "system", "systems", "workflow", "pipeline", "ingest", "each",
    "every", "approval", "canonical", "model", "usd", "utc", "them", "it", "new", "data", "records", "events", "files",
    "file", "api", "me", "case", "cases", "decision", "decisions", "people", "person", "someone", "you", "us", "all",
    "any", "some", "there", "here", "outbound", "instruction", "instructions", "currency", "units", "late", "audit",
    "send", "push", "write", "deliver", "post", "run", "be", "get", "make", "build", "create", "read", "pull", "load",
    "import", "sync", "keep", "handle", "convert", "normalise", "normalize", "check", "do", "go", "use", "start",
    "stop", "one", "two", "both", "reach", "receive", "track", "monitor", "process", "turn", "feed", "it's",
    "minutes", "hours", "day", "week", "production", "prod", "test", "testing", "demo", "now", "later", "review",
}  # fmt: skip
STOP_TOKENS = {
    "and", "the", "for", "management", "services", "service", "data", "active", "core", "cloud", "network", "order",
    "field", "partner", "market", "sales", "lifecycle", "reverse", "logistics", "depot", "transportation", "device",
    "pricing", "carbon", "warehouse", "finance", "engineering", "product", "quality",
}  # fmt: skip


def _norm(t: str) -> str:
    return " " + re.sub(r"\s+", " ", re.sub(r"[’']", "'", str(t or "").lower())) + " "


def _phrases(s: dict) -> list[str]:
    out = [s.get("name"), s.get("vendor"), s.get("short"), wf.SH.get(s["id"])]
    return list(dict.fromkeys(x.lower() for x in out if x))


def _tokens(s: dict) -> set[str]:
    words: set[str] = set()
    for p in _phrases(s):
        words |= {w for w in re.findall(r"[a-z0-9/.&-]+", p) if len(w) >= 3 and w not in STOP_TOKENS}
    if len(s["id"]) >= 3:
        words.add(s["id"])
    return words


_TOKEN_SIDS: dict[str, set[str]] = {}
for _sid, _s in SOURCES.items():
    for _w in _tokens(_s):
        _TOKEN_SIDS.setdefault(_w, set()).add(_sid)


def _find(t: str, rx: str) -> int:
    m = re.search(rx, t)
    return m.start() if m else -1


def _neg_before(t: str, pos: int) -> bool:
    return bool(NEG.search(t[max(0, pos - 30) : pos]))


# ---------------------------------------------------------------- the planner: what the description says
def _systems(t: str) -> tuple[list[tuple[str, int]], list[set[str]]]:
    """Sources the text names: (source id, position) for unambiguous hits, and groups of candidates for a word that
    names several (e.g. "oracle", "sap")."""
    hits: dict[str, int] = {}
    for sid, s in SOURCES.items():
        for p in _phrases(s):
            if (i := _find(t, r"(?<![a-z0-9])" + re.escape(p) + r"(?![a-z0-9])")) >= 0:
                hits[sid] = min(hits.get(sid, i), i)
    groups: list[set[str]] = []
    for w, sids in _TOKEN_SIDS.items():
        i = _find(t, r"(?<![a-z0-9])" + re.escape(w) + r"(?![a-z0-9])")
        if i < 0:
            continue
        if len(sids) == 1:
            sid = next(iter(sids))
            hits[sid] = min(hits.get(sid, i), i)
        elif not sids & set(hits):
            groups.append(set(sids))
    return sorted(hits.items(), key=lambda x: x[1]), groups


def _unknown_phrase(t: str) -> str | None:
    """A name after from/to/into/for that is not a connected system (the caller checks no source matched)."""
    for m in re.finditer(r"\b(?:from|to|into|for|in)\s+((?:[a-z0-9][a-z0-9&./-]*)(?:\s+[a-z0-9][a-z0-9&./-]*){0,2})", t):
        words = m.group(1).split()
        while words and words[0] in ("the", "our", "a", "an", "my", "their"):
            words = words[1:]
        cut = []
        for w in words:
            if w in GENERIC or w in ("with", "every", "on", "and", "using", "via", "by", "daily", "hourly", "called", "named"):
                break
            cut.append(w)
        if (
            cut
            and not re.fullmatch(r"\d+.*", cut[0])
            and not any(rx.search(" " + " ".join(cut) + " ") for rx in STEP_KW.values())
        ):
            return " ".join(cut)
    return None


def _closest(name: str, pool: list[str], n: int = 4) -> list[str]:
    """The sources in `pool` whose names, vendors or ids look like `name` (a similarity of at least 0.6), best first;
    [] when none does."""
    scored = []
    for sid in pool:
        s = SOURCES[sid]
        best = max(difflib.SequenceMatcher(None, name, p).ratio() for p in [*_phrases(s), sid])
        tok = max((difflib.SequenceMatcher(None, w, x).ratio() for w in name.split() for x in _tokens(s)), default=0)
        scored.append((max(best, tok), sid))
    scored.sort(key=lambda x: -x[0])
    return [sid for sc, sid in scored[:n] if sc >= 0.6]


def _by_type(sid: str, pool: list[str]) -> list[str]:
    """The sources in `pool` that feed the same canonical model as `sid`, then the rest."""
    t = MAP_TARGET.get(sid)
    return [x for x in pool if MAP_TARGET.get(x) == t] + [x for x in pool if MAP_TARGET.get(x) != t]


def _trigger(t: str) -> tuple[dict | None, bool]:
    """(the trigger the text asks for, whether it asked for one)."""
    if m := re.search(r"every\s+(\d+)\s*(minutes?|mins?|m\b|hours?|hrs?|h\b)", t):
        n = int(m.group(1)) * (60 if m.group(2).startswith("h") else 1)
        return {"t": "schedule", "min": max(1, min(n, 10080))}, True
    if re.search(r"every (single )?hour|\bhourly\b", t):
        return {"t": "schedule", "min": 60}, True
    if re.search(r"every minute", t):
        return {"t": "schedule", "min": 5}, True
    if re.search(r"\bdaily\b|every day|\bnightly\b|once a day|every night", t):
        return {"t": "schedule", "min": 1440}, True
    if re.search(r"file (arriv|land|drop)|when (a|the) file|on file|sftp drop", t):
        return {"t": "file"}, True
    if re.search(r"on approval|when (it is |a decision is |they are )?approved|after (an? )?approval|once approved", t):
        return {"t": "approval"}, True
    if re.search(r"case request|per case|for each case|on (each |every )?case|when a case", t):
        return {"t": "case"}, True
    if re.search(
        r"real[- ]?time|on (each |every |an? )?event|webhook|as (soon as|they) (arrive|happen)|event[- ]driven|streaming"
        r"|when .{0,30}(arrives|changes|is created)",
        t,
    ):
        return {"t": "event"}, True
    if re.search(r"\bmanual(ly)?\b|on demand|by hand|run it myself", t):
        return {"t": "manual"}, True
    if re.search(r"\bschedul", t):
        return None, False
    return None, False


def _type(t: str) -> list[str]:
    found = []
    if re.search(r"\bblank\b|\bempty\b|from scratch", t):
        found.append("blank")
    if re.search(r"\bdecision|six[- ]gate|\bgates?\b|\ballocat|\bpool\b|\broutes?\b|\b(approval|business|routing) rules?\b", t):
        found.append("dec")
    if re.search(
        r"outbound|\b(send|push|write|deliver|post|export)\b.{0,60}\b(to|into)\b|instructions? to\b|\bwrite[- ]?back", t
    ):
        found.append("out")
    if re.search(
        r"\bingest|\bimport|\bpull\b|\bread (data )?from|\bload\b.{0,30}\bfrom|\bsync\b.{0,30}\bfrom|\bfeed from"
        r"|bring in|\bfrom\b",
        t,
    ):
        found.append("ingest")
    return found


def _delivery(t: str) -> str | None:
    for ch, rx in (
        ("file", r"\bfiles?\b|\bcsv\b|\bsftp\b|\bbatch file|interface file"),
        ("proc", r"process orchestration|\bbpm\b|approval task|\btasks?\b in|orchestrat"),
        ("event", r"\bevents?\b|webhook|\bqueue\b|message"),
        ("api", r"\bapi\b|\brest\b|\bsoap\b|api call"),
    ):
        if re.search(rx, t):
            return ch
    return None


def read_prompt(prompt: str) -> dict[str, Any]:
    """Every slot the description settles, with notes about what it names but cannot be used."""
    t = _norm(prompt)
    p: dict[str, Any] = {"t": t, "notes": []}
    types = _type(t)
    hits, groups = _systems(t)
    p["hits"], p["groups"] = [h[0] for h in hits], groups
    if "blank" in types:
        p["type"] = "blank"
    elif "dec" in types and not hits and "out" not in types:
        p["type"] = "dec"
    elif "out" in types and "ingest" in types:
        # "from X to Y": a write to a system is outbound when the system after "to" is writable
        to_i = max(t.rfind(" to "), t.rfind(" into "))
        after = [sid for sid, i in hits if i > to_i >= 0]
        if after and wf.DELIVER.get(after[0]) and not re.search(r"\bingest|\bimport", t):
            p["type"] = "out"
        elif re.search(r"\bingest|\bimport", t):
            p["type"] = "ingest"
        else:
            p["ambiguous_type"] = ["ingest", "out"]
    elif "out" in types:
        p["type"] = "out"
    elif "ingest" in types:
        p["type"] = "ingest"
    elif "dec" in types:
        p["type"] = "dec"
    # the system: prefer the one after "to" for outbound and after "from" for ingest
    if hits:
        if p.get("type") == "out":
            to_i = max(t.rfind(" to "), t.rfind(" into "))
            after = [sid for sid, i in hits if i > to_i >= 0]
            p["system"] = (after or [h[0] for h in hits])[0]
        elif p.get("type") == "ingest" or len(hits) == 1:
            fr = t.find(" from ")
            after = [sid for sid, i in hits if i > fr >= 0]
            p["system"] = (after or [h[0] for h in hits])[0]
        else:
            p["system_choices"] = [h[0] for h in hits]
        if len({h[0] for h in hits}) > 1 and p.get("system"):
            others = [SOURCES[h[0]]["name"] for h in hits if h[0] != p["system"]]
            p["notes"].append(
                f"Each workflow stands alone with one system, so this one uses {SOURCES[p['system']]['name']}; "
                f"build another for {', '.join(others)}."
            )
    elif groups:
        p["system_choices"] = sorted(groups[0], key=list(SOURCES).index)
    elif (u := _unknown_phrase(t)) is not None:
        p["unknown"] = u
    if p.get("type") is None and p.get("system") and not p.get("ambiguous_type"):
        s = SOURCES[p["system"]]
        if not wf.DELIVER.get(p["system"]):
            p["type"] = "ingest"  # Circularity only reads from it
        elif re.search(r"\b(to|into)\b", t) and not s.get("read"):
            p["type"] = "out"
    if p.get("type") in ("dec", None):
        p["decision"] = (
            "pool"
            if re.search(r"\bpool\b|allocat|optimi[sz]", t)
            else "gap"
            if re.search(r"missing evidence|evidence gaps?|find demand|request evidence", t)
            else ("standard" if re.search(r"standard|six[- ]gate|\bgates\b", t) else None)
        )
    if (ch := _delivery(t)) and p.get("type") == "out":
        p["delivery"] = ch
    trig, said = _trigger(t)
    if trig:
        p["trigger"] = trig
    p["trigger_said"] = said
    if re.search(r"\b(only )?(through|via|by|over) (the )?api\b|\bpoll(ing|ed)?\b|api only", t):
        p["channels"] = "api"
    elif re.search(r"\bevents? only\b|only events|(through|via|by) (webhooks?|events)", t):
        p["channels"] = "event"
    want: list[str] = []
    drop: list[str] = []
    for ref, rx in STEP_KW.items():
        for m in rx.finditer(t):
            (drop if _neg_before(t, m.start()) else want).append(ref)
    p["steps_want"] = [r for r in STEP_ORDER if r in want and r not in drop]
    p["steps_drop"] = [r for r in STEP_ORDER if r in drop]
    p["steps_said"] = bool(want or drop)
    keep: list[str] = []
    lose: list[str] = []
    for ref, rx in HANDLING_KW.items():
        for m in rx.finditer(t):
            (lose if _neg_before(t, m.start()) else keep).append(ref)
    if re.search(r"\b(no|without) (error handling|branches)\b", t):
        lose += ["x_err", "x_audit", "x_pub"]
    p["handling_keep"] = [r for r in HANDLING_KW if r in keep and r not in lose]
    p["handling_drop"] = [r for r in HANDLING_KW if r in lose]
    if rm := re.search(r"\b(\d)\s*retr(y|ies)\b|\bretr(y|ies)\s*(\d)\b|\b(no|zero) retr(y|ies)\b", t):
        n = 0 if rm.group(5) else int(rm.group(1) or rm.group(4))
        p["retries"] = min(wf.RETRIES, key=lambda r: abs(r - n))
    if re.search(r"two (runs )?(fail|failures) in a row|fails? twice", t):
        p["alert"] = wf.ALERTS[1]
    elif re.search(r"success rate|below 95", t):
        p["alert"] = wf.ALERTS[2]
    elif re.search(r"\b(no|never|without) alerts?\b|don'?t alert", t):
        p["alert"] = wf.ALERTS[3]
    elif re.search(r"alert (me |us )?(when|if) (a |any |the )?(run )?fails|alert on (any )?failure", t):
        p["alert"] = wf.ALERTS[0]
    if nm := re.search(r"\b(?:called|named)\s+[\"“']?([^\"”'.,;]{3,80})", prompt, re.I):
        p["name"] = nm.group(1).strip()
    if om := re.search(r"\bowned by\s+([A-Za-z][A-Za-z &-]{2,60}?)(?:[.,;]|$| with| every| and)", prompt):
        p["owner"] = om.group(1).strip()
    return p


# ---------------------------------------------------------------- the language model (optional)
def model_slots(prompt: str) -> dict[str, Any]:
    """The description read by Groq into the same slots, or {} (no key, disabled, any failure). Only values that pass
    the checks in `_merge_model` are used. The key goes to the SDK only."""
    try:
        from di.core.config import DEFAULT_GROQ_MODEL, get_settings

        st = get_settings()
        key = st.groq_api_key.get_secret_value().strip()
        if not key or (st.ask_provider or "groq").strip().lower() != "groq":
            return {}
        from di.services.ask.groq_model import _client

        names = "; ".join(f"{sid}={s['name']} ({s['vendor']})" for sid, s in SOURCES.items())
        system = (
            "You turn a workflow request into JSON slots. Reply with one JSON object only, keys optional: "
            'type ("ingest"|"out"|"dec"|"blank"), system (one id from the list), delivery ("api"|"event"|"file"|"proc"), '
            'trigger ("schedule"|"event"|"file"|"approval"|"case"|"manual"), minutes (integer), '
            f"steps (list of: {', '.join(STEP_ORDER)}). Leave out every key the request does not state; never guess. "
            f"Systems: {names}"
        )
        model = st.groq_model.strip() or DEFAULT_GROQ_MODEL
        extra = {"reasoning_effort": "low", "include_reasoning": False} if model.startswith("openai/gpt-oss") else {}
        r = _client(
            key, min(st.ask_timeout_seconds, 10.0)
        ).chat.completions.create(  # type: ignore[call-overload]
            model=model,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": prompt[:1000]}],
            temperature=0,
            max_completion_tokens=300,
            response_format={"type": "json_object"},
            **extra,
        )
        out = json.loads(r.choices[0].message.content or "{}")
        return out if isinstance(out, dict) else {}
    except Exception:  # noqa: BLE001 - the model is an optional helper; the keyword reading stands on its own
        log.info("workflow.plan: the language model did not answer; using the keyword reading")
        return {}


def _merge_model(p: dict, m: dict) -> None:
    """Let the model settle only what the keywords found but could not resolve: which of two readings of the type,
    which of several systems a word names, the system behind a name that is not one of ours, a trigger the description
    talks about in other words, and steps it describes in other words. It never fills a slot the description does not
    mention (so "make a workflow" still asks the type first), and its values are checked against the allowed choices."""
    if not m:
        return
    t = p["t"]
    if p.get("ambiguous_type") and m.get("type") in p["ambiguous_type"]:
        p["type"] = m["type"]
        p.pop("ambiguous_type", None)
    if not p.get("system") and m.get("system") in SOURCES:
        if m["system"] in (p.get("system_choices") or []):
            p["system"] = m["system"]
            p.pop("system_choices", None)
        elif p.get("unknown"):
            s = SOURCES[m["system"]]
            p["notes"].append(f"I read “{p.pop('unknown')}” as {s['name']} ({s['vendor']}). Change it if that is wrong.")
            p["system"] = m["system"]
    talks_trigger = re.search(r"\b(every|each|schedul\w*|when|whenever|once|nightly|weekly|hourly|minutes?|hours?|run)\b", t)
    if not p.get("trigger") and talks_trigger and m.get("trigger") in (*TRIG_HINT, "schedule"):
        if m["trigger"] == "schedule":
            if isinstance(m.get("minutes"), int) and 0 < m["minutes"] <= 10080:
                p["trigger"] = {"t": "schedule", "min": m["minutes"]}
        else:
            p["trigger"] = {"t": m["trigger"]}
        p["trigger_said"] = bool(p.get("trigger"))
    talks_steps = re.search(r"\b(with|including|plus|add|adds|then|also)\b", t)
    if not p.get("steps_said") and talks_steps and isinstance(m.get("steps"), list):
        steps = [x for x in STEP_ORDER if x in m["steps"]]
        if steps:
            p["steps_want"], p["steps_said"] = steps, True


# ---------------------------------------------------------------- the planner: sources as they are now
def _live(ctx: CallContext) -> tuple[set[str], dict[str, str]]:
    """Deleted sources and the connector state of the others (paused, disconnected ...)."""
    try:
        from di.connectors import lifecycle

        gone = lifecycle.deleted(ctx.session)
        rows = ctx.session.execute(text("SELECT id, status FROM source_system")).all()
        return gone, {r[0]: r[1] for r in rows}
    except Exception:  # noqa: BLE001 - without the tables the reference record stands
        return set(), {}


def readable(ctx: CallContext) -> list[str]:
    gone, _ = _live(ctx)
    return [sid for sid, s in SOURCES.items() if s.get("read") and s["status"] != "unavailable" and sid not in gone]


def writable(ctx: CallContext) -> list[str]:
    gone, _ = _live(ctx)
    return [sid for sid in SOURCES if wf.DELIVER.get(sid) and SOURCES[sid].get("write") and sid not in gone]


def _src_choice(sid: str, out: bool = False) -> dict:
    s = SOURCES[sid]
    if out:
        hint = "Accepts " + ", ".join(wf.CH_DEL[c] for c in wf.DELIVER.get(sid, []))
    else:
        ch = channels(s)
        hint = (
            f"{s['vendor']} · " + " and ".join(wf.CH_ARR[c] for c in ch) + f" · into {SRC_TYPES[s['type']]['target']}"
            + (" · stale feed" if s["status"] == "stale" else " · manual import" if s["status"] == "manual" else "")
        )  # fmt: skip
    return {"value": sid, "label": f"{s['name']} · {s['vendor']}", "hint": hint}


def _trig_value(t: dict) -> str:
    return f"schedule:{t['min']}" if t.get("t") == "schedule" else str(t.get("t"))


def _trig_from(v: Any) -> dict | None:
    if isinstance(v, dict) and v.get("t"):
        return v
    if not isinstance(v, str):
        return None
    if v.startswith("schedule:"):
        n = v.split(":", 1)[1]
        return {"t": "schedule", "min": int(n)} if n.isdigit() and 0 < int(n) <= 10080 else None
    return {"t": v} if v in TRIG_HINT else None


def default_trigger(kind: str, sid: str | None) -> dict:
    """What workflow.create gives each type."""
    if kind == "ingest" and sid:
        s = SOURCES[sid]
        return {"t": "schedule", "min": s["interval"]} if s.get("interval") else {"t": "event"}
    return {"t": {"out": "approval", "dec": "case"}.get(kind, "manual")}


def _trig_ok(kind: str, sid: str | None, t: dict) -> bool:
    if t.get("t") not in TRIG_OK[kind]:
        return False
    if kind == "ingest" and sid:
        ch = channels(SOURCES[sid])
        if t["t"] == "file" and "file" not in ch:
            return False
        if t["t"] == "event" and "event" not in ch:
            return False
    return True


def _q(qid: str, text_: str, kind: str, choices: list[dict], default: Any, note: str | None = None) -> dict:
    return {
        "id": qid, "text": text_, "kind": kind, "multi": kind == "multi", "choices": choices, "default": default,
        **({"note": note} if note else {}),
    }  # fmt: skip


def step_choices(kind: str, sid: str | None) -> list[dict]:
    """The palette steps worth adding for this workflow (the source's own transform is a standard step already)."""
    if kind == "ingest":
        refs = [r for r in STEP_ORDER if r != "x_flag" or (sid and SOURCES[sid]["type"] in ("repair", "insp"))]
    elif kind == "out":
        refs = list(OUT_STEPS)
    else:
        return []
    std = _std_xform(kind, sid)
    return [
        {
            "value": r,
            "label": wf._xf_req(r)["label"],
            "hint": wf._xf_req(r)["desc"] + (" (usual for this source; optional)" if r == std else ""),
        }
        for r in refs
    ]


def _std_xform(kind: str, sid: str | None) -> str | None:
    """The transform the standard ingest adds for the source's type (wfBuild's XFORM), if any."""
    if kind != "ingest" or not sid:
        return None
    s = SOURCES[sid]
    ch = channels(s)
    file_only = "file" in ch and "api" not in ch and "event" not in ch
    return None if file_only else wf.XFORM.get(s["type"])


def handling_choices(kind: str, sid: str | None, ch: str | None) -> list[str]:
    if kind == "ingest":
        canon = wf.CANON_FIX.get(MAP_TARGET.get(sid or "") or "Outcome")
        return ["x_err", "x_audit"] + (["x_pub"] if canon != "c_out" else [])
    if kind == "out":
        return ["x_audit"] + (["x_cb"] if ch == "file" else [])
    if kind == "dec":
        return ["x_audit"]
    return []


# ---------------------------------------------------------------- the planner: one round
def plan(prompt: str, answers: dict[str, Any], ctx: CallContext, use_model: bool = True) -> dict[str, Any]:
    """The next questions, or the complete plan. `answers` are the person's answers so far, by question id."""
    p = read_prompt(prompt)
    if use_model:
        _merge_model(p, model_slots(prompt))
    a = {k: v for k, v in (answers or {}).items() if v is not None and v != ""}
    notes: list[str] = list(p["notes"])
    understood: list[dict] = []
    defaults_ok = bool(a.get("_defaults"))

    def said(slot: str, label_: str, value: str, by: str) -> None:
        understood.append({"slot": slot, "label": label_, "value": value, "from": by})

    # ---- round 1: the type
    kind = a.get("type") if a.get("type") in TYPES else p.get("type")
    if kind == "dec":  # decisions, gates, approval rules and routes are the Modeler's, never a new Studio draft
        return _redirect(notes, understood, a)
    if kind is None:
        why = None
        if p.get("ambiguous_type"):
            why = "Your description reads both ways: data coming in from a system, or an instruction going out to one."
        default = "out" if p.get("ambiguous_type") else "ingest"
        q = _q("type", "What kind of workflow is it?", "choice",
               [{"value": k, "label": v[0], "hint": v[1]} for k, v in TYPES.items()], default, why)  # fmt: skip
        return _questions([q], notes, understood, a)
    said("type", "Type", TYPES[kind][0], "answer" if "type" in a else "prompt")

    # ---- round 2: the system (and delivery or decision flow)
    sid: str | None = None
    ch: str | None = None
    qs: list[dict] = []
    if kind in ("ingest", "out"):
        pool = readable(ctx) if kind == "ingest" else writable(ctx)
        cand = a.get("system") if a.get("system") in SOURCES else p.get("system")
        if cand and cand not in pool:
            s = SOURCES[cand]
            if kind == "ingest" and s["status"] == "unavailable":
                notes.append(f"{s['name']} ({s['vendor']}) has no connected feed yet ({s['auth']}), so an ingest from it "
                             "would fail its checks. Pick a connected system, or connect it first.")  # fmt: skip
            elif kind == "out":
                notes.append(f"Circularity reads from {s['name']} ({s['vendor']}) but does not write to it, so it cannot "
                             "receive instructions. These systems can:")  # fmt: skip
            else:
                notes.append(f"{s['name']} is not available to read from now.")
            closest = _by_type(cand, pool)[:4]
            qs.append(_q("system", "Which system should it " + ("read from?" if kind == "ingest" else "send to?"), "choice",
                         [_src_choice(x, kind == "out") for x in closest + [x for x in pool if x not in closest]],
                         closest[0] if closest else None))  # fmt: skip
            cand = None
        elif cand:
            sid = cand
        else:
            choices = [x for x in (p.get("system_choices") or []) if x in pool]
            note = None
            if p.get("unknown"):
                closest = _closest(p["unknown"], pool)
                note = (f"I could not find “{p['unknown']}” among the connected systems (all of them synthetic mocks). "
                        + ("The closest names are listed first." if closest else "Pick one of these."))  # fmt: skip
                choices = closest
            elif choices:
                note = "Your description could mean more than one system."
            order = choices + [x for x in pool if x not in choices]
            qs.append(_q("system", "Which system should it " + ("read from?" if kind == "ingest" else "send to?"), "choice",
                         [_src_choice(x, kind == "out") for x in order], order[0] if order else None, note))  # fmt: skip
        if sid:
            s = SOURCES[sid]
            said("system", "Source system" if kind == "ingest" else "Target system", f"{s['name']} · {s['vendor']}",
                 "answer" if "system" in a else "prompt")  # fmt: skip
            st = _live(ctx)[1].get(sid)
            if st in ("paused", "disconnected"):
                notes.append(
                    f"{s['name']} is {st} now; the workflow can be built, but it reads nothing until the source is resumed."
                )
            if kind == "out":
                acc = wf.DELIVER.get(sid, [])
                want = a.get("delivery") if a.get("delivery") in acc else None
                if want is None and p.get("delivery"):
                    if p["delivery"] in acc:
                        want = p["delivery"]
                    else:
                        notes.append(f"{s['name']} does not accept {wf.CH_DEL[p['delivery']]}. It accepts "
                                     f"{', '.join(wf.CH_DEL[c] for c in acc)}.")  # fmt: skip
                if want is None and len(acc) == 1:
                    want = acc[0]
                if want is None:
                    qs.append(_q("delivery", f"How should {s['name']} receive the instruction?", "choice",
                                 [{"value": c, "label": CH_LABEL[c], "hint": CH_HINT[c]} for c in acc], acc[0]))  # fmt: skip
                else:
                    ch = want
                    said("delivery", "Delivery", CH_LABEL[ch], "answer" if "delivery" in a else "prompt")
    elif kind == "dec":
        dk = a.get("decision") if a.get("decision") in DECISIONS else p.get("decision")
        if dk is None:
            qs.append(_q("decision", "Which decision flow?", "choice",
                         [{"value": k, "label": v[0], "hint": v[1]} for k, v in DECISIONS.items()], "standard"))  # fmt: skip
        else:
            said("decision", "Decision flow", DECISIONS[dk][0], "answer" if "decision" in a else "prompt")
    if qs:
        return _questions(qs, notes, understood, a)

    # ---- round 3: the details, all at once, each with its default
    dk = (a.get("decision") if a.get("decision") in DECISIONS else p.get("decision")) or "standard"
    src_name = SOURCES[sid]["name"] if sid else None
    s_ch = channels(SOURCES[sid]) if sid else []
    details: list[dict] = []

    def settled(slot: str, from_prompt: bool) -> bool:
        return slot in a or from_prompt or defaults_ok

    # channels (ingest from a source that delivers by API and events): one channel unless the person wants both
    two_ways = kind == "ingest" and "api" in s_ch and "event" in s_ch
    arrive: str = str(a["channels"] if a.get("channels") in ARRIVE else p.get("channels") or "")
    # the trigger
    dflt = default_trigger(kind, sid)
    trig = _trig_from(a.get("trigger")) or p.get("trigger")
    if trig and not _trig_ok(kind, sid, trig):
        what = "files" if trig["t"] == "file" else "events"
        why = f": {src_name} does not send {what}." if kind == "ingest" else "."
        notes.append(f"{wf.trig_text(trig)} does not fit this workflow{why} Pick one of these.")
        trig = None
        a.pop("trigger", None)
    if kind == "ingest" and arrive == "event" and not trig and "event" in s_ch:  # "events only" said in the prompt
        dflt = {"t": "event"}
    if trig is None and not defaults_ok:
        opts = []
        for t in TRIG_OK[kind]:
            if t == "schedule":
                mins = sorted(set(INTERVALS) | ({dflt["min"]} if dflt.get("t") == "schedule" else set()))
                opts += [
                    {"value": f"schedule:{m}", "label": wf.trig_text({"t": "schedule", "min": m}), "hint": "On a schedule"}
                    for m in mins
                ]
            elif _trig_ok(kind, sid, {"t": t}):
                opts.append({"value": t, "label": wf.trig_text({"t": t}), "hint": TRIG_HINT[t]})
        details.append(_q("trigger", "When should it run?", "choice", opts, _trig_value(dflt)))
    trig = trig or dflt
    if p.get("trigger") or "trigger" in a:
        said("trigger", "Trigger", wf.trig_text(trig), "answer" if "trigger" in a else "prompt")
    if two_ways:
        one = "event" if trig.get("t") == "event" else "api"
        if not settled("channels", bool(p.get("channels"))):
            details.append(_q("channels", f"How should records arrive from {src_name}?", "choice",
                              [{"value": k, "label": v[0], "hint": v[1]} for k, v in ARRIVE.items()], one,
                              "One channel is all it needs; both only if the system sends some records each way."))  # fmt: skip
        arrive = arrive or one
        if "channels" in a or p.get("channels"):
            said("channels", "Arrives by", ARRIVE[arrive][0], "answer" if "channels" in a else "prompt")
    arrive = arrive or "api"
    # extra blocks: only the ones asked for
    choices = step_choices(kind, sid)
    allowed = {c["value"] for c in choices}
    if "steps" in a and isinstance(a["steps"], list):
        steps = [r for r in STEP_ORDER if r in a["steps"] and r in allowed]
    else:
        steps = [r for r in p["steps_want"] if r in allowed]
    for r in p["steps_want"]:
        if r not in allowed and kind in ("ingest", "out"):
            fits = "an outbound instruction" if kind == "out" else "this ingest"
            notes.append(f"{wf._xf_req(r)['label']} does not fit {fits}, so it is left out.")
    if choices and not settled("steps", p["steps_said"]):
        details.append(_q("steps", "Which blocks should it add?", "multi", choices, steps,
                          "Only the blocks you mention are ticked; the workflow runs without any of them. They run in the "
                          "order shown."))  # fmt: skip
    elif steps:
        said(
            "steps",
            "Adds",
            ", ".join(wf._xf_req(r)["label"] for r in steps) or "no extra blocks",
            "answer" if "steps" in a else "prompt",
        )
    # error handling and branches
    hc = handling_choices(kind, sid, ch)
    if "handling" in a and isinstance(a["handling"], list):
        handling = [h for h in hc if h in a["handling"]]
    else:
        handling = [h for h in hc if h in p["handling_keep"]]  # none is needed to run: only what was asked for
    if hc and not settled("handling", bool(p["handling_keep"] or p["handling_drop"])):
        details.append(_q("handling", "Error handling and logging", "multi",
                          [{"value": h, "label": HANDLING_LABEL[h][0], "hint": HANDLING_LABEL[h][1]} for h in hc], handling,
                          "Optional: the workflow runs without them. Tick the ones you want."))  # fmt: skip
    elif handling:
        said(
            "handling",
            "Adds",
            ", ".join(HANDLING_LABEL[h][0] for h in handling),
            "answer" if "handling" in a else "prompt",
        )
    # run settings
    retries = a.get("retries") if a.get("retries") in wf.RETRIES and not isinstance(a.get("retries"), bool) else p.get("retries")
    if isinstance(retries, str) and retries.isdigit():
        retries = int(retries)
    if retries is None and not defaults_ok and kind != "blank":
        rc = [
            {"value": r, "label": "No retries" if r == 0 else f"{r} retr{'y' if r == 1 else 'ies'}", "hint": ""}
            for r in wf.RETRIES
        ]
        details.append(_q("retries", "Retries when a step fails", "choice", rc, 3))
    retries = 3 if retries is None else retries
    alert = a.get("alert") if a.get("alert") in wf.ALERTS else p.get("alert")
    if alert is None and not defaults_ok and kind != "blank":
        details.append(
            _q("alert", "Alert when", "choice", [{"value": x, "label": x, "hint": ""} for x in wf.ALERTS], wf.ALERTS[0])
        )
    alert = alert or wf.ALERTS[0]
    if "retries" in a or p.get("retries") is not None:
        said("retries", "Retries", str(retries), "answer" if "retries" in a else "prompt")
    if "alert" in a or p.get("alert"):
        said("alert", "Alert when", alert, "answer" if "alert" in a else "prompt")
    # the graph, then the name and owner that describe it
    shape = {
        "kind": kind,
        "sid": sid,
        "ch": ch,
        "dec": dk,
        "arrive": arrive,
        "steps": steps,
        "handling": handling,
    }
    g = tailored_graph(shape)
    for ref, cfg in read_settings(prompt).items():
        for n in g["nodes"]:
            if n["k"] == "xf" and n["ref"] == ref:
                n.update(wf._n(n["id"], n["k"], n["ref"], n["x"], n["y"], cfg))
                said("settings", wf._xf_req(ref)["label"], ", ".join(f"{k} {_val(v)}" for k, v in cfg.items()), "prompt")
    name0 = tailored_name(shape, trig)
    owner0 = SOURCES[sid]["owner"] if sid else "Decision Services" if kind == "dec" else "Unassigned"
    name = str(a.get("name") or p.get("name") or name0).strip()[:80]
    owner = str(a.get("owner") or p.get("owner") or owner0).strip()[:80]
    # the questions with a safe default (how it arrives, the standard transform, the name and owner) come only
    # alongside one that shapes the workflow (trigger, steps, handling, retries, alert); alone they never hold it up
    if any(q["id"] in PRIMARY for q in details):
        if not settled("name", bool(p.get("name"))):
            details.append(_q("name", "Name", "text", [], name0))
        if not settled("owner", bool(p.get("owner"))):
            details.append(_q("owner", "Owner", "text", [], owner0))
        return _questions(details, notes, understood, a)
    return _ready(shape, g, name, owner, trig, retries, alert, notes, understood, a)


PRIMARY = ("trigger", "steps", "handling", "retries", "alert")

# block settings the description can state (di/workflow/blocks.py keys): "to EUR" → x_fx currency, "dedupe by id" →
# x_late keys. Only values the block accepts are taken; the rest stay the defaults.
_CUR = re.compile(r"\b(?:to|into|in)\s+(usd|eur|inr)\b")
_DEDUPE_BY = re.compile(r"\b(?:de-?dup\w*|duplicat\w*|order(?:ed)?)\s+(?:by|on)\s+([a-z_][\w.]*(?:\s*(?:,|and)\s*[a-z_][\w.]*)*)")


def read_settings(prompt: str) -> dict[str, dict]:
    """The block settings the description states, by transform: {"x_fx": {"currency": "EUR"}, ...}."""
    t = _norm(prompt)
    out: dict[str, dict] = {}
    if (m := _CUR.search(t)) and m.group(1).upper() != "USD":
        out["x_fx"] = {"currency": m.group(1).upper()}
    if m := _DEDUPE_BY.search(t):
        keys = [k for k in re.split(r"\s*(?:,|\band\b)\s*", m.group(1)) if k and k not in GENERIC]
        if keys:
            out["x_late"] = {"keys": keys}
    return {ref: cfg for ref, cfg in out.items() if not blocks.cfg_errors({"k": "xf", "ref": ref, "cfg": cfg})}


def _val(v: Any) -> str:
    return ", ".join(map(str, v)) if isinstance(v, list) else str(v)


def _questions(qs: list[dict], notes: list[str], understood: list[dict], a: dict) -> dict[str, Any]:
    return {
        "status": "questions", "questions": qs, "notes": notes, "understood": understood, "answers": a, "plan": None,
        "redirect": None,
    }  # fmt: skip


MODELER_REASON = (
    "Decisions, gates, approval rules and routes are business rules, and they live in the Modeler. Workflow Studio "
    "builds the connection workflows: ingest from a system and outbound instructions to one."
)


def _redirect(notes: list[str], understood: list[dict], a: dict) -> dict[str, Any]:
    """The reply to a decision sentence: no questions and no plan, a pointer to the Modeler (P9-0.16)."""
    return {
        "status": "blocked", "questions": [], "notes": [*notes, MODELER_REASON], "understood": understood, "answers": a,
        "plan": None, "redirect": {"to": "modeler", "reason": MODELER_REASON},
    }  # fmt: skip


# ---------------------------------------------------------------- the tailored graph
def tailored_graph(sh: dict) -> dict:
    kind = sh["kind"]
    if kind == "ingest":
        g = _ingest(sh)
    elif kind == "out":
        g = _outbound(sh)
    elif kind == "dec":
        g = wf.build({"k": "dec", "id": sh["dec"]})
        if "x_audit" not in sh["handling"]:
            g["nodes"] = [n for n in g["nodes"] if n["id"] != "aud"]
            g["edges"] = [e for e in g["edges"] if e["b"] != "aud"]
    else:
        g = {"nodes": [], "edges": []}
    for i, e in enumerate(g["edges"]):
        e["id"] = f"e{i}"
    return g


def minimal_graph(tpl: dict) -> dict:
    """The graph New workflow starts with ({k: "min", type, src, ch, arrive, id}): MINIMAL, the blocks the workflow
    needs to run, and nothing else; the person adds the rest from the palette. Reset to template returns to it."""
    kind = tpl.get("type") or "blank"
    return tailored_graph({
        "kind": kind, "sid": tpl.get("src"), "ch": tpl.get("ch"), "dec": tpl.get("id") or "standard",
        "arrive": tpl.get("arrive") or "api", "steps": [], "handling": [],
    })  # fmt: skip


def _step_id(ref: str) -> str:
    return "s_" + ref.removeprefix("x_")


def _ingest(sh: dict) -> dict:
    """The required ingest blocks (MINIMAL) with bIngest's step ids, the chosen ingestion channel(s), the requested steps
    between validation and the field mapping in run order, and the requested branches; laid out left to right."""
    sid = sh["sid"]
    s = wf.src(sid) or SOURCES[sid]  # New workflow reads the sources as they are now (wf.live_sources)
    ch = channels(s)
    file_only = "file" in ch and "api" not in ch and "event" not in ch
    chain = [r for r in STEP_ORDER if r in sh["steps"]]
    y0, X = 170, 206
    nodes: list[dict] = []
    edges: list[dict] = []
    col = [0]

    def x() -> int:
        v = 24 + col[0] * X
        col[0] += 1
        return v

    nodes.append(wf._n("r", "conn", sid, x(), y0))
    prev = ["r"]
    if file_only:
        for i, r in enumerate(["x_trig", "x_unzip", "x_chunk"]):
            nodes.append(wf._n(f"f{i}", "xf", r, x(), y0))
            edges.append(wf._e(prev[0], f"f{i}"))
            prev = [f"f{i}"]
    else:
        rs = (["x_gw"] if "api" in ch else []) + (["x_evt"] if "event" in ch else [])
        if sh["arrive"] == "api" and "x_gw" in rs:
            rs = ["x_gw"]
        elif sh["arrive"] == "event" and "x_evt" in rs:
            rs = ["x_evt"]
        rs = rs or ["x_gw"]
        cx, ids = x(), []
        for i, r in enumerate(rs):
            nid = f"ig{['x_gw', 'x_evt'].index(r)}" if r in ("x_gw", "x_evt") else f"ig{i}"
            nodes.append(wf._n(nid, "xf", r, cx, y0 - 80 + i * 160 if len(rs) > 1 else y0))
            edges.append(wf._e("r", nid))
            ids.append(nid)
        prev = ids
    nodes.append(wf._n("v", "xf", "x_val", x(), y0))
    edges += [wf._e(q, "v") for q in prev]
    prev = ["v"]
    branch_at = None
    for r in chain:
        nid = _step_id(r)
        nodes.append(wf._n(nid, "xf", r, x(), y0))
        edges.append(wf._e(prev[0], nid))
        prev = [nid]
        if r == "x_branch":
            branch_at = nid
    nodes.append(wf._n("m", "map", sid, x(), y0))
    edges.append(wf._e(prev[0], "m"))
    c: Any = wf.CANON_FIX.get(wf.map_target(sid) or "Outcome")
    nodes.append(wf._n(c, "fixed", c, x(), y0))
    edges.append(wf._e("m", c))
    if c != "c_out" and not file_only:
        nodes.append(wf._n("snap", "fixed", "snap", x(), y0))
        edges.append(wf._e(c, "snap", True))
    by = {n["id"]: n for n in nodes}
    if "x_err" in sh["handling"]:
        at = by[branch_at] if branch_at else by["v"]
        nodes.append(wf._n("err", "xf", "x_err", at["x"], at["y"] + 170))
        edges.append(wf._e("v", "err"))
        if branch_at:
            edges.append(wf._e(branch_at, "err"))
    if "x_audit" in sh["handling"]:
        nodes.append(wf._n("aud", "xf", "x_audit", by["m"]["x"], by["m"]["y"] + 170))
        edges.append(wf._e("m", "aud"))
    if "x_pub" in sh["handling"] and c != "c_out":
        nodes.append(wf._n("pub", "xf", "x_pub", by[c]["x"], by[c]["y"] - 150))
        edges.append(wf._e(c, "pub"))
    return {"nodes": nodes, "edges": edges}


def _outbound(sh: dict) -> dict:
    """bOut's shape, with the requested steps between the instruction envelope and the delivery step."""
    sid, ch = sh["sid"], sh["ch"]
    y0, X = 200, 206
    rec = {"api": "a_api", "event": "a_evt", "file": "a_file", "proc": "a_proc"}.get(ch or "", "a_api")
    nodes = [
        wf._n("c_dec", "fixed", "c_dec", 24, y0),
        wf._n("appr", "fixed", "appr", 24 + X, y0),
        wf._n("t_env", "xf", "x_env", 24 + 2 * X, y0),
    ]
    edges = [wf._e("c_dec", "appr", True), wf._e("appr", "t_env")]
    prev, col = "t_env", 3
    for r in [r for r in OUT_STEPS if r in sh["steps"]]:
        nid = _step_id(r)
        nodes.append(wf._n(nid, "xf", r, 24 + col * X, y0))
        edges.append(wf._e(prev, nid))
        prev, col = nid, col + 1
    nodes.append(wf._n("a", "act", rec, 24 + col * X, y0))
    edges.append(wf._e(prev, "a"))
    prev, col = "a", col + 1
    if ch == "file":
        nodes.append(wf._n("f_man", "xf", "x_man", 24 + col * X, y0))
        edges.append(wf._e(prev, "f_man"))
        prev, col = "f_man", col + 1
    nodes.append(wf._n("w", "wconn", sid, 24 + col * X, y0))
    edges.append(wf._e(prev, "w"))
    col += 1
    nodes.append(wf._n("c_out", "fixed", "c_out", 24 + col * X, y0))
    edges.append(wf._e("w", "c_out"))
    if ch == "file" and "x_cb" in sh["handling"]:
        nodes += [
            wf._n("f_cb", "xf", "x_cb", 24 + col * X, y0 + 170),
            wf._n("f_note", "xf", "x_notify", 24 + (col + 1) * X, y0 + 170),
        ]
        edges += [wf._e("w", "f_cb"), wf._e("f_cb", "f_note")]
    if "x_audit" in sh["handling"]:
        nodes.append(wf._n("aud", "xf", "x_audit", 24 + 2 * X, y0 + 170))
        edges.append(wf._e("t_env", "aud"))
    return {"nodes": nodes, "edges": edges}


def tailored_name(sh: dict, trig: dict) -> str:
    kind = sh["kind"]
    added = list(sh["steps"])
    if kind == "ingest":
        s = SOURCES[sh["sid"]]
        base = f"{wf.SH.get(sh['sid'], s['name'])} ingest"
        tail = " and ".join(PHRASE[r] for r in added[:2]) if added else wf.trig_text(trig).lower()
        return f"{base} · {tail}"[:80]
    if kind == "out":
        s = SOURCES[sh["sid"]]
        base = f"Approved instructions to {s['vendor']} {CH_BY[sh['ch']]}"
        return (base + (" · " + " and ".join(PHRASE[r] for r in added[:2]) if added else ""))[:80]
    if kind == "dec":
        return {"standard": "Six-gate decision", "pool": "Pool allocation decision", "gap": "Evidence-gap decision"}[sh["dec"]]
    return "New pipeline"


def _lc(label_: str) -> str:
    """A step label inside a sentence: "Timestamps to UTC" -> "timestamps to UTC"."""
    return label_[:1].lower() + label_[1:]


def tailored_desc(sh: dict, g: dict, trig: dict) -> str:
    kind = sh["kind"]
    tt = wf.trig_text(trig)
    if kind == "ingest":
        s = SOURCES[sh["sid"]]
        target = MAP_TARGET.get(sh["sid"]) or SRC_TYPES[s["type"]]["target"]
        refs = [n["ref"] for n in g["nodes"] if n["k"] == "xf"]
        arrive = " and ".join(
            wf.CH_ARR[c] for c in ("api", "event", "file") if {"api": "x_gw", "event": "x_evt", "file": "x_trig"}[c] in refs
        )
        mid = [_lc(wf._xf_req(r)["label"]) for r in STEP_ORDER if r in refs]
        tail = []
        if "x_err" in refs:
            tail.append("rejected rows held in the error handler")
        if "x_audit" in refs:
            tail.append("run metrics in the audit log")
        if "x_pub" in refs:
            tail.append("a model-updated event on the stream")
        return (
            f"{tt}: reads {s['name']} ({s['vendor']}) by {arrive or 'its feed'} into the {target} model, through validation"
            + (", " + ", ".join(mid) if mid else "") + " and field mapping"
            + ("; " + ", ".join(tail) if tail else "") + "."
        )  # fmt: skip
    if kind == "out":
        s = SOURCES[sh["sid"]]
        mid = [_lc(wf._xf_req(r)["label"]) for r in OUT_STEPS if r in sh["steps"]]
        return (
            f"{tt}: an approved decision goes to {s['name']} ({s['vendor']}) as {wf.CH_DEL[sh['ch']]}, wrapped in an instruction "
            "envelope" + (" with " + ", ".join(mid) if mid else "") + "; the returned outcome is recorded"
            + ("; the instruction is written to the audit log" if "x_audit" in sh["handling"] else "") + "."
        )  # fmt: skip
    if kind == "dec":
        return f"{tt}: {DECISIONS[sh['dec']][1]} The approved instruction is sent and its outcome reconciled."
    return "Blank pipeline. Drag steps from the left and connect them."


def _why(n: dict, added: bool) -> str:
    k, ref = n["k"], n["ref"]
    if k == "fixed":
        return "Fixed step: Circularity owns it; it is never moved or removed."
    if k == "conn":
        s = SOURCES[ref]
        return f"Reads {s['name']} ({s['vendor']}) · {s['mode']} · {s['auth']}."
    if k == "wconn":
        s = SOURCES[ref]
        return (
            f"Delivers to {s['name']} ({s['vendor']}), which accepts {', '.join(wf.CH_DEL[c] for c in wf.DELIVER.get(ref, []))}."
        )
    if k == "map":
        n_maps = len(MAPPINGS.get(ref) or [])
        return f"Maps {n_maps} {wf.SH.get(ref)} fields to the {MAP_TARGET.get(ref)} model, so no raw vendor value enters it."
    if k == "act":
        return next(t for t in wf.ACT_TYPES if t["id"] == ref)["desc"]
    if k == "tool":
        return f"Agent tool {ref}, in the order the decision rules require."
    d = wf._xf_req(ref)["desc"]
    return ("You asked for it. " if added else "Required to run. ") + d


def _ready(sh: dict, g: dict, name: str, owner: str, trig: dict, retries: int, alert: str, notes: list[str],
           understood: list[dict], a: dict) -> dict[str, Any]:  # fmt: skip
    kind, sid, ch = sh["kind"], sh["sid"], sh["ch"]
    wkind = "dec" if kind == "dec" else "pipe"
    v = wf.validate(g, wkind)
    dropped = []
    while (er := [x for x in v if x["sev"] == "error"]) and (bad := next((x for x in er if x["id"].startswith("s_")), None)):
        # an added step the checks refuse: leave it out, rewire around it, and say so
        nid = bad["id"]
        ins = [e["a"] for e in g["edges"] if e["b"] == nid]
        outs = [e["b"] for e in g["edges"] if e["a"] == nid]
        g["edges"] = [e for e in g["edges"] if nid not in (e["a"], e["b"])] + [wf._e(x, y) for x in ins for y in outs]
        g["nodes"] = [n for n in g["nodes"] if n["id"] != nid]
        dropped.append(bad["msg"])
        for i, e in enumerate(g["edges"]):
            e["id"] = f"e{i}"
        v = wf.validate(g, wkind)
    notes += [f"Left out: {m}" for m in dropped]
    errs = [x for x in v if x["sev"] == "error"]
    if errs:
        return {"status": "blocked", "questions": [], "notes": notes + [x["msg"] for x in errs], "understood": understood,
                "answers": a, "plan": None, "redirect": None}  # fmt: skip
    # every block is either required to run (MINIMAL) or one the person asked for; nothing comes from a template
    asked = set(sh["steps"]) | set(sh["handling"]) | ({"x_evt"} if sh.get("arrive") == "both" else set())
    order = studio._order(g)
    by = {n["id"]: n for n in g["nodes"]}
    steps = []
    for nid in order:
        n = by[nid]
        is_new = n["k"] == "xf" and n["ref"] in asked
        steps.append({
            "id": nid, "label": wf.label(n), "kind": n["k"], "fixed": n["k"] == "fixed",
            "status": "fixed" if n["k"] == "fixed" else "added" if is_new else "required", "why": _why(n, is_new),
        })  # fmt: skip
    dflt_trig = default_trigger(kind, sid)
    changed = []
    if trig != dflt_trig:
        changed.append(f"Trigger: {wf.trig_text(trig)} (default: {wf.trig_text(dflt_trig)})")
    if retries != 3:
        changed.append(f"Retries: {retries} (default: 3)")
    if alert != wf.ALERTS[0]:
        changed.append(f"Alert when: {alert} (default: {wf.ALERTS[0]})")
    if kind == "dec" and sh["dec"] != "standard":
        changed.append(f"Decision flow: {DECISIONS[sh['dec']][0]}")
    std_owner = SOURCES[sid]["owner"] if sid else "Decision Services" if kind == "dec" else "Unassigned"
    if owner != std_owner:
        changed.append(f"Owner: {owner} (default: {std_owner})")
    desc = tailored_desc(sh, g, trig)
    diff = {
        "required": [x["label"] for x in steps if x["status"] != "added"],
        "added": [x["label"] for x in steps if x["status"] == "added"],
        "changed": changed,
    }
    warns = [x["msg"] for x in v if x["sev"] == "warn"]
    infos = [x["msg"] for x in v if x["sev"] == "info"]
    summary = (
        f"{name}: {len(g['nodes'])} blocks, {len(diff['required'])} required to run"
        + (f" and {len(diff['added'])} you asked for ({', '.join(diff['added'])})" if diff["added"] else "")
        + "; checks show 0 errors"
        + (f" and {len(warns)} warning{'s' if len(warns) != 1 else ''}" if warns else "")
        + ". Nothing is created until you press Create workflow."
    )
    create: dict[str, Any] = {"type": kind, "name": name, "desc": desc, "graph": copy.deepcopy(g)}
    if sid:
        create["src"] = sid
    if ch:
        create["ch"] = ch
    save: dict[str, Any] = {
        "name": name,
        "graph": copy.deepcopy(g),
        "owner": owner,
        "trig": trig,
        "note": "Built with the AI workflow builder",
    }
    if kind != "blank":
        save |= {"retries": retries, "alert": alert}
    return {
        "status": "ready", "questions": [], "notes": notes, "understood": understood, "answers": a, "redirect": None,
        "plan": {
            "name": name, "desc": desc, "type": kind, "type_label": TYPES[kind][0], "src": sid, "ch": ch,
            "decision": sh["dec"] if kind == "dec" else None, "trigger": trig, "trigger_text": wf.trig_text(trig),
            "owner": owner, "settings": {"retries": retries, "alert": alert}, "graph": g,
            "checks": {"errors": [], "warnings": warns, "notes": infos}, "steps": steps, "diff": diff, "summary": summary,
            "create": create, "save": save,
        },
    }  # fmt: skip


@guard("workflow.plan")
def plan_guard(i: dict[str, Any], ctx: CallContext):  # noqa: ARG001 - every guard takes (input, context)
    if len(i["prompt"]) > 2000:
        return "validation_error", "Keep the description under 2,000 characters."
    if not isinstance(i.get("answers") or {}, dict):
        return "validation_error", '"answers" must be an object.'
    return None


@implement("workflow.plan")
def plan_action(i: dict[str, Any], ctx: CallContext):
    return plan(i["prompt"], i.get("answers") or {}, ctx)
