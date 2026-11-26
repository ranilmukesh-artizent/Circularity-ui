"""A plain-language change turned into a checked proposal (plan 8, MVP-5.2; Domain spec D10; the prototype's
buildProposal, lines 2446-2460). It never saves anything: applying it is the person's own flow.saveDraft.

- A text that would change a locked guardrail (`text_breaks`), or that weakens a guardrail it names
  (`text_names_guardrail`, plan 10 T8), gives a `blocked` proposal with no graph.
- "add … step before|for|after <path>" gives a `step` proposal: a process step after that path's node.
- Otherwise the text is parsed (`parse_rule`); no path gives an `unclear` proposal. A rule proposal gets the next rule
  id, is placed between the last node feeding the decision and the decision, is validated (only its own checks and the
  conflicts) and is simulated against the current draft. A rule that breaks a guardrail is `blocked` with its graph,
  so the canvas can show it in red until it is dismissed.
"""

import copy
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

from di.services.modeler.compile import CompiledRule, compile_flow
from di.services.modeler.flow import Flow, Node, fe, fn, node_label
from di.services.modeler.guard import ANY_GUARDRAIL, rule_breaks, text_breaks, text_names_guardrail
from di.services.modeler.parse import ParsedRule, parse_rule
from di.services.modeler.simulate import SimResult
from di.services.modeler.templates import Template
from di.services.modeler.text import rule_text
from di.services.modeler.validate import Check, validate_flow

Kind = Literal["rule", "step", "blocked", "unclear"]
STEP = re.compile(r"add (?:an? )?(.+?) step (?:before|for|after) (.+)", re.IGNORECASE)


@dataclass(frozen=True)
class Proposal:
    kind: Kind
    text: str
    graph: Flow | None = None
    node_id: str | None = None
    rid: str | None = None
    label: str | None = None
    guard: str | None = None
    checks: list[Check] = field(default_factory=list)
    sim: SimResult | None = None
    msg: str = ""


def _noun(t: Template) -> str:
    return "channel" if t.key == "device" else "path"


def _names(t: Template) -> str:
    return ", ".join(p.name for p in t.paths)


def _free(f: Flow, base: str) -> str:
    used = {n["id"] for n in f["nodes"]}
    nid, k = base, 2
    while nid in used:
        nid, k = f"{base}-{k}", k + 1
    return nid


def next_rid(t: Template, f: Flow) -> str:
    """The next rule id: the highest number among the flow's rule ids plus one, two digits (`T.pre + "-" + nn`)."""
    nums = [int(n["rid"].rsplit("-", 1)[-1]) for n in f["nodes"] if n.get("rid") and n["rid"].rsplit("-", 1)[-1].isdigit()]
    return f"{t.pre}-{max([0, *nums]) + 1:02d}"


def _blocked_text(t: Template, text: str, gid: str) -> Proposal:
    if gid == ANY_GUARDRAIL:
        msg = ("I can't draft this. It would weaken the guardrails. Each guardrail is changed only by its owner, never by "
               "me or the Modeler.")  # fmt: skip
        return Proposal("blocked", text, msg=msg)
    g = next(x for x in t.guardrails if x.id == gid)
    msg = (f"I can't draft this. It would change {gid} ({g.text}), which is owned by {g.owner}. Guardrails are changed "
           "only by their owner, never by me or the Modeler.")  # fmt: skip
    return Proposal("blocked", text, guard=gid, msg=msg)


def refused_text(t: Template, text: str) -> str | None:
    """The guardrail a plain-language text would change (`text_breaks`) or weaken by name (`text_names_guardrail`)."""
    return text_breaks(t, text) or text_names_guardrail(t, text)


