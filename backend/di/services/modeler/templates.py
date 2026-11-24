"""Template packs: the paths, locked guardrails, scope dimensions and actors of one kind of returns desk.

Three packs (`TEMPLATE_KEYS`):
- `industrial`: the demo's 7 routes (`fixtures/golden/world.json`) and its gate texts as guardrails, from the packaged
  `packs/industrial.json`;
- `tool_fleet` and `device`: the PO prototype's tool-fleet (`TPL.equip`) and device recommerce templates, built from
  the PO golden `fixtures/golden/po/templates.json` plus the prototype's rule checks (`ruleGuardE`, `ruleGuardD`,
  `textGuard`) and rule wording (`ruleTextE`, `ruleTextD`), which are code in the prototype and data here.
"""

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path
from typing import Any, Literal, cast

from di.core import golden
from di.services.modeler.stages import GuardType, StageKey

TEMPLATE_KEYS = ("industrial", "tool_fleet", "device")
PACKS = Path(__file__).parent / "packs"
DimKind = Literal["set", "min", "max"]


@dataclass(frozen=True)
class PathDef:
    id: str
    name: str
    app: str
    owner: str
    lead_days: int | None


@dataclass(frozen=True)
class Forbid:
    """A rule breaks the guardrail if its path is `path`, its action is in `actions`, and for each key of `scope_any`
    its scope list shares a value with it."""

    path: str
    actions: tuple[str, ...]
    scope_any: dict[str, tuple[str, ...]]


@dataclass(frozen=True)
class TextPattern:
    """Regexes that must all match the lowercased text."""

    all_of: tuple[str, ...]


@dataclass(frozen=True)
class Guardrail:
    id: str
    text: str
    owner: str
    forbids: tuple[Forbid, ...]
    protects: tuple[TextPattern, ...]
    type: GuardType
    stage: StageKey
    locked: bool  # `type == "Compliance"`: only the guardrail owner changes it


@dataclass(frozen=True)
class ScopeDim:
    """A scope dimension. `set`: the rule lists values (empty: any). `min`: the case's value is at or above the rule's.
    `max`: the case's value is below the rule's. `fields`: where the case holds the value (dotted paths, the first
    non-empty one wins; default the key itself), e.g. the tool-fleet grade is `grade`, else `estGrade`."""

    key: str
    label: str
    kind: DimKind
    values: tuple[str, ...]
    fields: tuple[str, ...] = ()

    def case_fields(self) -> tuple[str, ...]:
        return self.fields or (self.key,)


@dataclass(frozen=True)
class Phrase:
    """How one scope dimension reads in a rule's text: `fmt` around the values joined by `joiner`, each value
    replaced by its word in `words` when there is one."""

    key: str
    fmt: str
    joiner: str
    words: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class Wording:
    """A rule's text: the phrases of its scope in this order (or `every`), then never/only/prefer and the path's name
    as `path_names` gives it."""

    every: str
    phrases: tuple[Phrase, ...]
    path_names: dict[str, str]


@dataclass(frozen=True)
class Template:
    key: str
    name: str
    pre: str
    paths: tuple[PathDef, ...]
    guardrails: tuple[Guardrail, ...]
    dims: tuple[ScopeDim, ...]
    actors: tuple[tuple[str, str, str], ...]
    wording: Wording

    def path(self, k: str) -> PathDef | None:
        return next((p for p in self.paths if p.id == k), None)

    def path_ids(self) -> tuple[str, ...]:
        return tuple(p.id for p in self.paths)


# ----------------------------------------------------------------------------- the prototype's code as data
APPROVAL = TextPattern(("auto-?approv|without approval|skip approval",))
TOOL_FLEET_GUARDS: dict[str, tuple[tuple[Forbid, ...], tuple[TextPattern, ...]]] = {
    "GR-01": ((Forbid("release", ("require", "prefer"), {"grade": ("C", "D")}),), ()),
    "GR-02": ((), (TextPattern(("refurb", "to stock")),)),
    "GR-03": ((), (TextPattern(("fit-for-use|threshold", "lower|reduce|change|set|relax|raise")),)),
    "GR-04": ((), (TextPattern(("holding cost",)),)),
    "GR-05": ((), (APPROVAL,)),
}
DEVICE_GUARDS: dict[str, tuple[tuple[Forbid, ...], tuple[TextPattern, ...]]] = {
    "GR-D1": ((), (TextPattern(("wipe|certificate", r"skip|without|\bno\b")),)),
    "GR-D2": ((), (TextPattern(("floor", "lower|reduce|change|set|remove")),)),
    "GR-D3": (
        tuple(Forbid(k, ("require", "prefer"), {"grade": ("D",)}) for k in ("buynow", "market")),
        (),
    ),
    "GR-D4": ((), (TextPattern(("lot size|lot limit", "raise|increase|remove|change")),)),
    "GR-D5": ((), (TextPattern(("undercut",)),)),
    "GR-D6": ((), (APPROVAL,)),
}
# (type, stage) of the tool-fleet and device guardrails (P9-0.11); P9-1.1 moves these into the pack files
GUARD_META: dict[str, tuple[GuardType, StageKey]] = {
    "GR-01": ("Compliance", "decide"), "GR-02": ("Compliance", "decide"), "GR-03": ("Threshold", "condition"),
    "GR-04": ("Threshold", "value"), "GR-05": ("Approval", "decide"), "GR-06": ("Compliance", "execute"),
    "GR-D1": ("Compliance", "condition"), "GR-D2": ("Threshold", "value"), "GR-D3": ("Compliance", "decide"),
    "GR-D4": ("Threshold", "decide"), "GR-D5": ("Threshold", "value"), "GR-D6": ("Approval", "decide"),
}  # fmt: skip
DIM_KIND: dict[str, DimKind] = {"rulMax": "max", "rulMin": "min", "dohMin": "min", "qtyMin": "min"}
DIM_FIELDS = {"grade": ("grade", "estGrade"), "rulMax": ("rul",), "rulMin": ("rul",), "dohMin": ("doh",),
              "qtyMin": ("qty",)}  # fmt: skip
