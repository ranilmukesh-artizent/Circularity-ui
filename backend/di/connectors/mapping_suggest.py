"""Field mapping suggestions with calibrated confidence (plan 9, P9-8.2; registry entry I-19).

    profile(sample, field)                    -> FieldProfile   one source field, masked (the masker runs here, before
                                                                anything is stored or sent to a model)
    suggest(profiles, sample, canonical, memory=None, rerank=None) -> [MappingProposal]
    check_answer(profile, candidates, answer) -> error text | None   the checks a model's `RerankAnswer` must pass
    canonical_fields(models=None)             -> [CanonicalField]    from di.services.canonical.schema.MODEL_FIELDS

How a proposal is made (R16, model first, code holds the line):
  1. Candidates, no model: RapidFuzz `token_set_ratio` and Jaro-Winkler on the names after splitting vendor codes and
     expanding `mapping_synonyms.json`, the value profile's agreement with the canonical field's type, a code set that
     fits the field's name, and a memory hit. A fixed weighted sum is the raw score in [0, 1]; the top 5 are kept.
  2. The model (`rerank`, built by di.services.agents.mapping_rerank) reads the masked profile and the candidates, chooses
     one of them or abstains and writes `why`. An answer that fails `check_answer` is dropped: the deterministic target
     stays. `rerank=None` (no key) skips the step.
  3. Confidence is `isotonic.lookup` of the raw score on the curve of `mapping_calibration.json`, adjusted by agreement
     (the model chose the top candidate), disagreement (it chose another) and a memory hit. Never the model's own number.
  4. The reason is the model's `why`, else one phrase per signal filled from evidence.
  5. The band: `pre_ticked` at or above the threshold that gave at least 95 % precision on the held-out gold set, `check`
     down to the lower bound, `none` below (target None, the candidates shown). Nothing is auto-accepted; this module
     writes nothing.

Never does: call a model itself, read a database, or save a mapping (mapping.apply does, a person's choice, P9-8.4).
The `memory` argument comes from `di.repositories.mapping_decisions.memory_for` (what people chose for the vendor family).
"""

import json
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from functools import cache
from pathlib import Path
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict
from rapidfuzz import fuzz
from rapidfuzz.distance import JaroWinkler

from di.connectors import isotonic, mapping
from di.services.canonical.schema import MODEL_FIELDS

MASK = "«masked»"
TOP = 5  # candidates kept per field
AMBIGUITY, TIE_MARGIN = 0.15, 0.05  # a tie with the runner-up costs 0.15 of score; a margin of 0.05 costs none
W_NAME, W_VALUE, W_MEMORY = 0.6, 0.25, 0.15  # the raw score's weights (sum 1)
_HERE = Path(__file__).parent
Band = Literal["pre_ticked", "check", "none"]

