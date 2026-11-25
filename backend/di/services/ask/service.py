"""POST /api/ask: one question, answered as a stream of Server-Sent Events (the endpoint is di.routes.ask, the body
di.schemas.ask; this module makes the answer).

    POST /api/ask   (signed in: Authorization: Bearer <JWT>)
        body    {question, context?: {page?, section?, case_id?, object?: {kind, id}}, conversation_id?}
        stream  text/event-stream, each event `event: <type>` with JSON data carrying the same `type`:
            start   {conversation_id, provider, model}                      the provider that will try first
            tool    {name, args, ok, code, message}                         each tool or action call, as it is made
            delta   {text}                                                  answer text as it arrives
            reset   {reason}                                                the model failed after it started; the
                                                                            text so far is void, the fallback follows
            final   {provider: "groq" | "fallback", model, fallback_reason, notice, text, case_ids, asset_ids,
                     sources, tools, refused, next, intent, result, cards, conversation_id}

The model path: the configured AskModel (di.services.ask.model.get_model) answers with the read-only tools
(di.services.ask.tools), each call run through the action pipeline as the signed-in account, so the access policy
and the tenant boundary decide what it may read; a refusal comes back to the model as data and is listed in
`refused`. The answer's case ids are the ones the text names that a successful tool returned; its sources are the
source systems those results name; `next` holds the suggested next steps the server computes for those cases
(di.repositories.common.next_step: the action and its input, or the approval card), for the person to press.
Nothing in an answer runs an action.

The fallback: when the model is unavailable (no key, ASK_PROVIDER=none, 429, 5xx, timeout, a stream error, an empty
answer, or an error of its own), Ask answers with the demo's rule-based agent (di.services.ask.fallback): provider "fallback",
with `fallback_reason` and a `notice` that says so, the demo's intent, text, cards and next steps.

Memory: the conversation's last turns (di.services.ask.memory) are given to the model; the turn is saved after the answer.
The whole request runs in a worker thread (a synchronous generator under StreamingResponse), with its own session.
"""

import json
import logging
import re
import time
from collections.abc import Iterator
from typing import Any, cast

from di.core import policy
from di.core.auth import Principal
from di.core.db import SessionLocal
from di.repositories.common import next_step
from di.repositories.context import can_see_case
from di.schemas.ask import AskBody
from di.services.actions.pipeline import Actor, CallContext
from di.services.ask import memory
from di.services.ask.checked_answer import answer_checked
from di.services.ask.fallback import ask_rule, rules_first
from di.services.ask.model import AskModel, AskRequest, Done, ModelUnavailable, NoModel, TextDelta, ToolUse
from di.services.ask.prompt import system_prompt
from di.services.ask.tools import Toolbox, log_call
from di.services.cases import store

log = logging.getLogger("di.services.ask")
CASE_RX = re.compile(r"\bRT-\d{4}\b")
ASSET_RX = re.compile(r"\b(?:MTR|PMP|CTL|DRL|BAT|ITE)-\d{4}\b")
KINDS = ("case", "kpi", "source", "workflow", "exception", "event")
WHY = {
    "no_key": "no language-model key is configured",
    "disabled": "the language model is switched off (ASK_PROVIDER=none)",
    "unknown_provider": "the configured provider is not known",
    "rate_limited": "the language model is over its rate limit",
    "timeout": "the language model did not answer in time",
    "unavailable": "the language model is unavailable",
    "model_error": "the language model could not answer",
    "error": "the language model answer failed",
    "unchecked": "the language model's answer about a workflow did not match what the workflow's run shows",
    "rules_first": "workflow drafts come from the workflow builder, which uses the real palette and checks every step",
}


def sse(kind: str, data: dict) -> str:
    return (
        f"event: {kind}\ndata: {json.dumps({'type': kind, **data}, ensure_ascii=False, separators=(',', ':'), default=str)}\n\n"
    )


def tidy(s: str) -> str:
    """Model text with plain hyphens: models often write ids with a non-breaking hyphen (RT‑1048), which reads the
    same but matches nothing."""
    return s.replace("‑", "-").replace("‐", "-")


def page_of(body: AskBody, account: policy.Account) -> dict:
    c = body.context
    obj = c.object.model_dump() if c.object and c.object.kind in KINDS else None
    if obj is None and c.case_id:
        obj = {"kind": "case", "id": c.case_id}
    return {"page": c.page or "home", "section": c.section or "", "role": account.role, "object": obj}


def _walk(v: Any, keys: tuple[str, ...], out: list) -> None:
    if isinstance(v, dict):
        for k, x in v.items():
            if k in keys and isinstance(x, str) and x and x not in out:
                out.append(x)
            else:
                _walk(x, keys, out)
    elif isinstance(v, list):
        for x in v:
            _walk(x, keys, out)


def grounding(text: str, results: list[tuple[dict, Any]]) -> dict:
    """The case ids, asset ids and source systems an answer used: ids the text names that a successful call returned
    (or was called for), and the source systems those calls' results name."""
    seen = json.dumps([[a, d] for a, d in results], default=str)
    called = [a["case_id"] for a, _ in results if isinstance(a.get("case_id"), str)]
    cases = list(dict.fromkeys([*[c for c in CASE_RX.findall(text) if c in seen], *[c for c in called if c in text]]))
    assets = list(dict.fromkeys(a for a in ASSET_RX.findall(text) if a in seen))
    sources: list[str] = []
    for _, d in results:
        _walk(d, ("source", "system"), sources)
    return {"case_ids": cases, "asset_ids": assets, "sources": sources[:12]}


