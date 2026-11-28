# Plan 11: Packaging (28 Nov 2026)

Why: the 27 Nov review with the practice lead. The parts exist; a new customer cannot tell where to start or why each
menu entry is there. This plan changes what people see first, not what the product does.

Goal: a super user signs in, sees Home, Set up and Admin, walks five steps, publishes, and the rest of the menu opens.
Every other role lands on the one page that is theirs.

Branch: `feature/ai-engine` (after the plan-9 merge). Commit and push only when the user asks.

## Rules for this plan

- The demo's 128 cases, RT-1048 and the 11 accounts keep working. Never hand-edit `fixtures/golden/`.
- The demo's menu lives in `fixtures/golden/screens/nav.json`. Renames and regrouping are an overlay in
  `backend/di/services/screens/nav.py` (as `EXTRA_NAV` is today), with a decision-log row. Routes (`#/command`,
  `#/product`, …) do not change, so links, smokes and guides that use routes keep working.
- Hiding is display only. Access stays enforced on the server by `policy.can_page`, unchanged.
- No new settings screens. No new motion on things people do all day.

## Work, in order

### A. Menu (writer A: `nav.py`, `policy.py` reads only, `Sidebar.tsx`, `api/nav.ts`)

| # | Change | Done when |
|---|---|---|
| A1 | Staged menu. `navigation()` takes "this organisation has a published setup" (one query on `compositions`; the demo workspace counts as published). Before publish: Home, Set up, Admin. After: everything the role may open. A line at the foot of the menu: "Decide and Understand open when you publish." | A fresh organisation's admin sees three entries; `admin` on the demo workspace sees the full menu. |
| A2 | Groups and names (overlay): **Decide** (My Tasks, Cases, Exceptions), **Understand** (Pulse, Analytics, Agents), **Advanced**, collapsed by default (Modeler, Connection Fabric with Data Checks inside it, Policies, MCP & Tools). Command Centre shows as Pulse; Decision Workbench as Cases. | The menu reads in those three groups; every old route still opens its page. |
| A3 | One builder. Process Orchestration and Workflow Studio's "Build a workflow with AI" are labelled as data pipelines under Advanced. Set up is the only entry that says it builds a business flow. | No two menu entries or buttons claim to build "the flow". |
| A4 | Landing per role: no published setup and may set up → `#/setup`; planner, warehouse, approver → My Tasks; executive → Pulse; developer → Connection Fabric. | Each of the 11 accounts lands on its page. |

### B. Set up (writer B: `frontend/src/pages/setup/`, `pages/modeler/compose/`)

| # | Change | Done when |
|---|---|---|
| B1 | Five steps on the route line: Business flow, Systems, Agents, Approve, Publish. Template is the first screen of Business flow; Access is a section of Approve. The seven stops stay in the data (`markStep` unchanged). | The line shows five stops; an existing setup opens on the right one. |
| B2 | Published moment. After publish the step shows what opened (Decide, Understand) and one primary button, "Open Pulse". | Publishing ends on that screen, and the menu has grown without a reload. |
| B3 | The mapping rule in words on Systems: "You map and rename canonical fields. A new field is a project with us." | The line is on the step. |
| B4 | Describe step copy: pack names, not keys ("Matched: Tool fleet"); guardrails by their text, not ids. Update the three plan-9 smokes that assert the old text. | No raw key or id on the step. |

### C. AI that does not stall a demo (writer C: `services/modeler/compose.py`, `actions/compose.py`, `TemplateStep.tsx`)

| # | Change | Done when |
|---|---|---|
| C1 | Each pack's sample prompts have their drafts stored with the pack (built once by the model, checked in, marked as such). Clicking a sample prompt uses the stored draft; typing your own text still calls the model. | A sample prompt drafts in about a second with no model call. |
| C2 | A live draft shows its stages as they happen (reading, matching the template, drafting rules, checking) instead of one long wait. | The 40 s wait shows progress the whole time. |
| C3 | When every model is rate-limited, the step says so in one line and offers "Use the template as it is". | No red raw error. |