_ISO4217 = frozenset(
    "AED AFN ALL AMD ANG AOA ARS AUD AWG AZN BAM BBD BDT BGN BHD BIF BMD BND BOB BRL BSD BTN BWP BYN BZD CAD CDF CHF CLP CNY "
    "COP CRC CUP CVE CZK DJF DKK DOP DZD EGP ERN ETB EUR FJD FKP GBP GEL GHS GIP GMD GNF GTQ GYD HKD HNL HTG HUF IDR ILS INR "
    "IQD IRR ISK JMD JOD JPY KES KGS KHR KMF KPW KRW KWD KYD KZT LAK LBP LKR LRD LSL LYD MAD MDL MGA MKD MMK MNT MOP MRU MUR "
    "MVR MWK MXN MYR MZN NAD NGN NIO NOK NPR NZD OMR PAB PEN PGK PHP PKR PLN PYG QAR RON RSD RUB RWF SAR SBD SCR SDG SEK SGD "
    "SHP SLE SOS SRD SSP STN SVC SYP SZL THB TJS TMT TND TOP TRY TTD TWD TZS UAH UGX USD UYU UZS VES VND VUV WST XAF XCD XOF "
    "XPF YER ZAR ZMW ZWL".split()
)
_ISO3166 = frozenset(
    "AD AE AF AG AI AL AM AO AQ AR AS AT AU AW AX AZ BA BB BD BE BF BG BH BI BJ BL BM BN BO BQ BR BS BT BV BW BY BZ CA CC CD "
    "CF CG CH CI CK CL CM CN CO CR CU CV CW CX CY CZ DE DJ DK DM DO DZ EC EE EG EH ER ES ET FI FJ FK FM FO FR GA GB GD GE GF "
    "GG GH GI GL GM GN GP GQ GR GS GT GU GW GY HK HM HN HR HT HU ID IE IL IM IN IO IQ IR IS IT JE JM JO JP KE KG KH KI KM KN "
    "KP KR KW KY KZ LA LB LC LI LK LR LS LT LU LV LY MA MC MD ME MF MG MH MK ML MM MN MO MP MQ MR MS MT MU MV MW MX MY MZ NA "
    "NC NE NF NG NI NL NO NP NR NU NZ OM PA PE PF PG PH PK PL PM PN PR PS PT PW PY QA RE RO RS RU RW SA SB SC SD SE SG SH SI "
    "SJ SK SL SM SN SO SR SS ST SV SX SY SZ TC TD TF TG TH TJ TK TL TM TN TO TR TT TV TW TZ UA UG UM US UY UZ VA VC VE VG VI "
    "VN VU WF WS YE YT ZA ZM ZW".split()
)
_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}.*)?")
# code set -> (members or a pattern, the phrase a reason uses, the words of a canonical field name it fits)
_CODE_SETS: dict[str, tuple[frozenset[str], str, frozenset[str]]] = {
    "grade_A-D": (frozenset("ABCD"), "values are grades A to D", frozenset({"grade", "condition"})),
    "iso4217": (_ISO4217, "values look like ISO 4217 codes", frozenset({"currency"})),
    "iso3166": (_ISO3166, "values look like ISO 3166 country codes", frozenset({"country"})),
    "flag_01": (
        frozenset({"0", "1"}),
        "coded 0/1; meaning taken from the registry documentation",
        frozenset({"flag", "is", "has"}),
    ),
    "flag_YN": (
        frozenset({"Y", "N"}),
        "coded Y/N; meaning taken from the registry documentation",
        frozenset({"flag", "is", "has"}),
    ),
}
_ID_WORDS = frozenset({"id", "serial", "number", "reference", "key", "code"})
_ISO_DATE_PHRASE = "values look like ISO dates"
_EMAIL = re.compile(r"[^@\s]+@[^@\s]+\.[A-Za-z]{2,}")
_PERSON = re.compile(r"[A-Z][a-z]{1,}(?: [A-Z][a-z'-]{1,}){1,2}")
_PHONE = re.compile(r"\+?[\d\s().-]{7,}")
_NUMBER = re.compile(r"-?\d+(?:[.,]\d+)*")


class FieldProfile(BaseModel):
    """What one source field looks like, masked (the spec's FieldProfile)."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    name: str
    type: str  # text, number, bool, date, object, list, unknown (no value in the sample)
    null_rate: float
    distinct_ratio: float
    top_values: list[str]  # at most 5, masked
    pattern: str | None
    min: float | str | None
    max: float | str | None
    code_sets: list[str]


class RerankAnswer(BaseModel):
    """The model's typed answer for one field: one of the candidates or None, the transform rule and a reason."""

    model_config = ConfigDict(extra="forbid")
    target: str | None
    rule: str
    why: str


class Reranker(Protocol):
    def __call__(self, field: FieldProfile, candidates: list[tuple[str, float]], /) -> RerankAnswer | None: ...


