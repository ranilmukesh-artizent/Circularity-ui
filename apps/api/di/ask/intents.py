"""The demo's intent router (index.html, `afParse`, `afMatch`, `AF_INTENTS`): a question becomes parameters and an intent.

The catalog (52 intents, each with weighted patterns), the route words and the product classes come from the demo
itself (fixtures/golden/ask.json, apps/web/scripts/golden/ask.mjs), so the server scores exactly the patterns the demo
scores. JavaScript patterns are compiled with Python's `re`; the catalog uses no syntax the two read differently.

    parse(text, obj, case_ids)  the demo's afParse: case ids, places, customers, classes, routes, a what-if change,
                                amounts, time, evidence kinds, a source
    match(p, obj)               the demo's afMatch: every intent whose patterns score at least 1, best first
"""

import re
from dataclasses import dataclass
from typing import Any

from di import golden
from di.engine.jsmath import js_round
from di.reads.common import SOURCES, to_fixed

_G = golden.load("ask")


def _rx(source: str, flags: str) -> re.Pattern:
    return re.compile(source, (re.I if "i" in flags else 0) | (re.M if "m" in flags else 0))


@dataclass(frozen=True)
class Intent:
    id: str
    area: str
    need: str | None
    ctx: str | None
    title: str
    m: tuple[tuple[re.Pattern, float], ...]


CATALOG: list[Intent] = [
    Intent(i["id"], i["area"], i["need"], i["ctx"], i["title"], tuple((_rx(s, f), w) for s, f, w in i["m"]))
    for i in _G["catalog"]
]
INTENT = {i.id: i for i in CATALOG}
ROUTE_WORDS = [(rid, _rx(s, f)) for rid, s, f in _G["route_words"]]
CLASSES = [(cid, _rx(s, f)) for cid, s, f in _G["classes"]]
STARTERS: dict[str, list[str]] = _G["starters"]
IGNORE_RULES = re.compile(r"(ignore|disregard) (all |the |previous |your )?(rules|instructions)|you are now|system prompt", re.I)


def _source_rx(s: dict) -> re.Pattern:
    names = [x.lower() for x in (s.get("id"), s.get("name"), s.get("vendor"), s.get("short")) if x]
    return re.compile(r"\b(" + "|".join(re.escape(x) for x in names) + r")\b")


_SOURCE_RX = [(sid, _source_rx(s)) for sid, s in SOURCES.items()]


def parse(text: str, obj: dict | None, case_ids: set[str]) -> dict[str, Any]:
    """The demo's afParse. `obj` is the page's object ({kind, id}) or None; `case_ids` the cases that exist."""
    t = " " + re.sub(r"[’']", "'", str(text or "").lower()) + " "
    p: dict[str, Any] = {"raw": text, "t": t}
    p["cases"] = list(dict.fromkeys("RT-" + m for m in re.findall(r"\brt[-\s]?(\d{4})\b", t) if "RT-" + m in case_ids))
    p["closed"] = list(dict.fromkeys("CS-" + m for m in re.findall(r"\bcs[-\s]?(\d{4})\b", t)))
    p["thisRef"] = bool(re.search(r"\b(this|it|that|the case|the asset|this asset|this case)\b", t))
    p["case"] = p["cases"][0] if p["cases"] else (obj["id"] if obj and obj.get("kind") == "case" else None)
    if w := re.search(r"warehouse\s*(1|2|one|two)\b", t):
        p["location"] = "Warehouse " + ("1" if w[1] == "one" else "2" if w[1] == "two" else w[1])
    if re.search(r"repair cent(re|er)", t):
        p["location"] = "Repair centre"
    if cu := re.search(r"customer\s*([abc])\b", t):
        p["owner"] = "Customer " + cu[1].upper()
    if cl := next((cid for cid, rx in CLASSES if rx.search(t)), None):
        p["cls"] = cl
    p["routes"] = [rid for rid, rx in ROUTE_WORDS if rx.search(t)]
    if pc := re.search(r"(\d+(?:\.\d+)?)\s*(%|percent)", t):
        v = float(pc[1]) / 100
        if re.search(r"(less|lower|down|drop|fall|cheaper|decrease|cut|reduc)", t):
            v = -v
        f = (
            "cost"
            if re.search(r"(repair|prep|preparation|refurb|cost|fees|freight|labou?r)", t)
            else "purchase"
            if re.search(r"(purchase|new price|buy new|new unit|replacement price)", t)
            else "service"
            if re.search(r"service", t)
            else "market"
            if re.search(r"(market|price|resale value|sale price|demand price|buyer)", t)
            else "cost"
        )
        p["whatif"] = {"factor": f, "mult": float(to_fixed(1 + v, 3)), "pct": js_round(v * 100)}
    if re.search(r"(demand|order).{0,20}(cancel|lost|gone|disappear|falls through)|(no|without) (confirmed )?demand", t):
        p["demandOff"] = True
    am = re.search(r"\$\s?([\d,]+(?:\.\d+)?)\s?(k|m)?\b", t) or re.search(r"\b([\d,]{4,})\s*(dollars|usd)\b", t)
    if am:
        n = float(am[1].replace(",", "")) * (1000 if am[2] == "k" else 1e6 if am[2] == "m" else 1)
        p["amount"] = int(n) if n.is_integer() else n
    if re.search(r"this week|past week|last 7 days|last week", t):
        p["days"] = 7
    elif re.search(r"today", t):
        p["days"] = 1
    elif re.search(r"this month|last 30 days", t):
        p["days"] = 30
    if re.search(r"last month|previous month", t):
        p["month"] = 10
    ek = (
        "insp"
        if re.search(r"(inspection|inspect)", t) or re.search(r"(test)", t)
        else "photo"
        if re.search(r"photo", t)
        else "eng"
        if re.search(r"assessment", t)
        else None
    )
    if ek:
        p["evidence"] = ek
    src = next((sid for sid, rx in _SOURCE_RX if rx.search(t)), None)
    p["source"] = src or (obj["id"] if obj and obj.get("kind") == "source" else None)
    return p


@dataclass
class Hit:
    intent: Intent
    s: float
    raw: float


def match(p: dict, obj: dict | None) -> list[Hit]:
    """The demo's afMatch: score every intent, keep those whose raw score reaches 1, best first (a stable sort)."""
    out = []
    for i in CATALOG:
        s = 0.0
        for rx, w in i.m:
            if rx.search(p["t"]):
                s += w
        if s > 0 and i.need == "case" and p.get("case"):
            s += 0.6
        if s > 0 and i.need == "source" and p.get("source"):
            s += 0.6
        if s > 0 and obj and i.ctx and i.ctx == obj.get("kind"):
            s += 0.5
        raw = s
        if s > 0 and i.need == "case" and not p.get("case"):
            s -= 0.5
        out.append(Hit(i, s, raw))
    return sorted((h for h in out if h.raw >= 1), key=lambda h: -h.s)