### D. Analytics per pack (writer C, after C; `services/questions/`, `pages/analytics/`)

| # | Change | Done when |
|---|---|---|
| D1 | Tool fleet and device recommerce open Analytics on five headline numbers (net recovered, sell-through by channel, days to sell, still listed, carbon avoided) and the grade-to-channel chart. | Both packs show them from their own data. |
| D2 | The other packs keep today's Analytics. Not in this plan. | n/a |

### E. Markdown in every assistant answer (writer C first; `components/Markdown*`, `layout/assistant/`)

Today the model's answers show their markdown as raw characters (`**`, `-`, backticks, tables as pipes) on every chat
surface: the dock, the Modeler's pinned column, Set up's assistant, Ask.

| # | Change | Done when |
|---|---|---|
| E1 | One `Markdown` component in `components/`, built on `react-markdown` with `remark-gfm` (tables, task lists, strikethrough, autolinks). It renders React elements, never `innerHTML`; raw HTML in the text is not rendered; links open in a new tab with `rel="noopener noreferrer"` and only `http`, `https` and `mailto` are kept; images are not loaded (shown as a link). | A model answer with a heading, a list, a table, code and a link reads correctly; a `<script>` or `javascript:` link in the text does nothing. |
| E2 | Styled from the brand tokens in one stylesheet: tight spacing for a narrow column, tables scroll sideways inside their own frame, code blocks wrap or scroll and have a copy button, tabular numbers, light and dark. No syntax-highlighting library (answers here are prose, numbers and field names). | Looks right at dock width (about 360 px), in the pinned column, in dark and on a phone. |
| E3 | Safe while text is still arriving: a half-written table, list or code fence never throws or flashes; the component is memoised so a long thread does not re-parse every message on each keystroke. | Unit tests feed truncated markdown at every length of a sample answer without an error. |
| E4 | Used by every surface that shows model text (assistant answers only; what the person typed stays plain text). Rule-based fallback answers go through it too, unchanged in wording. | No chat surface shows raw markdown characters. |

Adds two packages to the frontend (`react-markdown`, `remark-gfm`), pinned to exact versions like the rest.

## Testing: only what catches a real break

| When | What | Time |
|---|---|---|
| Each writer, before handing over | Unit tests for the view logic it wrote (menu filter, five-step mapping, landing route), the typecheck, and the api tests of the files it touched (`test_mywork_nav.py`, `test_screens_reference.py`, `test_composition.py`), through `api-test.sh`. | minutes |
| Lead, after each merge | One headless pass with screenshots: three accounts (`admin` on a fresh organisation, `planner.a`, `approver`), light and dark, one phone width. Look at the pictures. | ~10 min |
| Once, at the end | `web-check.sh`; `smoke-pages.mjs` (11 accounts, proves no page was lost by the menu change); `smoke-p9-8.mjs` (Set up end to end); `test_ns_ind_parity.py` (parity). | ~30 min |

Not run: the full api suite, the parallel suite, the other ten plan-9 smokes, fresh-clone and trial checks. Nothing here
touches the engine, the connectors or the migrations. If a change does reach shared code, run that area's tests, not
everything.

## Split and order

- Wave 1, together, on disjoint files in the one working tree: writer A (menu), writer B (Set up), writer C (E, markdown).
- Wave 2, after the lead has reviewed wave 1: C1 to C3 (they touch `TemplateStep.tsx`, which writer B owns in wave 1),
  then D.
- Writers are Sonnet agents; they do not commit. Each leaves a report in `docs/agents/plans/11-work/<letter>.md`. The
  lead reads each diff, reruns its tests and does the screenshot pass.
- For Monday: A1 to A4, B2 and E. The rest follows.

## Decisions the owner must make

1. A paid model key for the application (C1 to C3 lower the risk; they do not remove it).
2. Whether "Pulse" and "Cases" are the names to ship (they follow the practice lead's prototype).
3. An end date for the MVP.

## Out of scope

Removing the Modeler or guardrail screens (they move under Advanced). Customer-added canonical fields. Matching the
prototype's visual style. Headline analytics for the other eleven packs.