@dataclass(frozen=True)
class CanonicalField:
    model: str
    field: str
    type: str
    required: bool

    @property
    def target(self) -> str:
        return f"{self.model}.{self.field}"


@dataclass(frozen=True)
class MappingProposal:
    field: str
    target: str | None
    confidence: float
    reason: str
    rule: str
    proposed_by: Literal["rule", "memory", "model"]
    candidates: list[tuple[str, float]]
    band: Band

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Calibration:
    points: list[tuple[float, float]]
    pre_ticked: float
    check: float
    agree_bonus: float
    disagree_factor: float
    memory_bonus: float


@cache
def calibration() -> Calibration:
    d = json.loads((_HERE / "mapping_calibration.json").read_text(encoding="utf-8"))
    return Calibration(
        [(float(x), float(y)) for x, y in d["points"]], float(d["pre_ticked"]), float(d["check"]), float(d["agree_bonus"]),
        float(d["disagree_factor"]), float(d["memory_bonus"]),
    )  # fmt: skip


@cache
def _synonyms() -> dict[str, str]:
    return dict(json.loads((_HERE / "mapping_synonyms.json").read_text(encoding="utf-8"))["tokens"])


# ---------------------------------------------------------------- the masker and the profile
def mask(value: Any) -> str:
    """The value as text, or `«masked»` for an email, a phone number, a person's name or free text over 40 characters."""
    s = str(value).strip()
    if _EMAIL.search(s) or len(s) > 40:
        return MASK
    if _PHONE.fullmatch(s) and sum(c.isdigit() for c in s) >= 7 and not _ISO_DATE.fullmatch(s) and re.search(r"[+()\s]", s):
        return MASK
    if _PERSON.fullmatch(s):
        return MASK
    return s


def _kind(v: Any) -> str:
    if isinstance(v, bool):
        return "bool"
    if isinstance(v, int | float):
        return "number"
    if isinstance(v, dict):
        return "object"
    if isinstance(v, list):
        return "list"
    s = str(v).strip()
    if _ISO_DATE.fullmatch(s):
        return "date"
    return "number" if _NUMBER.fullmatch(s) and "," not in s else "text"


def _shape(s: str) -> str:
    return re.sub(r"[a-z]", "a", re.sub(r"[A-Z]", "A", re.sub(r"\d", "9", s)))


def _code_sets(values: list[str]) -> list[str]:
    out = [name for name, (members, _, _) in _CODE_SETS.items() if values and all(v in members for v in values)]
    if values and all(_ISO_DATE.fullmatch(v) for v in values):
        out.append("iso_date")
    return out


def profile(sample: Sequence[Mapping[str, Any]], field: str) -> FieldProfile:
    """The masked profile of `field` over the sample records (a dotted name reaches into a nested record)."""
    found = [mapping.lookup(r, field) for r in sample]
    values = [v for v in found if v is not mapping._MISSING and v is not None and v != ""]
    kinds = Counter(_kind(v) for v in values)
    kind = "unknown" if not kinds else ("text" if len(kinds) > 1 else next(iter(kinds)))
    shown = [str(v) if not isinstance(v, dict | list) else json.dumps(v, default=str) for v in values]
    counts = Counter(shown)
    top = [mask(v) for v, _ in counts.most_common(TOP)]
    lo: float | str | None = None
    hi: float | str | None = None
    if kind == "number":
        nums = [float(mapping._number(v)) for v in values]
        lo, hi = min(nums), max(nums)
    elif kind == "date":
        lo, hi = min(s[:10] for s in shown), max(s[:10] for s in shown)
    common = counts.most_common(1)
    return FieldProfile(
        name=field,
        type=kind,
        null_rate=round(1 - len(values) / len(sample), 4) if sample else 1.0,
        distinct_ratio=round(len(counts) / len(values), 4) if values else 0.0,
        top_values=top,
        pattern=_shape(common[0][0]) if common and mask(common[0][0]) != MASK and len(common[0][0]) <= 40 else None,
        min=lo,
        max=hi,
        code_sets=_code_sets(sorted(counts)),
    )