def suggestions(ctx: CallContext, case_ids: list[str]) -> list[dict]:
    """Next steps for the cases an answer used, for the person to press (Ask never runs them)."""
    out = []
    for cid in case_ids[:3]:
        c = store.get(ctx.session, cid)
        if not c or not can_see_case(cast(policy.Account, ctx.actor.account), ctx.actor.ctx, c):  # Ask runs signed in
            continue
        st = next_step(c, ctx)
        if st["kind"] == "act":
            out.append({"label": st["label"], "action": st["action"], "input": st["input"], "case_id": cid})
        elif st["kind"] == "approve":
            out.append({"label": f"Open the approval card for {cid}", "approve": cid, "case_id": cid})
    return out


def answer_stream(body: AskBody, p: Principal, model: AskModel) -> Iterator[str]:
    account, pctx = p.account, p.ctx
    q = body.question.strip()
    with SessionLocal() as s:
        conv, turns = memory.load(s, account.id, body.conversation_id)
        page = page_of(body, account)
        ctx = CallContext(actor=Actor(account=account, ctx=pctx), session=s)
        first = "fallback" if isinstance(model, NoModel) else model.name
        yield sse("start", {"conversation_id": conv, "provider": first, "model": model.model or None})

        box = Toolbox(session=s, account=account, pctx=pctx)
        text, reason, streamed = None, None, False
        try:
            if rules_first(q, ctx, page):
                raise ModelUnavailable("rules_first", "answered by the rules")
            req = AskRequest(question=q, system=system_prompt(account, pctx, page), conversation=memory.messages(turns))
            for ev in answer_checked(model, req, box):  # an answer about a workflow is checked first (P9-2.23)
                if isinstance(ev, TextDelta):
                    streamed = True
                    yield sse("delta", {"text": tidy(ev.text)})
                elif isinstance(ev, ToolUse):
                    u = box.used[-1] if box.used else None
                    yield sse(
                        "tool",
                        {
                            "name": ev.name,
                            "args": u.args if u else ev.arguments,
                            "ok": bool(ev.result.get("ok")),
                            "code": u.code if u else None,
                            "message": u.message if u else None,
                        },
                    )
                elif isinstance(ev, Done):
                    text = tidy(ev.text)
            if not (text or "").strip():
                raise ModelUnavailable("model_error", "empty answer")
        except ModelUnavailable as e:
            reason = e.reason
        except Exception:  # a provider bug must not leave the person without an answer
            log.exception("Ask: the model path failed; answering with the fallback")
            s.rollback()
            reason = "error"

        if reason is None:
            used = [(u.args, u.data) for u in box.used if u.ok]
            g = grounding(text or "", used)  # text is set here: an empty answer raised above
            final = {
                "provider": model.name,
                "model": model.model,
                "by_model": True,
                "fallback_reason": None,
                "notice": None,
                "text": text,
                **g,
                "tools": [{"name": u.name, "args": u.args, "ok": u.ok, "code": u.code} for u in box.used],
                "refused": [{"tool": u.name, "code": u.code, "message": u.message} for u in box.used if not u.ok],
                "next": suggestions(ctx, g["case_ids"]),
                "intent": None,
                "result": "ok",
                "cards": [],
            }
        else:
            if streamed:
                yield sse("reset", {"reason": reason})
            t0 = time.monotonic()
            rule = ask_rule(q, ctx, page)
            for c in rule["calls"]:
                if not c["skipped"]:
                    log_call(s, account, c["action"], c["input"], round((time.monotonic() - t0) * 1000), c["code"])
                yield sse(
                    "tool",
                    {
                        "name": c["action"],
                        "args": c["input"],
                        "ok": c["ok"],
                        "code": c["code"],
                        "message": c["message"],
                        "skipped": c["skipped"],
                    },
                )
            yield sse("delta", {"text": rule["text"]})
            used = [(c["input"], c["output"]) for c in rule["calls"] if c["ok"] and not c["skipped"]]
            g = grounding(rule["text"] + " " + json.dumps(rule["cards"], default=str), used)
            final = {
                "provider": "fallback",
                "model": None,
                "by_model": False,
                "fallback_reason": reason,
                "notice": f"Answered by Circularity's rule-based assistant, because {WHY.get(reason, reason)}.",
                "text": rule["text"],
                **g,
                "tools": [{"name": c["action"], "args": c["input"], "ok": c["ok"], "code": c["code"]} for c in rule["calls"]],
                "refused": [
                    {"tool": c["action"], "code": c["code"], "message": c["message"]} for c in rule["calls"] if not c["ok"]
                ]
                or [
                    {"tool": None, "code": x["data"]["code"], "message": x["data"].get("what")}
                    for x in rule["cards"]
                    if x["type"] == "cantdo" and x["data"].get("code")
                ],
                "next": rule["next"],
                "intent": rule["intent"],
                "result": rule["result"],
                "cards": rule["cards"],
            }
        conv = memory.save(s, account.id, conv, turns, q, final["text"], final["provider"])
        s.commit()
        yield sse("final", {**final, "conversation_id": conv})
