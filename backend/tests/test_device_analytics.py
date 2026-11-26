"""Plan 9, P9-6.17 (story DV-13): two worked device analytics questions, answered by `device.question`.

`price_after_launch` ("Why did price realised drop?") and `disputes_by_partner` ("Who causes grading disputes?") are computed from
the market's sales, feed and launches and the lab's disputes (R16: no figure by a model); a model may only word the sentence, and
every number in its sentence must be in the computed answer. The tests seed their own rows (ids `AN-T-*`) and clear the tables.
"""

# ruff: noqa: E501 - long SQL and sentence lines

import json
from datetime import date, datetime, timedelta

import pytest
from pydantic_ai import ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from sqlalchemy import text

from di.core import clock
from di.core.db import SessionLocal, engine
from di.services.actions.registry import ACTIONS
from di.services.agents import catalog
from di.services.agents.forbidden import forbidden
from di.services.device import analytics
from tests import starting
from tests.helpers import call

ORG_A, ORG_B = "Customer A", "Customer B"
MODEL, SKU = "Galaxy S24", "Galaxy S24|128"
REASON = "Screen graded before power-on"


def _clean() -> None:
    with engine.begin() as conn:
        for t in ("device_tradein", "device_price_point", "device_launch", "device_sale", "device_dispute"):
            conn.execute(text(f"DELETE FROM {t}"))  # noqa: S608 - fixed names


@pytest.fixture(autouse=True)
def fresh():
    starting.reset()
    _clean()
    yield
    starting.reset()
    _clean()


def _monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


def _tradein(conn, imei: str, org: str, model: str = MODEL, partner: str = "P01") -> None:
    conn.execute(
        text(
            "INSERT INTO device_tradein (trade_in_id, org_unit_id, imei, sku, quote, partner, bulk, received_at, source) "
            "VALUES (:t, :o, :i, CAST(:s AS jsonb), CAST(:q AS jsonb), :p, false, now(), 'test')"
        ),
        {"t": "AN-T-" + imei, "o": org, "i": imei, "s": json.dumps({"model": model, "storageGb": 128, "brand": "X"}),
         "q": json.dumps({"declaredGrade": "A", "amount": 100}), "p": partner},
    )  # fmt: skip


def _seed_prices() -> date:
    """Galaxy S24 sells at 99% of the feed for 9 weeks, then at 90% in the 3 weeks after its successor launched; Pixel 8 steadily at
    97%. Two sales a week each; the feed is 100 for both. Returns the launch day."""
    today = clock.now().date()
    start = _monday(today) - timedelta(weeks=11)
    launch = start + timedelta(weeks=9)
    n = 0
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO device_launch (model, successor, launched_on) VALUES (:m, 'Galaxy S25', :d)"),
            {"m": MODEL, "d": launch},
        )
        for model, sku in ((MODEL, SKU), ("Pixel 8", "Pixel 8|128")):
            for w in range(12):
                wk = start + timedelta(weeks=w)
                conn.execute(
                    text(
                        "INSERT INTO device_price_point (sku_key, grade, week, price, currency, source) VALUES (:k, 'A', :w, 100, 'USD', 'test')"
                    ),
                    {"k": sku, "w": wk},
                )
                pct = (99 if w < 9 else 90) if model == MODEL else 97
                for k in range(2):
                    n += 1
                    imei = f"3599{n:011d}"
                    _tradein(conn, imei, ORG_A, model)
                    conn.execute(
                        text(
                            "INSERT INTO device_sale (sale_id, imeis, price, fees, buyer_returns, settled_at, case_ids) "
                            "VALUES (:s, CAST(:i AS jsonb), :p, 5, 0, :at, '[]'::jsonb)"
                        ),
                        {"s": f"AN-T-S{n}", "i": json.dumps([imei]), "p": pct, "at": datetime.combine(wk + timedelta(days=k), datetime.min.time())},
                    )  # fmt: skip
    return launch


def _seed_disputes() -> None:
    """50 disputes of Customer A in the last 90 days: P02 15, P04 14 (together 29), P01 8, P03 7, P05 6; and 10 of Customer B (P09)."""
    spread = [("P02", 15), ("P04", 14), ("P01", 8), ("P03", 7), ("P05", 6)]
    n = 0
    with engine.begin() as conn:
        for partner, count in spread:
            for _ in range(count):
                n += 1
                imei = f"3588{n:011d}"
                _tradein(conn, imei, ORG_A, partner=partner)
                reason = REASON if partner in ("P02", "P04") else "Scratches not recorded"
                _dispute(conn, f"AN-T-D{n}", imei, partner, reason, n)
        for _ in range(10):
            n += 1
            imei = f"3577{n:011d}"
            _tradein(conn, imei, ORG_B, partner="P09")
            _dispute(conn, f"AN-T-D{n}", imei, "P09", "Battery health disputed", n)