DEVICE_FIELDS = {"dohMin": ("doh",), "qtyMin": ("qty",)}


def _tool_fleet_wording(paths: Sequence[PathDef], clswords: dict[str, str]) -> Wording:
    phrases = (
        Phrase("ft", "{} returns", " or "),
        Phrase("cls", "{}", " or ", clswords),
        Phrase("grade", "grade {}", "/"),
        Phrase("site", "at {}", " or "),
        Phrase("rulMax", "under {}% life", ""),
        Phrase("rulMin", "{}%+ life", ""),
    )
    return Wording("every return", phrases, {p.id: p.name.replace(" → place", "").lower() for p in paths})


def _device_wording(paths: Sequence[PathDef]) -> Wording:
    phrases = (
        Phrase("brand", "{}", " or "),
        Phrase("grade", "grade {}", "/"),
        Phrase("band", "{} age", " or "),
        Phrase("dohMin", "{}+ days on hand", ""),
        Phrase("qtyMin", "lots of {}+ units", ""),
    )
    return Wording("every lot", phrases, {p.id: p.name for p in paths})


# ----------------------------------------------------------------------------- loading
def _po(key: str) -> dict[str, Any]:
    return cast(dict[str, Any], next(t for t in golden.load("po/templates")["templates"] if t["key"] == key))


def _guards(rows: Sequence[Mapping[str, str]], checks: Mapping[str, tuple[tuple[Forbid, ...], tuple[TextPattern, ...]]]
            ) -> tuple[Guardrail, ...]:  # fmt: skip
    out = []
    for g in rows:
        forbids, protects = checks.get(g["id"], ((), ()))
        gtype, stage = GUARD_META[g["id"]]
        out.append(Guardrail(g["id"], g["text"], g["owner"], forbids, protects, gtype, stage, gtype == "Compliance"))
    return tuple(out)


def _po_dims(rows: Sequence[Mapping[str, Any]], fields: Mapping[str, tuple[str, ...]]) -> tuple[ScopeDim, ...]:
    return tuple(
        ScopeDim(d["key"], d["label"], DIM_KIND.get(d["key"], "set"), tuple(d["values"] or ()), fields.get(d["key"], ()))
        for d in rows
    )


def _tool_fleet() -> Template:
    g, root = _po("equip"), golden.load("po/templates")
    paths = tuple(PathDef(p["key"], p["name"], p["app"], p["owner"], p["lead"]) for p in g["paths"])
    actors = tuple((a["id"], a["name"], a["role"]) for a in root["ACTORS"])
    return Template("tool_fleet", g["name"], g["pre"], paths, _guards(g["guards"], TOOL_FLEET_GUARDS),
                    _po_dims(g["dims"], DIM_FIELDS), actors, _tool_fleet_wording(paths, dict(root["CLSWORDS"])))  # fmt: skip


def _device() -> Template:
    """The device pack: the prototype has no `TPL.device` and gives it no name; the golden's rebuilt entry, named
    "Device recommerce" (decision log, 2026-11-23). A channel's app and owner come from its path node in `tplDevice`."""
    g = _po("device")
    nodes = {n.get("path"): n for n in golden.load("po/flows")["device"]["n"] if n["t"] == "path"}
    paths = tuple(PathDef(p["key"], p["name"], nodes[p["key"]]["sub"], nodes[p["key"]]["owner"], None) for p in g["paths"])
    actors = tuple((a["id"], a["name"], a["role"]) for a in golden.load("po/templates")["ACTORS"])
    return Template("device", "Device recommerce", g["pre"], paths, _guards(g["guards"], DEVICE_GUARDS),
                    _po_dims(g["dims"], DEVICE_FIELDS), actors, _device_wording(paths))  # fmt: skip


def _industrial() -> Template:
    d = json.loads((PACKS / "industrial.json").read_text(encoding="utf-8"))
    paths = tuple(PathDef(p["id"], p["name"], p["app"], p["owner"], p["lead_days"]) for p in d["paths"])
    guards = tuple(
        Guardrail(
            g["id"],
            g["text"],
            g["owner"],
            (),
            tuple(TextPattern(tuple(p)) for p in g["protects"]),
            g["type"],
            g["stage"],
            g["type"] == "Compliance",
        )
        for g in d["guardrails"]
    )
    dims = tuple(ScopeDim(x["key"], x["label"], x["kind"], tuple(x["values"]), tuple(x["fields"])) for x in d["dims"])
    w = d["wording"]
    phrases = tuple(Phrase(p["key"], p["fmt"], p["joiner"], dict(p["words"])) for p in w["phrases"])
    wording = Wording(w["every"], phrases, {p.id: p.name.lower() for p in paths})
    actors = tuple((a[0], a[1], a[2]) for a in d["actors"])
    return Template(d["key"], d["name"], d["pre"], paths, guards, dims, actors, wording)


BUILDERS = {"industrial": _industrial, "tool_fleet": _tool_fleet, "device": _device}


@cache
def load_template(key: str) -> Template:
    """The template pack `key`; a KeyError for an unknown key. Cached: treat as read-only."""
    return BUILDERS[key]()
