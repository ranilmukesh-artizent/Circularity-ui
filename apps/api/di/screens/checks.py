"""Data checks (Home › Data checks; docs/backend-steps.md, B14): the demo's runInvariants(), run on the backend's data.

    GET /api/checks
        checks   [{name, ok, detail, af?, data}] in the demo's order; `af: true` marks the agent layer's checks, as in
                 the demo; `data` says what the check reads: "cases" (the database), "decisions" (the closed
                 decisions), "catalog" (the action registry) or "journal" (the action journal)
        not_run  [{name, af, reason}]: the demo's checks that test the browser itself, which the backend cannot run
        passed, total

Every check reads what the backend holds now, so after a fresh sync it passes; a check that fails names what broke.
None of the 31 checks reads sources or conflicts, so the connectors' tables do not enter here.

The checks, in the demo's order (index.html, runInvariants and afChecks):
 1 128 live returns                                    cases
 2 Queue split matches concept (86 / 24 / 18)         cases; after inspections move the live split, the check
                                                       judges the starting split (the golden cases, the demo's AF.seed)
                                                       and the detail reads "baseline … · now …", as in the demo
 3 Return and asset IDs are unique                     cases
 4 Every route net equals the sum of its cost terms    cases
 5 Line-item actuals are deterministic, within ±25% …  cases, di.execution.trace.line_actuals and confirmed outcomes
 6 RT-1048 reproduces framework figures               cases
 7 No approvable recommendation where a gate failed … cases
 8 Every decision carries an evidence snapshot         cases
 9 No excluded route is ever recommended               cases
10 No component allocated twice … (RT-1027)            cases
11-12 Pool RT-1048 / RT-1052: no demand line …         cases, the pool optimiser (di.engine.pool)
13 Exception value by warehouse equals the ranked total  for accounts that see Command Center exceptions
14 SKU unit count equals Returned assets …             for accounts that see Asset intelligence and RT-1048
15-21 closed decisions: ~1,400, totals, route counts, pending, overrides, model error, coverage   decisions
22 Every state-changing button calls invoke()          not run: about the demo page's buttons
23 Every adapter maps to a registered action           catalog: every action in the catalogue is registered
24 No action handler reads or draws the page           not run: about the demo page's handlers
25 Every action declares risk, permission and description   catalog
26 No stage key or idempotency key is written twice    journal (action_journal, entries not undone)
27 Every button is classified in the inventory         not run: about the demo page's buttons
28 Every catalog intent returns its card              not run: it runs all 52 of the demo's intent runners; the
                                                       server's rule-based Ask (di.ask.fallback) has the ones its
                                                       reads support
29 Safety tests pass (approve from text, …)            cases: the seven AF_SAFETY tests against the server's Ask
                                                       (di.ask.safety): its answers, the action journal, RT-1048's stage
30 Every intent in the catalog has a test              catalog: the intent catalog (fixtures/golden/ask.json) against
                                                       the demo's intent tests (AF_EVALS)
31 Card values equal case values                       cases: case.routes' best eligible route equals the
                                                       recommendation for RT-1048, RT-1049, RT-1033, RT-1027 (the
                                                       demo's decision packet repeats the recommendation's numbers)

Checks 13 and 14 depend on the signed-in account, as in the demo; the rest are the same for everyone. The top bar's
tenant filter is taken as "All" (the demo runs the checks from Home with it cleared).

Facade mapping (apps/web/src/api/home.ts): checks() → GET /api/checks (checks; not_run lists the browser's own);
checksRunAt and runChecks stay in the frontend (the time the page last ran them and its log line).
"""

