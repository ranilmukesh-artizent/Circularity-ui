# PO demo 27 Nov 2026: what broke, and the AI and agents testing plan

Written by the lead during the demo (main stack on `64611e66`, host Vite on :5174). Nothing here is fixed yet unless
it says so. Fix order: section 1 top to bottom, then run section 2 before any further demo.

## 1. Issues seen (screenshots from the user, 16:35 to 16:59)

| # | Where | What the user saw | Root cause (known or suspected) | Fix |
|---|---|---|---|---|
| A1 | Every Ask (dock and Modeler column) | "Answered by the rules, because rate limited"; "the language model is over its rate limit" | **Only one model is configured.** `ASK_MODEL_CHAIN` is empty in the api container, so Ask's chain is `GROQ_MODEL` alone (`di/core/config.py:137-146`). The user asked for fallback models on rate limit; this was never set up. The agents' router (`di/services/llm/router.py`) has the same single seed row `groq-default`. One 429 means no AI anywhere. | Set `ASK_MODEL_CHAIN` (e.g. `groq:openai/gpt-oss-120b,groq:llama-3.3-70b-versatile,groq:<a third model>`) in `.env.example` defaults and compose, and seed matching `llm_model` rows for the roles `ask, agent, stage, author, judge` with priorities, so a 429 moves to the next model. Add a test that a 429 on model 1 answers from model 2. |
| A2 | Ask, rules fallback | "hii" gives "I can't do that yet. I can: hii" | The rule fallback (`di/services/ask/fallback.py` `ask_rule`) has no greeting or small-talk intent and echoes the question as the suggestion list. | Add a greeting/help intent that lists 3 page starters; never echo the question as a suggestion. |
| A3 | Modeler, Ask column | "Which guardrails does this flow keep?" (a starter we ship, `services/ask/starters.py:121`) answered "I can't see any record that describes the guardrails" | The system prompt gave the model no flow: the page sends only `{page: modeler, section: <template>}` and the prompt never named `get_decision_flow` or its arguments. | **Edited, uncommitted, untested**: `services/ask/prompt.py` `modeler_hint()` names the tool and template; `mcp/tools.py` description says the graph carries the GR- ids. Also add a rule-based answer for this starter (it must work without a model). |
| A4 | Modeler, Flow tab, assistant column, Set up | "Could not start the description · no template chosen. Open the Modeler and pick a template and organisation first" while on the Modeler with Industrial returns / Workspace selected | Set up mode reads its template and org only from a `compose` work surface. On the Flow tab the surface is `kind: 'flow'` (`ModelerPage.tsx:222`), so Set up sees no template. From the Set up tab (compose surface) it works: the lead got "Matched: IT asset disposition (100)" there. | Set up mode takes `template`/`org` from a flow surface too (`layout/assistant/modes/SetupMode.tsx`, context in `layout/assistant/context.ts`); unit test both surfaces. |
| A5 | Set up, pack matching | "We take back used laptops and phones from business customers, wipe them, grade them and resell or recycle them" gives "No pack fits. Closest: IT asset disposition (58)" | `config_agent.match_pack` bar is 60; plain everyday wording scores under it. | Lower the bar or add synonyms (laptops, phones, wipe, grade) to the ITAD and device packs; add the sentence above as a test case that must match ITAD or device. |
| A6 | Workflow Studio, Ask | Ask in the side panel only offers rules when rate limited; held proposals fill the panel above the answer | A1, plus the "Waiting for you" list takes most of the panel height. | After A1; cap the waiting list at 2 with "Show all". |
| U1 | Modeler canvas | Right-hand steps (Execute / apply, Outcome learning) hidden behind the inspector | `FlowCanvas.tsx:166` `openZoom={0.8}` keeps zoom at 0.8 even when the flow doesn't fit. | Fit the whole flow on open (min zoom ~0.5), then let people zoom in. |
| S1 | Stack | 502 "Could not reach di-api" for about 3 min after an api restart | The api imports through the Windows bind mount (`di.repositories.cases` alone took 26 s); the lead restarted the api during demo prep. | Never restart the api in the hour before a demo. Look at the prod images (`docker-compose.prod.yml`) for demos. |
| S2 | Stack | :5173 pages take about 30 s under load | Three writer stacks plus test containers on the same machine. | For demos: host Vite (:5174) and pause the other stacks. |