def field_paths(sample: Sequence[Mapping[str, Any]], depth: int = 3, cap: int = 200) -> list[str]:
    """The field names a sample's records have, nested keys dotted (RECEIVING_INSPECTION.GRADE), first seen first."""
    out: dict[str, None] = {}

    def walk(rec: Mapping[str, Any], prefix: str, d: int) -> None:
        for k, v in rec.items():
            path = f"{prefix}{k}"
            if isinstance(v, dict) and d > 1:
                walk(v, path + ".", d - 1)
            elif not isinstance(v, dict | list):
                out.setdefault(path)

    for r in sample:
        walk(r, "", depth)
    return list(out)[:cap]


def canonical_fields(models: Sequence[str] | None = None) -> list[CanonicalField]:
    """The canonical fields to propose, from the canonical schema (`models` narrows them, e.g. to a pack's entities)."""
    return [
        CanonicalField(m, f, spec.type, spec.required)
        for m, fields in MODEL_FIELDS.items()
        if models is None or m in models
        for f, spec in sorted(fields.items())
    ]


# ---------------------------------------------------------------- a pack's hint limits the choices (P9-10.8, TN-03)
ASK_OWNER, CONFIRMED_FIELD = "ask_system_owner", "confirmed_source_field"


@cache
def _pack_hints() -> tuple[dict[str, Any], ...]:
    """The `hint` mappings of the shipped packs (a pack's `data.mappings` rows of kind `hint`): source, field, canonical, ..."""
    from di.services.modeler.pack import load_pack, pack_keys

    return tuple(m for k in pack_keys() for m in load_pack(k).data.mappings if m.get("kind") == "hint")


def hint_of(source_id: str, field: str) -> dict[str, Any] | None:
    """The pack hint for a source field of the source (a second source of the same system, `tn_inv_2`, shares its hints)."""
    base = re.sub(r"_\d+$", "", source_id)
    return next((h for h in _pack_hints() if h.get("source") in (source_id, base) and h.get("field") == field), None)


def allowed_choices(source_id: str, field: str) -> list[str] | None:
    """The only choices a pack's hint offers for the field (`allowed_choices`: "ask_system_owner", "confirmed_source_field"),
    or None when the hint restricts none or there is no hint. The export class inferred from a part number is the case."""
    h = hint_of(source_id, field)
    return list(h["allowed_choices"]) if h and h.get("allowed_choices") else None


def refused_choice(source_id: str, field: str, decision: str, target: str | None) -> str | None:
    """Why a person's choice for the field is refused, or None. Where a hint restricts the choices, the one choice that
    records is "choose another field" (`replaced`: the source's confirmed field, kept apart from the hint's own target);
    accepting the hint, converting it or marking it not needed is refused, and so is moving it into the hint's target by
    another name. Asking the system owner is `mapping.askOwner`, which this never refuses."""
    choices = allowed_choices(source_id, field)
    if choices is None:
        return None
    h = hint_of(source_id, field)
    assert h is not None  # noqa: S101 - allowed_choices found it
    if decision == "replaced" and CONFIRMED_FIELD in choices and target and target != h.get("canonical"):
        return None
    return (
        f"{field} is inferred, never accepted as {h.get('canonical')}: ask the system owner, or choose the source's "
        f"confirmed field."
    )