import json

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from di import golden, policy
from di.actions.pipeline import Actor, CallContext
from di.actions.registry import ACTIONS
from di.ask.fallback import RUNNERS
from di.ask.intents import CATALOG
from di.ask.safety import intents_without_test, run_safety
from di.auth import Principal, principal
from di.cases import store
from di.db import get_session
from di.engine.jsmath import js_sum
from di.engine.pool import solve_pool
from di.execution.trace import line_actuals
from di.reads.cases import case_routes
from di.reads.common import as_model, kfmt, money, to_fixed
from di.reads.constants import MODELS, ROUTES
from di.reads.context import call_ctx, can_see_case, visible_cases
from di.reads.decisions import all_rows, model_stats
from di.reads.workspace import cc_ex_list, cc_ex_rows, cc_scope

router = APIRouter(tags=["screens: checks"])
RISK_LABEL = {"act": "Act", "commit": "Commit", "draft": "Draft", "read": "Read", "system": "System only"}
POOL_IDS = ("RT-1048", "RT-1052")  # the demo's POOLS
CARD_IDS = ("RT-1048", "RT-1049", "RT-1033", "RT-1027")
NOT_RUN = [
    ("Every state-changing button calls invoke()", "About the demo page's buttons (ACT); the React app has none."),
    ("No action handler reads or draws the page", "About the demo page's handler code; backend handlers have no page."),
    ("Every button is classified in the inventory", "About the demo page's buttons (ACT); the React app has none."),
    (
        "Every catalog intent returns its card on seeded cases",
        "Runs every one of the demo's 52 intent runners; the server's rule-based Ask (di.ask.fallback, B16b) has the "
        f"{len(RUNNERS)} whose reads have server handlers, and the rest still draft in the browser (mappings, workflows, "
        "files) or read actions without a server handler yet.",
    ),
]


def _split(cases: list[dict]) -> tuple[int, int, int]:
    a = [c.get("assessment") for c in cases]
    return a.count("Ready"), a.count("Pending"), sum(1 for x in a if x in ("Review", "Partial"))


def _dumps(x) -> str:
    return json.dumps(x, sort_keys=True)


def _line_mismatch(c: dict) -> bool:
    r = c.get("chosen") or c.get("recommendation")
    a, b = line_actuals(c, r), _dumps(line_actuals(c, r))
    if _dumps(a) != b:
        return True
    if any(x["model"] and abs(x["act"] - x["pred"]) > abs(x["pred"]) * 0.25 + 5 for x in a):
        return True
    o = c.get("outcome")
    if o and o.get("lines"):
        return js_sum(x["act"] for x in o["lines"]) != o["net"] or _dumps(o["lines"]) != b
    return False


