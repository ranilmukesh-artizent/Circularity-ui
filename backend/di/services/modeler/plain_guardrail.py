"""A guardrail stated in plain words (plan 9, P9-10.14, story TN-14; registry entries I-4 and I-13).

    read_clause(clause, pack) -> PlainReading | None   what one sentence says: a new approval guardrail, a refused waiver, or None
    vouches(op, pack, text) -> str | None              why a model's new guardrail is not the sentence's (None: it is)
    action_of(pack_key, guardrail_id) -> str | None    the words of the work item an approval of this guardrail opens
    would_change(op, items, pack) -> int               how many of a history's decisions the guardrail would have held

"Resale of current-generation cards needs approval from network planning" is read, by code, into one `add_approver` operation
that creates an Approval guardrail (`di.services.modeler.overlay.AddApprover`): the route it covers, the facts that scope it and
the role that approves. The model reads the same words first when the router has one (`di.services.agents.config_agent`), and
this code checks what it returned and wins; a sentence the code cannot place gives nothing, never a guess.

The words a pack answers to (its routes, the facts and values a sentence may name, the guardrail ids and the wording of the
item) are the pack's own vocabulary in `plain_words_<pack key>.py` (a `Vocab`); a pack with none places nothing. The roles are
the pack's `roles`. A sentence that waives a compliance guardrail ("no longer needs", "skip", "without") is read as a refusal
naming that guardrail: there is no operation that weakens one (the customer layer only tightens, I-4).

Owns: the reading of a clause and the vocabulary shape. Never does: read a session, call a model, save or approve anything
(the guardrail is held for a person, maker-checker, `forbidden.py`). Pure. Kinective's Legal team reviews export-control wording
before it is relied on.
"""

import importlib
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from di.services.modeler.gates import Cond, conds_hold
from di.services.modeler.overlay import AddApprover, GuardWhen, RouteIs, route_of
from di.services.modeler.pack import Pack, PackGuardrail

STOP = frozenset("a an the and or of to for from in on at by with any before only is are be it its this that".split())
_WAIVE = re.compile(
    r"\b(?:no longer needs?|(?:does|do)\s*(?:not|n't)\s+need|doesn't need|don't need|without|skip(?:ping)?|waive[sd]?|waiving|"
    r"exempt(?:ed|s)?|bypass(?:ed|es|ing)?|drop(?:ped|ping)? the)\b",
    re.I,
)
_NEEDS = re.compile(
    r"^(?P<subject>.+?)\s+(?:needs?|requires?|must (?:get|have)|should (?:get|have))\s+(?:an?\s+)?(?:approval|sign ?off)\s+"
    r"(?:from|by)\s+(?P<who>.+?)\s*[.;!?]?$",
    re.I,
)
_BY = re.compile(r"^(?P<subject>.+?)\s+(?:must|should)\s+be\s+approved\s+by\s+(?P<who>.+?)\s*[.;!?]?$", re.I)


@dataclass(frozen=True)
class ValueWords:
    """A value a sentence may give a fact ("current" for market.generation) and the code in the guardrail's id."""

    literal: str
    code: str


@dataclass(frozen=True)
class FactWords:
    """A fact a sentence may scope by: the noun that follows the value ("generation": "current-generation cards")."""

    fact: str
    noun: str
    values: dict[str, ValueWords]


@dataclass(frozen=True)
class RangeWords:
    """A number a sentence may bound a fact by ("younger than 5 years" for asset.age_years): the words for a bound below ("lt")
    and above ("gt") the number, and the unit that follows it (P9-11.14)."""

    fact: str
    below: tuple[str, ...]
    above: tuple[str, ...]
    unit: str


@dataclass(frozen=True)
class Vocab:
    id_prefix: str  # "AP-TN": the guardrail id is `<prefix>-<value code>`
    routes: dict[str, tuple[str, ...]]  # route id -> the words that name it in a sentence
    facts: tuple[FactWords, ...]
    action: str  # the words of the work item an approval of a guardrail of this vocabulary opens
    default_route: str  # the route that is not named in the id
    ranges: tuple[RangeWords, ...] = ()  # numbers a sentence may bound a fact by
    ident: Callable[[str, list[str]], str] | None = None  # (route, codes) -> the guardrail id, when it is not `<prefix>-<codes>`


@dataclass(frozen=True)
class PlainReading:
    """`op` the new guardrail (None for a refusal); `refused` the (message, guardrail text) of each guardrail a waiver names."""

    op: AddApprover | None = None
    refused: list[tuple[str, str]] = field(default_factory=list)


def vocab_of(pack_key: str) -> Vocab | None:
    try:
        return importlib.import_module(f"di.services.modeler.plain_words_{pack_key}").VOCAB
    except ModuleNotFoundError:
        return None


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[-_–]", " ", s.lower())).strip()


def _content(s: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]+", _norm(s)) if len(w) >= 4 and w not in STOP}


def _role(who: str, pack: Pack) -> str | None:
    """The pack's role the words name: all of its words, nothing else but "the" and "team"."""
    want = {w for w in _norm(who).split() if w not in ("the", "team")}
    hit = [k for k in pack.roles if set(_norm(k).split()) == want]
    return hit[0] if len(hit) == 1 else None