def _step(t: Template, draft: Flow, text: str, m: re.Match[str], owner: str, sim: Callable[[Flow], SimResult | None]) -> Proposal:
    c = copy.deepcopy(draft)
    want = m.group(2).lower()
    tgt = next((n for n in c["nodes"] if n["t"] == "path" and n["label"].lower() in want), None)
    if tgt is None:
        return Proposal("unclear", text, msg=f"I couldn't find “{m.group(2)}” in this flow. Name one of: {_names(t)}.")
    nm = m.group(1)[:1].upper() + m.group(1)[1:]
    sid = _free(c, "s-" + re.sub(r"[^a-z0-9]+", "-", nm.lower()).strip("-"))
    ex = next((e for e in c["edges"] if e["a"] == tgt["id"]), None)
    c["nodes"].append(fn(sid, "step", tgt["x"] + 196, tgt["y"], nm, "Process step", owner=owner, ai=True))
    if ex:
        c["edges"] = [e for e in c["edges"] if e is not ex] + [fe(tgt["id"], sid), fe(sid, ex["b"])]
    else:
        c["edges"].append(fe(tgt["id"], sid))
    after = next((n for n in draft["nodes"] if ex and n["id"] == ex["b"]), tgt)
    label = f"Step “{nm}” before {node_label(after, t).lower() if ex else 'the end'}, after {tgt['label']}"
    return Proposal("step", text, c, sid, label=label, sim=sim(c))


def fill_parsed(r: ParsedRule, fill: Mapping[str, Any] | None) -> ParsedRule:
    """The parsed rule with what another reading (the optional model, MVP-5.3) adds where the parser found nothing:
    the path, and scope keys the parser did not read. The parser's action stands."""
    if not fill:
        return r
    extra = {k: v for k, v in (fill.get("scope") or {}).items() if k not in r.scope}
    return ParsedRule(r.path or fill.get("path"), r.action, {**r.scope, **extra})


def _rule(
    t: Template, draft: Flow, text: str, owner: str, sim: Callable[[Flow], SimResult | None], fill: Mapping[str, Any] | None
) -> Proposal:
    r = fill_parsed(parse_rule(t, text), fill)
    if not r.path:
        return Proposal("unclear", text, msg=f"I couldn't tell which {_noun(t)} this is about. Name one of: {_names(t)}.")
    c = copy.deepcopy(draft)
    rid = next_rid(t, c)
    dec = next(n for n in c["nodes"] if n["t"] == "decision")
    gate = next(n for n in c["nodes"] if n["t"] == "gate")
    into = next((e for e in c["edges"] if e["b"] == dec["id"]), None)
    last = into["a"] if into else gate["id"]
    rules = [n for n in c["nodes"] if n["t"] == "rule"]
    y = (max(n["y"] for n in rules) if rules else 50) + 140
    nid = _free(c, "r-" + rid)
    node: Node = fn(nid, "rule", gate["x"], y, "", "", rid=rid, action=r.action, path=r.path, scope=r.scope, owner=owner,
                    ai=True, src=text)  # fmt: skip
    c["nodes"].append(node)
    c["edges"] = [e for e in c["edges"] if e is not into] + [fe(last, nid), fe(nid, dec["id"])]
    words = rule_text(t, node)
    label = f"{rid}: {words}"
    checks = [x for x in validate_flow(t, c) if x.node_id == nid or x.msg.startswith("Conflict")]
    if g := rule_breaks(t, node):
        gd = next(x for x in t.guardrails if x.id == g)
        msg = (f"I drafted {rid} ({words}), but it breaks {g}: {gd.text}. I won't apply it. It is shown in red on the "
               "canvas until you dismiss it.")  # fmt: skip
        return Proposal("blocked", text, c, nid, rid, label, g, checks, None, msg)
    return Proposal("rule", text, c, nid, rid, label, None, checks, sim(c))


def build_proposal(
    t: Template,
    draft: Flow,
    text: str,
    actor_role: str,
    decide_queue: Callable[[list[CompiledRule]], SimResult] | None,
    fill: Mapping[str, Any] | None = None,
) -> Proposal:
    """The proposal for `text` on the current draft; `decide_queue` simulates a candidate rule set against the draft's
    rules on the open queue (None: no simulation); `fill` completes what the parser left empty (`fill_parsed`)."""
    text = text.strip()

    def sim(g: Flow) -> SimResult | None:
        return decide_queue(compile_flow(t, g)) if decide_queue else None

    if gid := refused_text(t, text):
        return _blocked_text(t, text, gid)
    if m := STEP.search(text):
        return _step(t, draft, text, m, actor_role, sim)
    return _rule(t, draft, text, actor_role, sim, fill)
