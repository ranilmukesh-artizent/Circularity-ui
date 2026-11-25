"""The configuration agent's pure core (plan 9, P9-2.7; story X-02; registry entry I-13).

    read_text(text, packs=None) -> Reading         the reading log: word count, controls, systems, unit
    match_pack(reading, text, packs) -> PackMatch  the closest pack (RapidFuzz token_set_ratio); below 60, nearest only
    draft_change_set(text, org, *, packs, answer, reader) -> ChangeSet   the change set of typed overlay operations

A person describes a business in words; the agent turns the controls they state into customer overlay operations
(`di.services.modeler.overlay`, I-4: tighten, add_approver, add_step, shortcut, set_param), places the answer to the pack's
one clarifying question, and marks every operation the person did not state as assumed. It writes configuration, never code:
`ChangeSet` has `extra="forbid"` and no field that holds a script or an expression. A weaker value on a guardrail or a skip of a
compliance check is never an operation: it goes to `blocked` with the guardrail named. The whole set is validated by
`apply_overlay`, so a refusal names the operation (`ChangeSetError`).

The text is data. With a model (`drafter`, `playbooks.pack_author`, no tools) the model drafts first and the checks of
`_accept` always win (typed ops only, weaker values and compliance skips go to `blocked`, deterministic controls override,
`apply_overlay` must pass, one retry then the deterministic path, `ChangeSet.by_model` false). Without one (R16) the
deterministic path answers: `read_text`, `match_pack` and the pack's own question.
Owns: the models and the deterministic reading, matching and drafting. Never does: read a session, call a model, save
anything or approve anything (rule 10): the actions (`di.services.actions.config_agent`) store the set and hold the overlay
draft as one proposal for a person.

Docs read: rapidfuzz 3.14.6 `fuzz.token_set_ratio(s1, s2, *, processor=None, score_cutoff=None)` (no preprocessing by default,
so `utils.default_process` lowercases and strips punctuation first), https://rapidfuzz.github.io/RapidFuzz/Usage/fuzz.html and
.../Usage/utils.html.
"""

import json
import logging
import re
from collections.abc import Callable, Sequence
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from rapidfuzz import fuzz, utils

from di.services.modeler.gates import pack_gates
from di.services.modeler.overlay import AddApprover, AddStep, OverlayError, OverlayOp, Shortcut, Tighten, apply_overlay, parse_ops
from di.services.modeler.pack import Pack, PackGuardrail, load_pack, pack_keys
from di.services.modeler.stages import STAGE_KEYS

log = logging.getLogger(__name__)

BAR = 60  # a pack score below this is "nearest only": no pack is invented
TIE = 5  # a model reading breaks a tie within this many points
MAX_TEXT = 4000
# Market codes the reading knows beside the packs' regions (two capital letters; "IT" and "IN" are left out: they are words).
MARKETS = frozenset("US CA MX BR GB DE FR ES NL BE SE NO DK FI PL AT CH IE PT CN JP KR IN AU NZ SG AE ZA".split()) - {"IN"}
# Roles named in a description that a pack may not list; the pack's own roles and owners are read as well.
COMMON_ROLES = ("fleet manager", "commercial manager", "account manager", "service operations", "customer care", "finance")
STOP = frozenset(
    "a an the and or of to for from in on at by with we our us is are be it its this that as into their they you your".split()
)

Kind = Literal["amount", "percent", "role", "market", "condition"]