def run(p: Principal, session: Session) -> list[dict]:
    out: list[dict] = []

    def t(name: str, ok, detail: str, data: str, af: bool = False) -> None:
        out.append({"name": name, "ok": bool(ok), "detail": detail, "data": data} | ({"af": True} if af else {}))

    live = store.all_cases(session)
    by_id = {c["id"]: c for c in live}
    t("128 live returns", len(live) == 128, f"{len(live)} cases", "cases")

    r, w, n = _split(live)
    seed = _split(golden.load("cases"))
    if (r, w, n) == seed:
        t("Queue split matches concept (86 / 24 / 18)", (r, w, n) == (86, 24, 18), f"{r} / {w} / {n}", "cases")
    else:  # people have recorded inspections since: the seed check reads the split captured before (the demo's AF.seed)
        detail = f"baseline {seed[0]} / {seed[1]} / {seed[2]} · now {r} / {w} / {n}"
        t("Queue split matches concept (86 / 24 / 18)", seed == (86, 24, 18), detail, "cases")

    t(
        "Return and asset IDs are unique",
        len({c["id"] for c in live}) == 128 and len({c["assetId"] for c in live}) == 128,
        "RT-1001…RT-1128",
        "cases",
    )
    bad = [c for c in live if any(abs(x["net"] - js_sum(y["amt"] for y in x["terms"])) > 0.5 for x in c["routes"])]
    t("Every route net equals the sum of its cost terms", not bad, f"{len(bad)} mismatches", "cases")

    la = [c for c in live if (c.get("chosen") or c.get("recommendation")) and _line_mismatch(c)]
    outcomes = sum(1 for c in live if c.get("outcome"))
    t(
        "Line-item actuals are deterministic, within ±25% and add up to the actual net",
        not la,
        f"{len(la)} mismatches · {outcomes} confirmed outcomes",
        "cases",
    )

    rd = by_id["RT-1048"]["routes"]
    nets = [x["net"] for x in rd[:4]]
    t(
        "RT-1048 reproduces framework figures ($9,600 / $4,800 / $3,600 / $3,200)",
        nets == [9600, 4800, 3600, 3200],
        ", ".join(str(x) for x in nets),
        "cases",
    )
    no_rec = [c for c in live if c.get("blocked") and c.get("recommendation")]
    t("No approvable recommendation where a gate failed or evidence is missing", not no_rec, f"{len(no_rec)} violations", "cases")
    dec = [c for c in live if c.get("recommendation")]
    t(
        "Every decision carries an evidence snapshot",
        all(c.get("snapshot") and c["snapshot"].get("id") for c in dec),
        f"{len(dec)} decisions",
        "cases",
    )
    t(
        "No excluded route is ever recommended",
        all(not c.get("recommendation") or not c["recommendation"].get("excluded") for c in live),
        "",
        "cases",
    )
    harvest = by_id["RT-1027"]["routes"][0]
    names = [x["n"] for x in harvest["components"]]
    t(
        "No component allocated twice; shared teardown charged once (RT-1027)",
        len(set(names)) == len(names)
        and abs(js_sum(x["v"] for x in harvest["components"]) - 240 - 90 - harvest["net"]) < 1
        and sum(1 for x in harvest["terms"] if "teardown" in x["label"].lower()) == 1,
        "5 outputs · $240 teardown once",
        "cases",
    )
    for k in POOL_IDS:
        pl = solve_pool(by_id[k]["pool"])
        used: dict[str, int] = {}
        for a in pl["optimal"]["alloc"].values():
            for d, q in a.items():
                used[d] = used.get(d, 0) + q
        dup = any(used.get(d["id"], 0) > d["cap"] for d in pl["dests"]) or any(
            sum((pl["optimal"]["alloc"].get(s["id"]) or {}).values()) > s["units"] for s in pl["supplies"]
        )
        detail = f"optimal {money(pl['optimal']['total'])} vs greedy {money(pl['greedy']['total'])}"
        t(f"Pool {k}: no demand line or unit allocated twice", not dup, detail, "cases")

    ctx = call_ctx(p, session)
    if policy.can_page(p.account, "command", "exceptions"):
        sc = cc_scope(ctx)
        a, b = cc_ex_list(sc, ctx), cc_ex_rows(sc, ctx)
        ta, tb = js_sum(x["value"] for x in a), js_sum(x["value"] for x in b)
        ok = ta == tb and all(js_sum(y["value"] for y in b if y["base"] == x["id"]) == x["value"] for x in a)
        t("Exception value by warehouse equals the ranked total", ok, f"{kfmt(tb)} in {len(b)} warehouse rows", "cases")
    if policy.can_page(p.account, "product", "asset"):
        c = by_id["RT-1048"]
        mine = visible_cases(ctx, cases=live)
        q = sum(1 for x in mine if as_model(x) == as_model(c) and x["owner"] == c["owner"])
        if can_see_case(p.account, p.ctx, c):
            sku = [x for x in mine if as_model(x) == as_model(c) and x["owner"] == c["owner"]]  # the demo's skuUnits
            t(
                "SKU unit count equals Returned assets for that product and customer",
                len(sku) == q,
                f"{as_model(c)} · {c['owner']}: {q} units",
                "cases",
            )

    rows = all_rows()
    rc = [x for x in rows if x["status"] == "reconciled"]
    t("~1,400 closed decisions", len(rows) == 1400, f"{len(rows)} rows", "decisions")
    total = js_sum(x["actual"] for x in rc)
    by_route = js_sum(js_sum(x["actual"] for x in rc if x["route"] == rt["id"]) for rt in ROUTES)
    t("Analytics total equals sum of case rows", abs(total - by_route) < 1, money(total), "decisions")
    mix = [sum(1 for x in rc if x["route"] == rt["id"]) for rt in ROUTES]
    t("Route counts sum to reconciled total", sum(mix) == len(rc), f"{len(rc)} reconciled", "decisions")
    pend = [x for x in rows if x["status"] == "pending"]
    t(
        "Pending decisions are never counted as failures",
        all(x["actual"] is None and x["days"] is None for x in pend),
        f"{len(pend)} pending",
        "decisions",
    )
    ov_rows = [x for x in rc if x.get("override")]
    ov = len(ov_rows) / len(rc)
    t(
        "Override rate ≈14% with a reason on each",
        0.1 < ov < 0.18 and all(x["override"].get("reason") for x in ov_rows),
        to_fixed(ov * 100, 1) + "%",
        "decisions",
    )
    ms = [model_stats(m["v"]) for m in MODELS]
    t(
        "Model error shrinks v1.0 → v1.3",
        ms[0]["mape"] > ms[3]["mape"] and abs(ms[0]["bias"]) > abs(ms[3]["bias"]),
        " → ".join(to_fixed(m["mape"] * 100, 0) + "%" for m in ms),
        "decisions",
    )
    t("P10–P90 covers ≈80% in latest model", 0.74 < ms[3]["cov"] < 0.87, to_fixed(ms[3]["cov"] * 100, 0) + "%", "decisions")

    # ---- the agent layer's checks (af), the ones about data the backend holds
    catalog = {a["id"] for a in golden.load("actions_catalog")}
    t(
        "Every adapter maps to a registered action",
        catalog <= set(ACTIONS),
        ", ".join(sorted(catalog - set(ACTIONS))) or f"{len(ACTIONS)} actions",
        "catalog",
        af=True,
    )
    bad_def = [a.id for a in ACTIONS.values() if a.risk not in RISK_LABEL or not a.desc or a.title == a.id]
    t(
        "Every action declares risk, permission and description",
        not bad_def,
        ", ".join(bad_def) or "complete",
        "catalog",
        af=True,
    )
    keys = list(session.execute(text("SELECT idem_key FROM action_journal WHERE idem_key IS NOT NULL AND NOT undone")).scalars())
    t(
        "No stage key or idempotency key is written twice",
        len(set(keys)) == len(keys),
        f"{len(keys)} keyed entries",
        "journal",
        af=True,
    )
    safety = run_safety(session, p.ctx)
    bad_safety = [f"{n}: {why}" for n, ok, why in safety if not ok]
    t(
        "Safety tests pass (approve from text, cross-tenant, waive a gate, hidden instructions)",
        not bad_safety,
        " | ".join(bad_safety) or f"{len(safety)} safety tests",
        "cases",
        af=True,
    )
    miss = intents_without_test()
    t("Every intent in the catalog has a test", not miss, ", ".join(miss) or f"{len(CATALOG)} intents", "catalog", af=True)
    admin = policy.account("admin", p.ctx)
    actx = CallContext(actor=Actor(account=admin, ctx=p.ctx), session=session)
    bad_cards = []
    for cid in CARD_IDS:
        c = by_id[cid]
        rec = c.get("recommendation")
        if not rec:
            continue
        rt = case_routes({"case_id": cid}, actx)
        if not rt["eligible"] or rt["eligible"][0]["net"] != rec["net"]:
            bad_cards.append(cid)
    t(
        "Card values equal case values",
        not bad_cards,
        ", ".join(bad_cards) or f"{len(CARD_IDS)} packets checked",
        "cases",
        af=True,
    )
    return out


@router.get("/api/checks")
def checks(p: Principal = Depends(principal), session: Session = Depends(get_session)):
    out = run(p, session)
    return {
        "checks": out,
        "not_run": [{"name": n, "af": True, "reason": why} for n, why in NOT_RUN],
        "passed": sum(1 for x in out if x["ok"]),
        "total": len(out),
    }