## 2. AI and agents testing plan (run it before every demo, and after any change to Ask, agents or the router)

Goal: prove every AI surface answers from a model, falls back to the next model on a 429, and gives a useful
deterministic answer when no model is left. Run on the main stack after `reset.sh` + `wait-idle.sh`, as `admin` unless
stated.

### 2.1 Model chain and fallback (api, no browser)
1. Configured chain: the api reports at least 2 models for `ask` and 2 for `agent`/`stage` (read `llm.models`).
2. Forced 429: with a test provider, model 1 raises a rate limit; the answer comes from model 2 and the call log names
   model 2. Same for an agent run (`agent` role) and a stage reasoner (`stage`).
3. All models cooling: Ask answers from the rules with a helpful answer (not an echo); an agent run holds for a person
   with "no model available", and nothing is written.
4. Budget reset: `reset.sh` clears `llm_budget` and cooldowns (writer 48's fix); the first Ask after reset uses model 1.
5. Live smoke (real key, one call per model): each configured model answers "What needs me today?" within the timeout.

### 2.2 Ask, per page (browser; every starter that the page shows must give a real answer)
For each page: Home, My work, Modeler (Flow and Set up tabs), Analytics, Connection Fabric, Workflow Studio, a case
(RT-1048), Agents. Click each starter (`GET /api/ask/starters`) and type "hi" and one free question.
Pass when: the answer names the page's real data (ids, numbers present in a tool result), the call log shows the tool
calls, no "I can't see any record" on data the page shows, "hi" gives help text. Record model vs rules for each.
Must include: "Which guardrails does this flow keep?" lists GR-I1..I4 and GR-I5 for Industrial returns.

### 2.3 Prompt to business process (Set up / Compose)
Sentences, each must pick the right pack (or a clear "closest" with a working "Start from ..." button):
- the A5 laptop sentence (ITAD or device);
- "We run IT asset disposition at IT lease end ..." (ITAD, already passes: 100);
- one plain sentence per pack (13 packs), written the way a customer would say it, not with the pack's own words.
Run from both the Set up tab and the Flow tab's assistant column (A4). Then go through Compose's five steps to a draft
and stop before approval (agents never approve).

### 2.4 Change flow (Modeler)
"Exclude returns from Customer C from whole-asset resale" gives a checked, simulated proposal held for a person;
a guardrail-weakening sentence ("skip the guardrail gate") is refused with the blocked card; nothing is published.

### 2.5 Agents
1. Agents page: registry lists each agent with autonomy and model; "View the run" opens a run with tool calls.
2. Case autopilot on a fresh case: proposals appear in My work and Home "Waiting for you" with confidence, threshold,
   evidence; "Accept, runs as you" runs as the person; "Reject" records the reason.
3. Forbidden actions: an agent-prepared approve/override/decline/access change is refused by the pipeline (F4).
4. Rate limited during a run: the run moves to the next model (2.1.2) or holds; never a half-written case.
5. MCP: an outside client with a per-agent credential can read and propose, not approve.

### 2.6 Where the results go
One row per check in `docs/agents/plans/09-run/ai-check-<date>.md`: check, model or rules, pass/fail, screenshot path.
Automate 2.1 as api tests (test provider, no live calls) and 2.2/2.3 as one smoke `frontend/scripts/smoke-ai.mjs`
that runs with `SMOKE_AI_LIVE=1` against the real key and otherwise accepts rule answers but fails on echoes and
"can't see" answers.
