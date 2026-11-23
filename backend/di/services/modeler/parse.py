"""A plain-language rule read into {path, action, scope} (plan 8, MVP-5.1; Domain spec D10; the prototype's parseEquip
and parseDevice, lines 2415-2433).

- `tool_fleet` and `device` port the prototype exactly (their regexes are the prototype's code, as data here).
- `industrial` reads the same structure over the demo's vocabulary: asset classes by label, plural or key (keys of
  three letters or more, so "it" the word is not IT electronics), sites by id or name, grades, the owner org units by
  exact name, and the route names plus `recycl|scrap|material` (material recovery), `exit`, `lease` (re-lease) and
  `parts` (internal recovered-part use, or the external parts sale when "sell" or "external" occurs).
- The action: `never|no|not|don't|do not|exclude|stop|avoid|block` excludes, `only|must|always|allow` requires,
  anything else prefers. The path is the one named first in the text; none gives `path: None`.
"""

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from di.core import golden
from di.services.modeler.templates import Template

EXCLUDE = re.compile(r"never|\bno\b|\bnot\b|don't|do not|exclude|stop|avoid|block")
REQUIRE = re.compile(r"\bonly\b|\bmust\b|always|allow")
GRADES = re.compile(r"grades?\s+([abcd](?:\s*(?:,|or|and|/)\s*[abcd])*)\b")


@dataclass(frozen=True)
class ParsedRule:
    path: str | None
    action: str
    scope: dict[str, Any] = field(default_factory=dict)


def _action(s: str) -> str:
    return "exclude" if EXCLUDE.search(s) else "require" if REQUIRE.search(s) else "prefer"


def _grades(s: str, scope: dict[str, Any]) -> None:
    m = GRADES.search(s)
    if m:
        scope["grade"] = re.findall(r"[ABCD]", m.group(1).upper())


def _first_path(s: str, table: Sequence[tuple[str, str]]) -> str | None:
    """The path whose pattern matches earliest in `s` (the prototype's hits sorted by index; ties keep table order)."""
    hits = [(m.start(), i, k) for i, (k, rx) in enumerate(table) if (m := re.search(rx, s))]
    return min(hits)[2] if hits else None


# ---------------------------------------------------------------- tool fleet (parseEquip, 2424-2433)
EQUIP_CLS = (("CMH", "combihammer"), ("BRK", "breaker"), ("DCD", "core drill"), ("CRH", "rotary hammer|cordless"),
             ("AGR", "grinder"), ("LSR", "laser"))  # fmt: skip
EQUIP_PATHS = (("refurb", "refurb"), ("redeploy", r"tool pool|loaner|\bpool\b"), ("harvest", "harvest|parts"),
               ("exit", r"\bexit\b|recycl|scrap"), ("resell", r"resell|resale|pre-owned|\bsell\b|outlet|\bbid\b"),
               ("release", r"re-?issu|fleet contract|\bissue\b"))  # fmt: skip


def _tool_fleet(s: str) -> ParsedRule:
    root = golden.load("po/templates")
    funcs: list[str] = root["FUNCS"]
    scope: dict[str, Any] = {}
    cls = [k for k, rx in EQUIP_CLS if re.search(rx, s)]  # CLSWORDS order (1011)
    if cls:
        scope["cls"] = cls
    _grades(s, scope)
    ft = [f for f in funcs if (re.search("fleet management|contract end", s) if f == "Fleet management" else f.lower() in s)]
    if ft:
        scope["ft"] = ft
    site = [x for x in root["SITES"] if x.lower() in s]
    if site:
        scope["site"] = site
    if m := re.search(r"(under|below|less than)\s*(\d+)\s*%", s):
        scope["rulMax"] = int(m.group(2))
    if m := re.search(r"(over|above|at least)\s*(\d+)\s*%", s):
        scope["rulMin"] = int(m.group(2))
    rest = s
    for f in funcs:
        rest = " ".join(rest.split(f.lower()))
    return ParsedRule(_first_path(rest, EQUIP_PATHS), _action(s), scope)