class Control(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Kind
    text: str
    value: str | float | list[str]


class Reading(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    word_count: int
    controls: list[Control] = Field(default_factory=list)
    systems: list[str] = Field(default_factory=list)
    unit: str | None = None
    by_model: bool = False


class PackMatch(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    key: str
    score: float
    nearest_only: bool


class Option(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    label: str
    ops: list[OverlayOp] = Field(default_factory=list)  # what choosing it adds (a model's question; the pack's is empty here)


class Question(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    text: str
    options: list[Option]


class Blocked(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    text: str
    guardrail: str


class SystemRef(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    adapter: bool


class ChangeSet(BaseModel):
    """What the agent proposes. No field holds code, a script or an expression (`extra="forbid"`; operations are the typed
    ones of I-4)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    pack: str
    base_version: str
    ops: list[OverlayOp] = Field(default_factory=list)
    assumed: list[str] = Field(default_factory=list)  # ids of operations the person did not state
    blocked: list[Blocked] = Field(default_factory=list)
    systems: list[SystemRef] = Field(default_factory=list)
    kpis: list[str] = Field(default_factory=list)
    question: Question | None = None
    answer: str | None = None
    by_model: bool = False  # a model drafted it (every check of `draft_change_set` still applied)


class ModelDraft(BaseModel):
    """What the pack author model returns (`playbooks.pack_author`): a draft that code then checks. `systems` are names."""

    pack: str
    ops: list[OverlayOp] = Field(default_factory=list)
    assumed: list[str] = Field(default_factory=list, description="Ids of ops the person did not state.")
    kpis: list[str] = Field(default_factory=list)
    systems: list[str] = Field(default_factory=list)
    question: Question | None = Field(default=None, description="The one open question, with the ops each option adds.")


# (text, reading, packs, answer, error of the last try) -> a draft, or None when no model is available
Drafter = Callable[[str, "Reading", Sequence[Pack], str | None, str | None], ModelDraft | None]


class ChangeSetError(ValueError):
    """A change set that does not validate: `code` is `validation_error`; `op_id` names the operation when there is one."""

    code = "validation_error"

    def __init__(self, message: str, op_id: str | None = None) -> None:
        super().__init__(message)
        self.message, self.op_id = message, op_id


# ---------------------------------------------------------------- reading
_AMOUNT = re.compile(r"(?:[$€£]\s?(?P<a>\d[\d,]*(?:\.\d+)?)(?P<k>[kK]\b)?|(?P<b>\d[\d,]*(?:\.\d+)?)\s?(?:USD|EUR|GBP)\b)")
_PERCENT = re.compile(r"(?P<n>\d+(?:\.\d+)?)\s?(?:%|percent\b)")
_DURATION = re.compile(
    r"\b(?P<cmp>over|under|older than|younger than|within|more than|less than|at least)\s+(?P<n>\d+)"
    r"\s*(?P<u>day|week|month|year)s?\b",
    re.I,
)
_MARKET = re.compile(r"\b[A-Z]{2}\b")
_SKIP = re.compile(r"\bskip(?:ping)?\s+(?:the\s+|all\s+)?(?P<what>[^.;,:]+)", re.I)
_LOW = ("over", "older than", "more than", "at least")


def _clauses(text: str) -> list[str]:
    return [c.strip() for c in re.split(r"(?<=[.;!?])\s+|\n+", text) if c.strip()]


def _num(s: str) -> float:
    return float(s.replace(",", ""))


def _pack_roles(packs: Sequence[Pack]) -> list[str]:
    roles = set(COMMON_ROLES)
    for p in packs:
        roles.add(p.author_role)
        roles.update(g.owner for g in p.guardrails)
        roles.update(r.owner for r in p.routes)
        roles.update(a[2] for a in p.actors)
        roles.update(t.owner_role for t in p.runtime.exception_types)
    return sorted((r for r in roles if r), key=len, reverse=True)


def _markets(packs: Sequence[Pack]) -> set[str]:
    return set(MARKETS) | {r for p in packs for r in p.regions}


def _systems_of(p: Pack) -> list[str]:
    return [s.name for s in p.data.systems] + [r.app for r in p.routes if r.app]


def _find(pattern: str, text: str) -> bool:
    return re.search(rf"(?<![\w]){re.escape(pattern)}(?![\w])", text, re.I) is not None


def read_text(text: str, packs: Sequence[Pack] | None = None) -> Reading:
    """The reading log of a description (pure): word count; amounts (`$600`), percents, market codes, roles and conditions
    ("over 3 months", "older than 2 years"); the systems and the unit that the packs name. `packs` defaults to every pack."""
    packs = list(packs) if packs is not None else [load_pack(k) for k in pack_keys()]
    controls: list[Control] = []
    markets = _markets(packs)
    roles = _pack_roles(packs)
    for clause in _clauses(text):
        for m in _AMOUNT.finditer(clause):
            n = _num(m.group("a") or m.group("b"))
            n = n * 1000 if m.group("k") else n
            controls.append(Control(kind="amount", text=clause[: m.end()], value=n))
        for m in _PERCENT.finditer(clause):
            controls.append(Control(kind="percent", text=clause[: m.end()], value=_num(m.group("n"))))
        for m in _DURATION.finditer(clause):
            controls.append(
                Control(
                    kind="condition", text=m.group(0), value=f"{m.group('cmp').lower()} {m.group('n')} {m.group('u').lower()}s"
                )
            )
        found = [c for c in dict.fromkeys(_MARKET.findall(clause)) if c in markets]
        if found:
            controls.append(Control(kind="market", text=clause.rstrip(".;!?"), value=found))
        for r in roles:
            if _find(r, clause):
                controls.append(Control(kind="role", text=clause.rstrip(".;!?"), value=r))
                break
    systems = list(dict.fromkeys(s for p in packs for s in _systems_of(p) if _find(s, text)))
    unit = next((p.unit for p in packs if re.search(rf"\b{re.escape(p.unit)}s?\b", text, re.I)), None)
    return Reading(word_count=len(text.split()), controls=controls, systems=systems, unit=unit)


# ---------------------------------------------------------------- matching
def _prep(s: str) -> str:
    return " ".join(w for w in utils.default_process(s).split() if w not in STOP)


def _candidates(p: Pack) -> list[str]:
    routes = " ".join(r.name for r in p.routes)
    systems = " ".join(_systems_of(p))
    return [c for c in (p.name, p.industry, p.unit, routes, systems, *p.prompts) if c]


def _score(text: str, p: Pack) -> tuple[float, int]:
    t = _prep(text)
    scores = [fuzz.token_set_ratio(t, _prep(c)) for c in _candidates(p)]
    return max(scores, default=0.0), sum(1 for s in scores if s >= BAR)


def match_pack(reading: Reading, text: str, packs: Sequence[Pack]) -> PackMatch:
    """The pack whose name, industry, unit, routes, systems and sample prompts are closest to the text (the best
    token_set_ratio of any of them); ties go to the pack with more good matches, and a model reading's unit breaks a tie
    within 5 points. Below 60 the pack is only the nearest: `nearest_only`."""
    if not packs:
        raise ValueError("no packs to match")
    scored = [(p, *_score(text, p)) for p in packs]
    best = max(s for _, s, _ in scored)
    top = [(p, s, n) for p, s, n in scored if s >= best - (TIE if reading.by_model else 0.0)]
    if reading.by_model and reading.unit:
        same = [t for t in top if t[0].unit == reading.unit]
        top = same or top
    p, s, _ = max(top, key=lambda t: (t[1], t[2]))
    return PackMatch(key=p.key, score=round(s, 1), nearest_only=s < BAR)


# ---------------------------------------------------------------- drafting
def _slug(label: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")[:40] or "option"


def _options(p: Pack) -> list[tuple[str, str, str]]:
    """(id, label, adds) of the pack's question, ids unique and never `skip`."""
    seen: set[str] = {"skip"}
    out = []
    for k, o in enumerate(p.clarify.options if p.clarify else []):
        oid = _slug(o.label)
        oid = oid if oid not in seen else f"{oid}_{k + 1}"
        seen.add(oid)
        out.append((oid, o.label, o.adds))
    return out


def _ops_of(adds: str) -> list[OverlayOp]:
    """An option's operations: its `adds` is a JSON list of operations, or plain words that add none."""
    s = adds.strip()
    if not s.startswith("["):
        return []
    try:
        return parse_ops(json.loads(s))
    except (ValueError, TypeError) as e:
        raise ChangeSetError(f"The pack's answer option has operations that are not valid: {e}") from e


def _strip(clause: str) -> str:
    return _prep(re.sub(r"[$€£]?\s?\d[\d,.]*\s?(?:%|percent|k|USD|EUR|GBP)?", " ", clause))


def _guardrail_for(clause: str, fraction: bool, p: Pack) -> PackGuardrail | None:
    """The guardrail with a numeric parameter (of the same scale) whose words are closest to the clause."""
    best: tuple[float, PackGuardrail] | None = None
    for g in p.guardrails:
        if g.param is None or (g.param.max <= 1.0) != fraction:
            continue
        s = fuzz.token_set_ratio(_strip(clause), _strip(g.text))
        if s >= 45 and (best is None or s > best[0]):
            best = (s, g)
    return best[1] if best else None


def _try(pack: Pack, op: OverlayOp) -> OverlayError | None:
    try:
        apply_overlay(pack, [op])
    except OverlayError as e:
        return e
    return None


def _cond_of(clause: str) -> list[dict[str, object]]:
    m = _DURATION.search(clause)
    if not m:
        return []
    months = int(m.group("n")) * {"day": 1 / 30, "week": 1 / 4, "month": 1, "year": 12}[m.group("u").lower()]
    return [{"fact": "age_months", "op": "gte" if m.group("cmp").lower() in _LOW else "lte", "value": round(months, 2)}]


def _check_named(what: str, p: Pack) -> tuple[str, str, str] | None:
    """The check a person asked to skip, (name, type, stage), from the pack's guardrails and active gates."""
    words = re.sub(r"\b(check|step|test|verification|stage|the)\b", " ", what, flags=re.I).strip()
    if not words:
        return None
    best: tuple[float, tuple[str, str, str]] | None = None
    named = [(g.text, g.type, g.stage) for g in p.guardrails] + [(g.name, g.type, g.stage) for g in pack_gates(p)]
    for name, typ, stage in named:
        s = fuzz.token_set_ratio(_prep(words), _prep(name))
        if s >= 85 and (best is None or s > best[0]):
            best = (s, (name, typ, stage))
    return best[1] if best else None


def _skip(clause: str, what: str, p: Pack) -> tuple[OverlayOp | None, Blocked | None]:
    named = _check_named(what, p)
    if named is None:
        return None, Blocked(text=f"Cannot skip {what.strip()}: the pack has no such check.", guardrail=what.strip())
    name, typ, stage = named
    idx = STAGE_KEYS.index(stage)
    if 0 < idx < len(STAGE_KEYS) - 1:
        op = Shortcut(id="op-0", op="shortcut", stage=STAGE_KEYS[idx - 1], to=STAGE_KEYS[idx + 1], when=_cond_of(clause))
        err = _try(p, op)
        if err is None:
            return op, None
        return None, Blocked(text=err.message, guardrail=name)
    if typ == "Compliance":
        return None, Blocked(text=f"Blocked: this skips the compliance guardrail {name}.", guardrail=name)
    return None, Blocked(text=f"Cannot skip {name}: it is at the first or last stage.", guardrail=name)


def _stated(text: str, reading: Reading, p: Pack) -> tuple[list[OverlayOp], list[Blocked]]:
    ops: list[OverlayOp] = []
    blocked: list[Blocked] = []
    roles = {c.text: str(c.value) for c in reading.controls if c.kind == "role"}
    for clause in _clauses(text):
        if m := _SKIP.search(clause):
            op, bad = _skip(clause, m.group("what"), p)
            ops += [op] if op else []
            blocked += [bad] if bad else []
            continue
        role = roles.get(clause.rstrip(".;!?"))
        for c in reading.controls:
            if c.kind not in ("amount", "percent") or not c.text or not clause.startswith(c.text):
                continue
            value = float(c.value) if not isinstance(c.value, list | str) else 0.0
            g = _guardrail_for(clause, c.kind == "percent", p)
            if g is not None and g.param is not None:
                new = value / 100 if c.kind == "percent" else value
                if new == g.param.value:
                    continue
                op = Tighten(id="op-0", op="tighten", target=g.id, field=g.param.field, value=new, seen=g.param.value)
                if err := _try(p, op):
                    why = f"weakens {'locked ' if g.locked else ''}guardrail {g.text}" if err.code == "weakens" else err.message
                    blocked.append(Blocked(text=f"{c.text}: {why}", guardrail=g.text))
                else:
                    ops.append(op)
                    if role and re.search(r"approv|sign", clause, re.I) and role not in g.approvers:
                        ops.append(AddApprover(id="op-0", op="add_approver", target=g.id, role=role))
            elif role:
                fact = (
                    _slug(clause.split(" over ")[0].split(" under ")[0].split(" above ")[0].split(" below ")[0])[:30] or "value"
                )
                cmp_ = "lte" if re.search(r"\b(under|below|less than)\b", clause, re.I) else "gte"
                ops.append(AddStep(id="op-0", op="add_step", stage="decide", when=[{"fact": fact, "op": cmp_, "value": value}],
                                   step=f"{role[:1].upper()}{role[1:]} approval", owner_role=role))  # fmt: skip
    return ops, blocked


def _finish(p: Pack, tagged: list[tuple[OverlayOp, bool]]) -> tuple[list[OverlayOp], list[str]]:
    """Number the operations op-1.. in order, list the assumed ones, and validate the whole set with `apply_overlay`."""
    ops = [o.model_copy(update={"id": f"op-{k}"}) for k, (o, _) in enumerate(tagged, 1)]
    assumed = [o.id for o, (_, a) in zip(ops, tagged, strict=True) if a]
    try:
        apply_overlay(p, ops)
    except OverlayError as e:
        raise ChangeSetError(e.message, e.op_id) from e
    return ops, assumed


def _deterministic(text: str, reading: Reading, packs: list[Pack], answer: str | None) -> ChangeSet:
    """The draft without a model: `read_text`'s controls, `match_pack`, and the pack's own question (R16)."""
    match = match_pack(reading, text, packs)
    p = next(x for x in packs if x.key == match.key)
    stated, blocked = _stated(text, reading, p)
    tagged: list[tuple[OverlayOp, bool]] = [(o, False) for o in stated]  # (operation, assumed)
    question: Question | None = None
    options = _options(p)
    if p.clarify and answer is None:
        question = Question(text=p.clarify.question, options=[Option(id=i, label=lab) for i, lab, _ in options])
    elif options and answer is not None:
        if answer == "skip":
            tagged += [(o, True) for o in _ops_of(options[0][2])]
        elif (chosen := next((o for o in options if o[0] == answer), None)) is not None:
            tagged += [(o, False) for o in _ops_of(chosen[2])]
        else:
            raise ChangeSetError(f"No answer {answer!r}: choose one of {', '.join(i for i, _, _ in options)} or skip.")
    ops, assumed = _finish(p, tagged)
    return _result(p, ops, assumed, blocked, question, answer, by_model=False)


def _result(
    p: Pack, ops: list[OverlayOp], assumed: list[str], blocked: list[Blocked], question: Question | None, answer: str | None,
    *, by_model: bool, systems: list[str] | None = None, kpis: list[str] | None = None,
) -> ChangeSet:  # fmt: skip
    registry = {s.name: s.adapter == "registry" for s in p.data.systems}
    names = systems if systems else list(registry)
    return ChangeSet(
        pack=p.key, base_version=p.version, ops=ops, assumed=assumed, blocked=blocked,
        systems=[SystemRef(name=n, adapter=registry.get(n, False)) for n in names],
        kpis=kpis or [k.label for k in p.kpis], question=question, answer=answer if question is None else None, by_model=by_model,
    )  # fmt: skip


# ---------------------------------------------------------------- the model's draft, checked
def _guardrail_name(p: Pack, gid: str | None, fallback: str) -> str:
    g = next((x for x in p.guardrails if x.id == gid), None)
    if g is not None:
        return g.text
    gate = next((x for x in pack_gates(p) if x.id == gid), None)
    return gate.name if gate is not None else fallback


def _checked(p: Pack, op: OverlayOp) -> Blocked | None:
    """None when the operation applies; a `Blocked` for a weaker value or a skipped compliance check; else the refusal
    (`ChangeSetError`, which names the operation)."""
    err = _try(p, op)
    if err is None:
        return None
    if err.code in ("weakens", "skips_compliance", "locked"):
        target = op.target if isinstance(op, Tighten | AddApprover) else err.guardrail
        name = _guardrail_name(p, err.guardrail or target, str(target or err.code))
        g = next((x for x in p.guardrails if x.id == target), None)
        why = (
            f"weakens {'locked ' if g is not None and g.locked else ''}guardrail {name}" if err.code == "weakens" else err.message
        )
        return Blocked(text=why, guardrail=name)
    raise ChangeSetError(err.message, err.op_id)


def _answer_ops(answer: str, mq: Question | None, p: Pack) -> tuple[list[OverlayOp], bool]:
    """(operations, assumed) an answer adds: the model's option, else the pack's option; `skip` adds nothing
    (the model marks what it filled in); any other words were given to the model in the prompt and add nothing here."""
    if answer == "skip":
        return [], False  # the model's own `assumed` marks what it filled in
    if mq is not None and (o := next((x for x in mq.options if x.id == answer), None)) is not None:
        return list(o.ops), False
    options = _options(p)
    chosen = next((o for o in options if o[0] == answer), None)
    return (_ops_of(chosen[2]), False) if chosen else ([], False)


def _accept(draft: ModelDraft, text: str, reading: Reading, packs: list[Pack], answer: str | None) -> ChangeSet:
    """The checks every model draft passes, in order; they win over the model: the pack must exist; a control `read_text`
    found overrides the model's value for the same field; a weaker value or a skipped compliance check is `blocked`, never an
    operation; an operation that does not apply is a `ChangeSetError` (the caller retries once); `apply_overlay` accepts the
    whole set."""
    p = next((x for x in packs if x.key == draft.pack), None)
    if p is None:
        raise ChangeSetError(f"No pack {draft.pack!r}: choose one of {', '.join(x.key for x in packs)}.")
    det_ops, blocked = _stated(text, reading, p)
    held = {(o.target, o.field) for o in det_ops if isinstance(o, Tighten)}
    by_name = {g.text: g.id for g in p.guardrails}
    refused = {by_name[b.guardrail] for b in blocked if b.guardrail in by_name}
    model_assumed = set(draft.assumed)
    tagged: list[tuple[OverlayOp, bool]] = [(o, False) for o in det_ops]
    for o in draft.ops:
        if isinstance(o, Tighten) and ((o.target, o.field) in held or o.target in refused):
            continue  # the deterministic control wins
        if (bad := _checked(p, o)) is not None:
            if bad not in blocked:
                blocked.append(bad)
            continue
        tagged.append((o, o.id in model_assumed))
    mq = draft.question
    question: Question | None = None
    if answer is None:
        if mq is not None and mq.options:
            options = []
            for opt in mq.options:
                try:
                    apply_overlay(
                        p,
                        [*(t for t, _ in tagged), *(x.model_copy(update={"id": f"op-{90 + k}"}) for k, x in enumerate(opt.ops))],
                    )
                except OverlayError:
                    continue  # an option that cannot apply is not offered
                options.append(opt)
            question = Question(text=mq.text, options=options) if options else None
        if question is None and p.clarify:
            question = Question(text=p.clarify.question, options=[Option(id=i, label=lab) for i, lab, _ in _options(p)])
    else:
        extra, assumed = _answer_ops(answer, mq, p)
        tagged += [(o, assumed) for o in extra]
    ops, assumed_ids = _finish(p, tagged)
    return _result(p, ops, assumed_ids, blocked, question, answer, by_model=True, systems=draft.systems, kpis=draft.kpis)


def draft_change_set(
    text: str,
    org: str,  # noqa: ARG001 - the org scopes the packs the caller passes; the set itself is the same for any org
    *,
    packs: Sequence[Pack],
    answer: str | None,
    reader: Callable[[str], Reading] = read_text,
    drafter: Drafter | None = None,
) -> ChangeSet:
    """The change set for a description (I-13). `answer` is an option id of the question, `"skip"` or None (the question is
    returned and only what is stated is drafted).

    With a `drafter` that returns a model's draft, the model drafts and the checks of `_accept` always win; a draft that fails is
    tried once more with the error, and then the deterministic path answers with `by_model` false. A drafter that returns None (no
    model) or no drafter: the deterministic path (`read_text`, `match_pack`, the pack's question)."""
    reading = reader(text)
    packs = list(packs)
    error: str | None = None
    for _ in range(2 if drafter is not None else 0):
        if drafter is None:  # not reached: the range is empty without one
            break
        draft = drafter(text, reading, packs, answer, error)
        if draft is None:
            break
        try:
            return _accept(draft, text, reading, packs, answer)
        except ChangeSetError as e:
            error = e.message
            log.warning("configuration agent: the model draft was refused (%s)", error)
    return _deterministic(text, reading, packs, answer)
