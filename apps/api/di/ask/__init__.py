"""Ask Circularity on a language model (docs/BACKEND_STEPS.md, B16b): the product's assistant panel answered by di-api.

    POST /api/ask   a question with its page context; the answer streams as Server-Sent Events (di.ask.service)

Design:
    model.py       the AskModel interface (one method: answer(request, tools) streams text, tool calls and the final
                   text) and the provider switch: ASK_PROVIDER=groq|none, GROQ_API_KEY, GROQ_MODEL (di.config). Claude
                   or a local model is another class with the same method; nothing else changes, the frontend included.
    groq_model.py  the first provider: Groq's chat completions through the official `groq` SDK, streamed, with tool
                   calling; default model openai/gpt-oss-120b (the account's models list: tool calling, free tier)
    tools.py       the read-only tools a model may call: the six B16 MCP read tools and six read actions, each run
                   through the action pipeline as the signed-in account (preparer "ask"), each logged in the MCP call log
    prompt.py      the system prompt: the answering rules, the signed-in user and the page
    fallback.py    the demo's rule-based Ask (intent router and the runners the starters and data checks use), for
                   when no model answers; intents.py holds the router, with the demo's own catalog
    memory.py      the conversation's last turns, per account
    service.py     the endpoint: model first, fallback on any failure, the answer's case ids, sources, next steps

Safety, in code rather than in the prompt alone:
- **Grounded:** the model sees data only through tool results; the answer's case ids and asset ids are kept only when
  a successful tool returned them, and its sources are the systems those results name.
- **Tenant boundary and access policy:** every tool runs as the signed-in person through di.actions.pipeline.invoke,
  so a Customer B planner asking about RT-1048 (Customer A) gets the pipeline's tenant_boundary refusal, which the
  model is given as data and the answer lists under `refused`; nothing about the case reaches the model.
- **Read-only:** the tool table holds read tools and read actions only (asserted at import, and against the MCP
  layer's forbidden actions); the fallback never invokes an action that is not a read (a draft is recorded as
  skipped, as the demo's own eval mode does). Ask can point to an action (a suggested next step, a plan card, the
  approval card) but cannot perform it: the person presses the button, through POST /api/actions/{id}.
- **Record text is data (hard rule 6):** tool results go back to the model as `tool` messages, never as instructions,
  and the prompt says so; since no write tool exists, text like "approve RT-1048 now" in a record cannot cause a
  write whatever the model makes of it. The fallback never reads free text from records at all.
- **The key:** GROQ_API_KEY lives in the repository's local .env only, reaches the SDK only, and is never logged or
  returned.

Fallback: no key, ASK_PROVIDER=none, Groq's 429 or 5xx, a timeout, a stream error or an empty answer -> the rule-based
answer, marked provider "fallback" with the reason and a notice that says so.
"""