def _waived(clause: str, pack: Pack) -> list[PackGuardrail]:
    """The compliance guardrails a waiver names: two of the distinctive words of its text, or the role that approves it."""
    n = _norm(clause)
    words = _content(clause)
    out: list[PackGuardrail] = []
    for g in pack.guardrails:
        if not (g.locked or g.type == "Compliance"):
            continue
        by_role = any(_norm(a) in n for a in g.approvers)
        if len(words & _content(g.text)) >= 2 or by_role:
            out.append(g)
    return out


def _scope(subject: str, v: Vocab) -> tuple[list[Cond], list[str]] | None:
    """The conditions the subject names ("current generation" -> market.generation eq current) and their id codes; None when a
    noun of the vocabulary has a value it does not know."""
    n = _norm(subject)
    conds: list[Cond] = []
    codes: list[str] = []
    for f in v.facts:
        for m in re.finditer(rf"\b(?P<w>[a-z]+)\s+{re.escape(_norm(f.noun))}\b", n):
            val = f.values.get(m.group("w"))
            if val is None:
                return None
            conds.append(Cond(fact=f.fact, op="eq", value=val.literal))
            codes.append(val.code)
    for r in v.ranges:
        for m in re.finditer(
            rf"\b(?P<w>{'|'.join(map(re.escape, (*r.below, *r.above)))})\s+(?P<n>\d+(?:\.\d+)?)\s+{r.unit}\b", n
        ):
            num = float(m.group("n"))
            conds.append(Cond(fact=r.fact, op="lt" if m.group("w") in r.below else "gt", value=num))
            codes.append(f"{num:g}".replace(".", ""))
    return conds, codes


def read_clause(clause: str, pack: Pack) -> PlainReading | None:
    """What the sentence says, for a pack that has a vocabulary: a waiver of a compliance guardrail (a refusal), or "<route words>
    of <scope> needs approval from <role>" (one new guardrail), else None."""
    v = vocab_of(pack.key)
    if v is None:
        return None
    if _WAIVE.search(clause):
        named = _waived(clause, pack)
        if not named:
            return None
        return PlainReading(refused=[(f"Blocked: this waives the compliance guardrail {g.text}.", g.text) for g in named])
    m = _NEEDS.match(clause.strip()) or _BY.match(clause.strip())
    if m is None:
        return None
    role = _role(m.group("who"), pack)
    subject = _norm(m.group("subject"))
    routes = [r for r, words in v.routes.items() if any(re.search(rf"\b{w}\b", subject) for w in words) and r in _route_ids(pack)]
    scope = _scope(m.group("subject"), v)
    if role is None or len(routes) != 1 or scope is None or not scope[0]:
        return None
    conds, codes = scope
    route = routes[0]
    gid = (
        v.ident(route, codes)
        if v.ident
        else "-".join([v.id_prefix, *codes, *([] if route == v.default_route else [route.upper()])])
    )
    op = AddApprover(
        id="op-0", op="add_approver", guardrail_id=gid, type="Approval", stage="decide",
        when=GuardWhen(all=[RouteIs(route=route), *conds]), approver=role, text=clause.strip().rstrip(".;!?"),
    )  # fmt: skip
    return PlainReading(op=op)


def _route_ids(pack: Pack) -> set[str]:
    return {r.id for r in pack.routes}


def vouches(op: AddApprover, pack: Pack, text: str) -> str | None:
    """None when a model's new guardrail is what the description says; else why not (the draft is refused and retried): its
    words are in the description, its facts and values are the pack's vocabulary, and its route and approver are the pack's."""
    v = vocab_of(pack.key)
    if v is None:
        return f"The {pack.key} pack has no plain-words vocabulary: a guardrail cannot be placed from a sentence."
    if _norm(op.text) not in _norm(text):
        return f"The guardrail {op.guardrail_id} quotes words the description does not contain."
    names = {f.fact: {x.literal for x in f.values.values()} for f in v.facts}
    bounds = {r.fact for r in v.ranges}
    for c in op.when.all if op.when else []:
        if isinstance(c, Cond) and c.fact in bounds and c.op in ("lt", "gt") and isinstance(c.value, int | float):
            continue  # a number the vocabulary lets a sentence bound this fact by
        if isinstance(c, Cond) and (c.fact not in names or c.value not in names[c.fact] or c.op != "eq"):
            return (
                f"The guardrail {op.guardrail_id} scopes by {c.fact} {c.op} {c.value}, which the {pack.key} pack does not offer."
            )
    return None


def action_of(pack_key: str, guardrail_id: str) -> str | None:
    """The words of the item an approval of the customer's guardrail opens (the vocabulary's), None for another guardrail."""
    v = vocab_of(pack_key)
    return v.action if v is not None and guardrail_id.startswith(v.id_prefix + "-") else None


def would_change(op: AddApprover, decisions: Sequence[tuple[str | None, Mapping[str, Any]]], pack: Pack) -> int:
    """How many decisions of a history, each (the route taken, the facts known at the time as flat dotted names), the new
    guardrail would have held for a person: those that took its route and whose facts meet every condition. Counted on the
    route taken, as a person reads "resale needs approval"; the replay of the decider (`di.services.replay.run`) says how many it
    would hold when the flow recommends. A count; the caller labels it *modelled*."""
    scope = op.when.all if op.when is not None else []
    routes = [r for r in scope if isinstance(r, RouteIs)]
    route = route_of(pack, routes[0].route) if len(routes) == 1 else None
    conds = [c.model_dump() for c in scope if isinstance(c, Cond)]
    if route is None:
        return 0
    return sum(1 for taken, facts in decisions if taken == route and conds_hold(conds, facts, pack))
