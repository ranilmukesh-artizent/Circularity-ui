"""Ask's starter questions by pack and by page (UI pack audit E17).

The demo's starters (fixtures/golden/ask.json, by role) stay as they are; the web app shows them for the industrial pack
and the pages the demo has. This module adds what a pack or a page can be asked: each entry is a question the role can
really put to Ask's read tools, or "Prepare ... for my approval" (Ask holds a draft for a person; it never approves,
waives or overrides). Pack starters live here, not in the pack JSON: the pack's `prompts` are descriptions for Compose and
the pack schema takes no other field (decision 26 Nov 2026, like the worked questions in di.services.questions).

A starter is offered only when the account may open the page it is about (`policy.can_page`, the rule the demo's examples
use too); the server decides, the web app only displays.
"""

from dataclasses import dataclass

from sqlalchemy import text

from di.core import policy
from di.core.db import SessionLocal

#: words that would make a starter an action on a person's behalf; checked at import
_FORBIDDEN_WORDS = ("approve ", "waive", "override", "decline ", "grant ")


@dataclass(frozen=True)
class Starter:
    text: str
    page: str = "product"
    section: str | None = "case"


def _s(*texts: str, page: str = "product", section: str | None = "case") -> tuple[Starter, ...]:
    return tuple(Starter(t, page, section) for t in texts)


#: what a case of the pack can be asked (the pack's key is the case's template)
PACK_CASE: dict[str, tuple[Starter, ...]] = {
    "tool_fleet": _s(
        "Which contract or buyer order can take this tool?",
        "Why is this tool not a refurbish?",
        "Prepare the repair-or-sell decision for my approval",
    ),
    "device": _s(
        "Which channel gives the best net price for this device?",
        "Is the data-wipe certificate on file?",
        "Prepare the listing decision for my approval",
    ),
    "used_cars": _s(
        "Which lot or channel gives the best gross after costs?",
        "Is the title and finance check complete?",
        "Prepare the channel decision for my approval",
    ),
    "telecom_network": _s(
        "Which site needs this unit most?",
        "Has the export-control check been recorded?",
        "Prepare the redeploy-or-resell decision for my approval",
    ),
    "medical_rental": _s(
        "Which hospital needs this device next?",
        "Is the decontamination record on file?",
        "Prepare the re-rent decision for my approval",
    ),
    "itad": _s(
        "Does this serial match the pickup manifest?",
        "Has every disk been sanitised?",
        "Prepare the disposition for my approval",
    ),
    "rental_fleet": _s(
        "Should this machine be re-rented or sold?",
        "What does keeping it idle cost per week?",
        "Prepare the branch transfer for my approval",
    ),
    "battery": _s(
        "What is this pack's state of health and which route does it allow?",
        "Does it need the dangerous-goods lane?",
        "Prepare the reuse-or-recycle decision for my approval",
    ),
    "auto_core": _s(
        "Does this core meet the acceptance criteria?",
        "How much deposit would be credited, and why?",
        "Prepare the deposit credit for my approval",
    ),
}

#: what the pack as a whole can be asked (its worked analytics questions where it has them)
PACK_WIDE: dict[str, tuple[Starter, ...]] = {
    "tool_fleet": _s("Where do returned tools go, and which classes recover the most?", page="analytics", section=None),
    "device": _s(
        "Why did price realised drop after the launch?",
        "Which retail partner causes the most grading disputes?",
        page="analytics",
        section=None,
    ),
    "used_cars": _s(
        "Where do returned EV crossovers sell fastest?",
        "Which lots sell lease returns fastest?",
        page="analytics",
        section=None,
    ),
    "telecom_network": _s(
        "Why are we still buying new power units when returns are coming in?",
        "Where are our idle spares?",
        page="analytics",
        section=None,
    ),
    "medical_rental": _s(
        "Why did turnaround slip at the East depot?",
        "Which device models are retired earliest?",
        page="analytics",
        section=None,
    ),
    "itad": _s("Which customers' pickups have the most missing serials?", page="analytics", section=None),
    "rental_fleet": _s("Which branches have the most idle machines?", page="analytics", section=None),
    "battery": _s("Which chemistries keep the most state of health?", page="analytics", section=None),
    "auto_core": _s("Which dealers return the most rejected cores?", page="analytics", section=None),
}

#: what a page can be asked, whatever the pack
PAGE: dict[str, tuple[Starter, ...]] = {
    "home": _s("What needs me today?", "What did agents propose and hold for me?", page="home", section=None),
    "modeler": _s(
        "Which guardrails does this flow keep?",
        "Which rules in this flow changed the most decisions?",
        "Prepare a draft rule from a sentence for my approval",
        page="modeler",
        section=None,
    ),
    "analytics": _s(
        "What moved recovery this month?",
        "Which exceptions are the most expensive?",
        page="analytics",
        section=None,
    ),
    "integration": _s(
        "Which sources need attention?",
        "Why is this workflow failing?",
        "What is stuck in the last sync?",
        page="integration",
        section=None,
    ),
    "case": _s(
        "Why this route for this case?",
        "Which evidence is missing?",
        "Compare the routes for this case",
    ),
}

for _g in (PACK_CASE, PACK_WIDE, PAGE):
    for _v in _g.values():
        for _x in _v:
            if any(w in _x.text.lower() for w in _FORBIDDEN_WORDS):
                raise RuntimeError(f"a starter may not act for a person: {_x.text}")


def starters_for(a: policy.Account, page: str | None, pack_key: str | None, has_case: bool) -> dict:
    """The starters for what the person is looking at, in order: the pack's, then the page's. `pack_key` is the pack of the
    case in view or of the Modeler flow's template; `pack` in the answer is None for the industrial pack and for pages
    without one (the web app then shows the demo's starters first)."""
    pack = pack_key if pack_key in PACK_CASE else None
    pg = page or "home"
    out: list[Starter] = []
    if pack:
        out += PACK_CASE[pack] if has_case else PACK_WIDE[pack]
    if has_case:
        out += PAGE["case"]
    elif pg in PAGE:
        out += PAGE[pg]
    seen: set[str] = set()
    items = []
    for s in out:
        if s.text in seen or not policy.can_page(a, s.page, s.section):
            continue
        seen.add(s.text)
        items.append({"text": s.text})
    return {"pack": pack, "starters": items}


def for_request(a: policy.Account, page: str | None, section: str | None, case_id: str | None) -> dict:
    """`starters_for` with the pack found: the case's template, or on the Modeler the flow's template (`section`)."""
    key = section if page == "modeler" else None
    if case_id:
        with SessionLocal() as s:
            key = s.execute(text("SELECT data ->> 'template' FROM case_record WHERE id = :c"), {"c": case_id[:16]}).scalar()
        key = key or "industrial"
    return starters_for(a, page, key, bool(case_id))
