"""POST /api/ask: one question, answered as a stream of Server-Sent Events.

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

The model path: the configured AskModel (di.ask.model.get_model) answers with the read-only tools (di.ask.tools), each
call run through the action pipeline as the signed-in account, so the access policy and the tenant boundary decide
what it may read; a refusal comes back to the model as data and is listed in `refused`. The answer's case ids are
the ones the text names that a successful tool returned; its sources are the source systems those results name;
`next` holds the suggested next steps the server computes for those cases (di.reads.common.next_step: the action and
its input, or the approval card), for the person to press. Nothing in an answer runs an action.

The fallback: when the model is unavailable (no key, ASK_PROVIDER=none, 429, 5xx, timeout, a stream error, an empty
answer, or an error of its own), Ask answers with the demo's rule-based agent (di.ask.fallback): provider "fallback",
with `fallback_reason` and a `notice` that says so, the demo's intent, text, cards and next steps.

Memory: the conversation's last turns (di.ask.memory) are given to the model; the turn is saved after the answer.
The whole request runs in a worker thread (a synchronous generator under StreamingResponse), with its own session.
"""

import json
import logging
import re
import time
from collections.abc import Iterator
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from di import policy
from di.actions.pipeline import Actor, CallContext
from di.ask import memory
from di.ask.fallback import ask_rule
from di.ask.model import AskModel, AskRequest, Done, ModelUnavailable, NoModel, TextDelta, ToolUse, get_model
from di.ask.prompt import system_prompt
from di.ask.tools import Toolbox, log_call
from di.auth import Principal, principal
from di.cases import store
from di.db import SessionLocal
from di.reads.common import next_step

router = APIRouter(tags=["ask"])
log = logging.getLogger("di.ask")
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
}


class AskObject(BaseModel):
    kind: str = Field(..., description="case, kpi, source, workflow, exception or event")
    id: str = Field(..., max_length=64)


class AskContext(BaseModel):
    page: str | None = Field(None, max_length=40)
    section: str | None = Field(None, max_length=40)
    case_id: str | None = Field(None, max_length=16)
    object: AskObject | None = None


class AskBody(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    context: AskContext = Field(default_factory=AskContext)
    conversation_id: str | None = Field(None, max_length=32)


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
        if not c or not policy.tenant_ok(ctx.actor.account, c["owner"], ctx.actor.ctx):
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
            req = AskRequest(question=q, system=system_prompt(account, pctx, page), conversation=memory.messages(turns))
            for ev in model.answer(req, box):
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
            g = grounding(text, used)
            final = {
                "provider": model.name,
                "model": model.model,
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


@router.post("/api/ask")
def ask(body: AskBody, p: Principal = Depends(principal), model: AskModel = Depends(get_model)) -> StreamingResponse:
    """Ask Circularity: the answer streams as Server-Sent Events (see the module docstring for the events)."""
    headers = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    return StreamingResponse(answer_stream(body, p, model), media_type="text/event-stream", headers=headers)