def _dispute(conn, did: str, imei: str, partner: str, reason: str, n: int) -> None:
    conn.execute(
        text("INSERT INTO device_dispute (id, imei, partner, reason, opened_at, outcome) VALUES (:i, :m, :p, :r, :at, 'open')"),
        {"i": did, "m": imei, "p": partner, "r": reason, "at": clock.now() - timedelta(days=1 + n % 60)},
    )


def _ask(qid: str, user: str = "planner-a", **extra) -> dict:
    r = call("device.question", {"question_id": qid, **extra}, user)
    assert r["ok"], r
    return r["output"]


def test_dv_13_price_drop_after_launch():
    launch = _seed_prices()
    out = _ask("price_after_launch")
    assert out["sentence"] == (
        f"Price realised for {MODEL} fell from 99% to 90% of the feed in the 3 weeks after its successor launched on "
        f"{launch.day} {launch:%b %Y}; move volume to wholesale earlier"
    )
    line = next(s for s in out["chart"]["series"] if s["name"] == MODEL)
    assert out["chart"]["kind"] == "line" and len(line["points"]) == 12
    assert [p["y"] for p in line["points"]] == [99.0] * 9 + [90.0] * 3
    assert [p["launch"] for p in line["points"]].index(True) == 9  # the launch week is marked
    assert 8 <= line["points"][0]["y"] - line["points"][-1]["y"] <= 12
    assert len(out["examples"]) == 5 and all(e["model"] == MODEL for e in out["examples"])


def test_dv_13_disputes_by_partner():
    _seed_disputes()
    out = _ask("disputes_by_partner")
    assert out["sentence"] == "Partners P02 and P04 cause 58% of grading disputes (screen graded before power-on)"
    assert out["chart"]["kind"] == "bar"
    pts = {p["x"]: p["y"] for p in out["chart"]["series"][0]["points"]}
    assert (
        pts["P02"] + pts["P04"] == 29 and sum(pts.values()) == 50
    )  # Customer B's P09 is not in an admin-less planner's view of A
    assert 1 <= len(out["examples"]) <= 5 and all(e["reason"] == REASON for e in out["examples"])


def test_device_question_tenant_scoped():
    _seed_disputes()
    _seed_prices()
    b = _ask("disputes_by_partner", "planner-b")
    assert [p["x"] for p in b["chart"]["series"][0]["points"]] == ["P09"]
    assert all(e["partner"] == "P09" for e in b["examples"])
    assert _ask("price_after_launch", "planner-b")["examples"] == []  # every sale is Customer A's
    refused = call("device.question", {"question_id": "disputes_by_partner", "org_unit_id": ORG_A}, "planner-b")
    assert refused["ok"] is False and refused["error"]["code"] == "tenant_boundary"
    assert call("device.question", {"question_id": "nope"}, "planner-a")["ok"] is False


def test_dv_13_worked_question_registry_and_agent_rules():
    assert set(analytics.REGISTRY) >= {"price_after_launch", "disputes_by_partner"}
    assert analytics.REGISTRY["price_after_launch"].question == "Why did price realised drop?"
    assert analytics.REGISTRY["disputes_by_partner"].question == "Who causes grading disputes?"
    a = ACTIONS["device.question"]
    assert a.risk == "read" and a.perm is None and catalog.agent_allowed(a) and not forbidden("device.question")
    with SessionLocal() as s:  # no data at all: a plain sentence, nothing invented
        assert analytics.answer(s, "price_after_launch", None, clock.now().date()).examples == []


def _model(words: list[str]) -> tuple[FunctionModel, list[int]]:
    calls: list[int] = []

    def fn(_m, info: AgentInfo) -> ModelResponse:
        calls.append(1)
        i = min(len(calls), len(words)) - 1
        return ModelResponse(
            parts=[ToolCallPart(info.output_tools[0].name, {"sentence": words[i], "follow_up": "Which partner next?"})]
        )

    return FunctionModel(fn), calls


def test_dv_13_model_sentence_numbers_checked():
    _seed_disputes()
    with SessionLocal() as s:
        ans = analytics.answer(s, "disputes_by_partner", analytics.Scope(frozenset({ORG_A})), clock.now().date())
    good = "P02 and P04 are behind 58% of grading disputes, mostly screens graded before power-on."
    m, calls = _model([good])
    w = analytics.word(ans, m)
    assert (w.sentence, w.by_model, len(calls)) == (good, True, 1)
    # an invented number is refused once, the retry is accepted
    m, calls = _model(["P02 and P04 cause 71% of grading disputes.", good])
    w = analytics.word(ans, m)
    assert (w.sentence, w.by_model, len(calls)) == (good, True, 2)
    # refused twice: the template sentence stands
    m, calls = _model(["71% of disputes.", "72% of disputes."])
    w = analytics.word(ans, m)
    assert (w.sentence, w.by_model) == (ans.sentence, False)
    # no model: the template
    assert analytics.word(ans, None).by_model is False