# ---------------------------------------------------------------- candidates
def _words(name: str) -> list[str]:
    parts = [p for p in re.split(r"[^a-z0-9]+", re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", name).lower()) if p]
    syn = _synonyms()
    out = [w for p in parts for w in syn.get(p, p).split()]
    return out or parts


def _name_score(query: str, field_name: str) -> float:
    """0..1: fuzzy token overlap, Jaro-Winkler on the joined words and the Jaccard overlap of the word sets (1.0 only
    when the two have the same words)."""
    wa, wb = _words(query), _words(field_name)
    a, b = " ".join(wa), " ".join(wb)
    union = set(wa) | set(wb)
    jaccard = len(set(wa) & set(wb)) / len(union) if union else 0.0
    return 0.35 * fuzz.token_set_ratio(a, b) / 100 + 0.25 * JaroWinkler.normalized_similarity(a, b) + 0.4 * jaccard


_TYPE_FIT = {
    ("text", "number"): 0.4,
    ("text", "date"): 0.3,
    ("text", "bool"): 0.2,
    ("number", "text"): 0.2,
    ("ref", "number"): 0.5,
    ("bool", "number"): 0.4,
}  # fmt: skip  (canonical type, source type) -> fit


def _type_score(source: str, canon: str) -> float:
    if source == "unknown" or canon == "any":
        return 0.5
    if source == canon:
        return 1.0
    return 0.8 if (canon, source) == ("ref", "text") else _TYPE_FIT.get((canon, source), 0.0)


def _value_score(p: FieldProfile, c: CanonicalField) -> float:
    hints = [_CODE_SETS[s][2] for s in p.code_sets if s in _CODE_SETS]
    if "iso_date" in p.code_sets:
        hints.append(frozenset({"date", "at", "time", "timestamp"}))
    words = set(_words(c.field))
    id_shaped = p.type in ("text", "number") and p.pattern is not None and re.search(r"\d", p.pattern) is not None
    if len(p.top_values) >= 2 and p.distinct_ratio >= 0.9 and id_shaped:
        hints.append(_ID_WORDS)  # identifier-shaped values: all different, with digits
    hint = 0.5 if not hints else (1.0 if any(words & h for h in hints) else 0.3)
    return 0.6 * _type_score(p.type, c.type) + 0.4 * hint


@dataclass(frozen=True)
class _Scored:
    canon: CanonicalField
    raw: float
    name: float
    memory: bool


def raw_candidates(
    p: FieldProfile, canonical: Sequence[CanonicalField], memory: Mapping[str, str] | None = None
) -> list[_Scored]:
    """The top candidates for one field with no model: the weighted sum of the name, value and memory signals."""
    scored = []
    for c in canonical:
        name = max(_name_score(p.name, c.field), 0.9 * _name_score(p.name, f"{c.model} {c.field}"))
        mem = memory is not None and memory.get(p.name) == c.target
        raw = W_NAME * name + W_VALUE * _value_score(p, c) + W_MEMORY * mem
        scored.append(_Scored(c, round(min(raw, 1.0), 4), name, mem))
    return sorted(scored, key=lambda s: (-s.raw, s.canon.target))[:TOP]


def top_score(cands: Sequence[_Scored]) -> float:
    """The score the calibration curve reads: the top candidate's raw score, lowered when the runner-up is nearly as
    good (the same field name in two models), because such a pick is a coin toss that the name alone cannot settle."""
    if len(cands) < 2:
        return cands[0].raw if cands else 0.0
    margin = cands[0].raw - cands[1].raw
    return round(cands[0].raw - AMBIGUITY * (1 - min(1.0, margin / TIE_MARGIN)), 4)


def own_score(cands: Sequence[_Scored], chosen: _Scored) -> float:
    return chosen.raw if chosen is not cands[0] else top_score(cands)


# ---------------------------------------------------------------- the model's answer and the checks
def _numbers(text: str) -> set[str]:
    return {f"{float(n.replace(',', '')):g}" for n in _NUMBER.findall(text)}


def check_answer(p: FieldProfile, candidates: Sequence[tuple[str, float]], a: RerankAnswer) -> str | None:
    """Why the model's answer is refused, or None. The target must be a candidate (or None), the rule a rule the mapping
    engine knows, the reason non-empty, and every number in it must appear in the profile or the candidates' scores."""
    if a.target is not None and a.target not in {t for t, _ in candidates}:
        return f"The target {a.target!r} is not one of the candidates: choose one of them or answer null."
    if mapping.parse_rule(a.rule) is None:
        return f"{a.rule!r} is not a mapping rule (copy, upper, lower, number, int, date, utc, fx:XXX, units:a>b, code:grade)."
    if not a.why.strip():
        return "Write a reason."
    known = _numbers(p.model_dump_json()) | {f"{s:g}" for _, s in candidates} | {f"{round(s, 2):g}" for _, s in candidates}
    if stray := _numbers(a.why) - known:
        return f"The reason has numbers that are not in the profile: {sorted(stray)}."
    return None


# ---------------------------------------------------------------- proposals
def _rule_for(p: FieldProfile, c: CanonicalField) -> str:
    if "grade_A-D" in p.code_sets and "grade" in _words(c.field):
        return "code:grade"
    if c.type == "bool" and {"flag_01", "flag_YN"} & set(p.code_sets):
        return "code:bool"
    return c.type if c.type in ("date", "number") and p.type == c.type else "copy"


def _reason(p: FieldProfile, s: _Scored) -> str:
    parts = []
    if s.memory:
        parts.append("accepted for this vendor family before")
    if s.name >= 0.6:
        parts.append(f"name match {s.name:.2f} with {s.canon.field}")
    parts += [_CODE_SETS[c][1] for c in p.code_sets if c in _CODE_SETS][:2]
    if "iso_date" in p.code_sets:
        parts.append(_ISO_DATE_PHRASE)
    return "; ".join(parts) or "weak evidence: the best candidate by name and values"


def _band(conf: float, cal: Calibration) -> Band:
    return "pre_ticked" if conf >= cal.pre_ticked else "check" if conf >= cal.check else "none"


def _propose(p: FieldProfile, cands: list[_Scored], rerank: Reranker | None, cal: Calibration) -> MappingProposal:
    shown = [(s.canon.target, s.raw) for s in cands]
    if not cands:
        return MappingProposal(p.name, None, 0.0, "no canonical field to propose", "copy", "rule", [], "none")
    top = cands[0]
    conf = isotonic.lookup(cal.points, top_score(cands))
    chosen, reason, rule = top, _reason(p, top), _rule_for(p, top.canon)
    by: Literal["rule", "memory", "model"] = "memory" if top.memory else "rule"
    conf = min(1.0, conf + cal.memory_bonus) if top.memory else conf
    ans = rerank(p, shown) if rerank is not None else None
    if ans is not None and check_answer(p, shown, ans) is None:
        reason = ans.why.strip()
        if ans.target == top.canon.target:
            conf, by, rule = min(1.0, conf + cal.agree_bonus), "model", ans.rule
        elif ans.target is not None:  # another candidate: its own calibrated score, never above the top's, then lowered
            chosen = next(s for s in cands if s.canon.target == ans.target)
            own = isotonic.lookup(cal.points, own_score(cands, chosen)) + (cal.memory_bonus if chosen.memory else 0.0)
            conf, by, rule = min(1.0, own, conf) * cal.disagree_factor, "model", ans.rule
    conf = round(conf, 4)
    band = _band(conf, cal)
    return MappingProposal(p.name, chosen.canon.target if band != "none" else None, conf, reason, rule, by, shown, band)


def suggest(
    source_fields: Sequence[FieldProfile],
    sample: Sequence[Mapping[str, Any]],  # noqa: ARG001 - the records the profiles were made from (I-19's signature)
    canonical: Sequence[CanonicalField],
    *,
    memory: Mapping[str, str] | None = None,
    rerank: Reranker | None = None,
) -> list[MappingProposal]:
    """One proposal per source field (I-19). The proposals are drafts: nothing here accepts or saves one."""
    cal = calibration()
    return [_propose(p, raw_candidates(p, canonical, memory), rerank, cal) for p in source_fields]