# ---------------------------------------------------------------- device (parseDevice, 2415-2423)
DEVICE_BRANDS = (("Apple", "apple|iphone"), ("Samsung", "samsung|galaxy"), ("Google", "google|pixel"),
                 ("Motorola", r"motorola|moto\b"))  # fmt: skip
DEVICE_PATHS = (("buynow", "buy ?now"), ("offers", r"\boffers?\b"), ("auction", "auction"), ("market", "marketplace"))


def _device(s: str) -> ParsedRule:
    scope: dict[str, Any] = {}
    brands = [b for b, rx in DEVICE_BRANDS if re.search(rx, s)]
    if brands:
        scope["brand"] = brands
    _grades(s, scope)
    if re.search("under 24 months|0-24|newer", s):
        scope["band"] = ["0-24m"]
    elif re.search("25-48", s):
        scope["band"] = ["25-48m"]
    elif re.search("over 48|49|older", s):
        scope["band"] = ["49m+"]
    if m := re.search(r"(over|more than|above|at least)\s*(\d+)\s*days", s):
        scope["dohMin"] = int(m.group(2))
    if m := re.search(r"(over|more than|above|at least)\s*(\d+)\s*units", s):
        scope["qtyMin"] = int(m.group(2))
    return ParsedRule(_first_path(s, DEVICE_PATHS), _action(s), scope)


# ---------------------------------------------------------------- industrial (the demo's vocabulary)
def _words(rx_forms: Sequence[str]) -> str:
    return "|".join(r"\b" + re.escape(f) for f in rx_forms if f)


def _industrial_paths(t: Template, s: str) -> list[tuple[str, str]]:
    extra = {"material": ["recycl", "scrap", "material"], "exit": ["exit"], "relase": ["re-lease", "lease"],
             "resale": ["resale", "resell"]}  # fmt: skip
    table = [(p.id, _words([p.name.lower(), *extra.get(p.id, [])])) for p in t.paths if p.id not in ("intparts", "extparts")]
    parts = "extparts" if re.search(r"sell|external", s) else "intparts"
    return [*table, (parts, r"\bparts?\b|recovered-part")]


INDUSTRIAL_READ = ("cls", "grade", "site", "owner")  # the dims read above; any other set dim is read by its phrase


def _phrased(t: Template, s: str, scope: dict[str, Any]) -> None:
    """Any other set dim of the pack (e.g. the telemetry `alarm`, MVP-7.1): a value whose rule-text phrase (the
    pack's wording) occurs in the text as whole words."""
    phrases = {p.key: p for p in t.wording.phrases}
    for d in t.dims:
        p = phrases.get(d.key)
        if d.kind != "set" or d.key in INDUSTRIAL_READ or p is None:
            continue
        hits = [v for v in d.values if re.search(_words([p.fmt.format(p.words.get(v, v)).lower()]) + r"\b", s)]
        if hits:
            scope[d.key] = hits


def _industrial(t: Template, s: str) -> ParsedRule:
    world = golden.load("world")
    scope: dict[str, Any] = {}
    cls = []
    for key, c in world["classes"].items():
        forms = [c["label"].lower(), *(x.strip().lower() for x in c["plural"].split("/")), key if len(key) > 2 else ""]
        if re.search(_words(forms), s):
            cls.append(key)
    if cls:
        scope["cls"] = cls
    _grades(s, scope)
    site = [x["id"] for x in world["sites"] if re.search(_words([x["id"].lower()]) + r"\b|" + _words([x["name"].lower()]), s)]
    if site:
        scope["site"] = site
    owners = next((d.values for d in t.dims if d.key == "owner"), ())
    owner = [o for o in owners if re.search(_words([o.lower()]) + r"\b", s)]
    if owner:
        scope["owner"] = owner
    _phrased(t, s, scope)
    return ParsedRule(_first_path(s, _industrial_paths(t, s)), _action(s), scope)


PARSERS: dict[str, Callable[[str], ParsedRule]] = {"tool_fleet": _tool_fleet, "device": _device}


def parse_rule(t: Template, text: str) -> ParsedRule:
    s = text.lower()
    if t.key == "industrial":
        return _industrial(t, s)
    return PARSERS[t.key](s)
