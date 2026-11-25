"""Template packs: the paths, locked guardrails, scope dimensions and actors of one kind of returns desk.

Three packs (`TEMPLATE_KEYS`), each a pack file (`packs/<key>.json`, format v1 in `di.services.modeler.pack`, plan 9
P9-1.1) turned into a `Template` by `template_of_pack`:
- `industrial`: the demo's 7 routes (`fixtures/golden/world.json`) and its gate texts as guardrails;
- `tool_fleet` and `device`: the PO prototype's tool-fleet (`TPL.equip`) and device recommerce templates (the golden
  `fixtures/golden/po/templates.json`, the prototype's rule checks `ruleGuardE`, `ruleGuardD`, `textGuard` and its rule
  wording `ruleTextE`, `ruleTextD`), which are code in the prototype and data in the pack files.
"""

from dataclasses import dataclass, field
from functools import cache

from di.services.modeler.pack import DimKind, Pack, load_pack
from di.services.modeler.stages import GuardType, StageKey

TEMPLATE_KEYS = ("industrial", "tool_fleet", "device")


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


# ----------------------------------------------------------------------------- loading
def template_of_pack(p: Pack) -> Template:
    """The authoring template of a pack: its routes as paths, guardrails with their checks, dims, actors, wording."""
    paths = tuple(PathDef(r.id, r.name, r.app, r.owner, r.lead_days) for r in p.routes)
    guards = tuple(
        Guardrail(
            g.id,
            g.text,
            g.owner,
            tuple(Forbid(f.path, tuple(f.actions), {k: tuple(v) for k, v in f.scope_any.items()}) for f in g.forbids),
            tuple(TextPattern(tuple(pattern)) for pattern in g.protects),
            g.type,
            g.stage,
            g.locked,
        )
        for g in p.guardrails
    )
    dims = tuple(ScopeDim(d.key, d.label, d.kind, tuple(d.values), tuple(d.fields)) for d in p.dims)
    w = p.wording
    phrases = tuple(Phrase(x.key, x.fmt, x.joiner, dict(x.words)) for x in w.phrases)
    return Template(p.key, p.name, p.prefix, paths, guards, dims, tuple(p.actors), Wording(w.every, phrases, dict(w.path_names)))


@cache
def load_template(key: str) -> Template:
    """The template of pack `key`; a KeyError for an unknown key. Cached: treat as read-only."""
    return template_of_pack(load_pack(key))
