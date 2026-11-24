# V. Verification of claims (round 1: 24 Nov 2026, reports A–G; round 2: 25 Nov 2026, revision 2 and reports H, I, now parked)

What changed in this revision and why:
- Resolve and Reconcile removed (parked as out of scope, user decision 25 Nov 2026). Round 2 keeps the facts checked
  for them, marked "(claim from a parked report)".

A fact-check of 21 claims from the reports in this folder: 15 web claims against primary sources (licence files,
package registries, official docs, vendor releases, security advisories) and 6 code claims read from the repository
(nothing was run). Web searches named no company, product or people of ours.

**Licence findings need review by Kinective's Legal team before anyone relies on them.** This note reads public
licence files and pages. It is not legal advice.

## Summary

| Verdict | Count | Claims |
|---|---|---|
| Confirmed | 16 | 1, 2, 3, 4, 5, 6, 7, 9, 10, 14, 15, 16, 18, 19, 20, 21 |
| Corrected | 5 | 8, 11, 12, 13, 17 |
| Unconfirmed | 0 | none |
| False | 0 | none |

No claim was invented. Five were wrong in a detail. Reports C, E, F and G were edited where they repeated a wrong
detail, with the marker "(corrected in verification, see V-verification.md)". `README.md` (the synthesis) was not
edited (out of scope). Its Durability row still says DBOS is "Postgres-only" (claim 11) and should be fixed the same
way.

## Web claims

| # | Claim | Verdict | Evidence (read 24 Nov 2026) | Corrected text / note |
|---|---|---|---|---|
| 1 | Camunda 8 Self-Managed production needs a paid licence from 8.6 (Camunda License 1.0); Camunda 7 CE ended with 7.24 in Oct 2025 | Confirmed | Camunda docs, Licenses (8.10 docs): Zeebe, Operate, Tasklist, Identity, Optimize source under "Camunda License v1"; "To use the software in production, purchase the Camunda Self-Managed Enterprise Edition"; applies to "version 8.6 and higher". https://docs.camunda.io/docs/reference/licenses/ . Camunda forum "Camunda Automation Platform 7.24 released" and the 7 CE end-of-life announcement: 7.24 (Oct 2025) is the last CE release, with no further releases including security patches. https://forum.camunda.io/t/camunda-automation-platform-7-24-released/65415 , https://forum.camunda.io/t/important-update-camunda-7-community-edition-end-of-life-announced/50921 | The licence's official name is "Camunda License v1". Sources differ on the exact 7.24 day (7 or 14 Oct 2025). |
| 2 | Camunda 8.10 has an agent-instance monitoring view (model calls, tokens, tools against limits); release date | Confirmed | Docs "Monitor AI agents" (version 8.10): "token consumption, tool call count, and model call count against the configured limit"; needs "Operate on Camunda 8.10 or later". https://docs.camunda.io/docs/components/agentic-orchestration/monitor-ai-agents/ . 8.10 announcements: minor release **13 October 2026**, end of standard maintenance 11 April 2028. https://docs.camunda.io/docs/reference/announcements-release-notes/8100/8100-announcements/ | Release date 13 Oct 2026. This answers the open question in C §open questions ("Exact GA date of Camunda 8.10"). |
| 3 | GoRules ZEN is MIT; Python package 2.1.8 ~20 Nov 2026; JDM editor MIT | Confirmed | PyPI `zen-engine`: 2.1.8 released 20 Nov 2026, MIT. https://pypi.org/project/zen-engine/ . github.com/gorules/zen: MIT. github.com/gorules/jdm-editor: "MIT © GoRules" (no releases listed on GitHub). | none |
| 4 | Unleash moved to AGPLv3 from v8 (June 2026) | Confirmed | Unleash blog, 2 Jun 2026: source moves from Apache-2.0 to AGPLv3 from v8.0.0; official Docker images stay Apache-2.0 if unmodified; SDKs keep their licences. https://www.getunleash.io/blog/unleash-moving-to-agplv3 . LICENSE file = GNU AGPL v3. https://github.com/Unleash/unleash/blob/main/LICENSE | none |
| 5 | Oso's open-source library was deprecated in Dec 2023 | Confirmed | Oso notice "Deprecating the Oso Open Source Library", dated 18 Dec 2023 (shown on the PyPI, crates and npm listings of `oso` 0.27.x). https://pypi.org/project/oso/0.27.1 . **Newer:** github.com/osohq/oso now says "no longer maintained", and the repository "was archived by the owner on Oct 22, 2026". https://github.com/osohq/oso | E said the vendor "promises only critical fixes". That is out of date: the repo was archived on 22 Oct 2026. E was corrected. |
| 6 | PyAirbyte and Soda Core are under Elastic License 2.0 | Confirmed | PyAirbyte `LICENSE.md`: "Elastic License 2.0 (ELv2)". https://raw.githubusercontent.com/airbytehq/PyAirbyte/main/LICENSE.md (PyPI `airbyte` 0.71.3, 26 Oct 2026; 1.0.0rc45 pre-release 13 Nov 2026). Soda Core `LICENSE`: "Elastic License 2.0". https://github.com/sodadata/soda-core/blob/main/LICENSE | D gives no date for PyAirbyte 0.71.3. It is 26 Oct 2026. |
| 7 | n8n Sustainable Use License; Windmill AGPL; Activepieces core MIT | Confirmed | n8n `LICENSE.md`: Sustainable Use License 1.0, plus the n8n Enterprise License for `.ee.` files. https://raw.githubusercontent.com/n8n-io/n8n/master/LICENSE.md . Windmill `LICENSE`: backend and frontend AGPLv3, enterprise snippets proprietary, clients and OpenFlow spec Apache-2.0. https://raw.githubusercontent.com/windmill-labs/windmill/main/LICENSE . Activepieces `LICENSE`: MIT Expat outside `packages/ee/`, which has its own licence. https://raw.githubusercontent.com/activepieces/activepieces/main/LICENSE | Windmill's licence also says that redistributing or reselling, or re-exposing Windmill to your own users, needs a commercial licence. That makes the D verdict "avoid embedding" stronger. |
| 8 | `@xyflow/react` is MIT at v13; elkjs EPL-2.0; dagre MIT | Corrected | npm registry: `@xyflow/react` 13.0.3, MIT; `elkjs` 0.12.1, licence **"EPL-2.0 OR GPL-3.0-or-later"**; `@dagrejs/dagre` 3.1.3, MIT. https://registry.npmjs.org/@xyflow/react/latest , https://registry.npmjs.org/elkjs/latest , https://registry.npmjs.org/@dagrejs/dagre/latest | elkjs is dual-licensed EPL-2.0 OR GPL-3.0-or-later, not EPL-2.0 alone. Report D already says this, so it was not edited. |
| 9 | Pydantic AI 2.73.0 (MIT), 24 Nov 2026, with an "external call" deferred kind distinct from approval; LangGraph 1.2.24 | Confirmed | PyPI `pydantic-ai`: 2.73.0 on 24 Nov 2026, MIT (2.72.0 not listed). https://pypi.org/project/pydantic-ai/ . Deferred tools docs: approvals (`requires_approval=True` / `ApprovalRequired`) land in `DeferredToolRequests.approvals`; external calls (`CallDeferred`, `ExternalToolset`) land in `.calls`; `kind()` returns `'approval'`, `'external'` or `'question'`. https://pydantic.dev/docs/ai/tools-toolsets/deferred-tools/ . PyPI `langgraph`: 1.2.24 on 20 Nov 2026, MIT. https://pypi.org/project/langgraph/ | There is also a third kind: `CallDeferred(kind='question')`. |
| 10 | LiteLLM's PyPI releases were compromised twice in 2026 (March and October) | Confirmed | March: GHSA-5mg7-485q-xm76 / PYSEC-2026-2 / MAL-2026-2144, "Two litellm versions published containing credential harvesting malware", 1.82.7 and 1.82.8, published 24–25 Mar 2026. https://osv.dev/vulnerability/PYSEC-2026-2 , https://advisories.gitlab.com/pypi/litellm/GHSA-5mg7-485q-xm76/ ; Snyk, 24 Mar 2026 (PyPI token stolen through a compromised Trivy action in CI). October: 1.107.0 wheels and Docker images (including `latest`) on 21 Oct 2026, a credential stealer through `.pth` / `sitecustomize` startup hooks. Mend, 21 Oct 2026: https://mend.io/blog/litellm-1-107-0-compromised ; also The Register and StepSecurity on 21 Oct 2026. | I did not open a GHSA record of my own for the October incident. Search snippets say OSV lists 1.107.0 as malicious. |
| 11 | DBOS Transact Python is MIT and Postgres-only; Restate is BSL; Inngest is SSPL | Corrected | DBOS repo: MIT. https://github.com/dbos-inc/dbos-transact-py . DBOS configuration docs: the system database "may be either Postgres or SQLite, though Postgres is recommended for production"; "If no connection string is provided, DBOS uses a SQLite database." https://docs.dbos.dev/python/reference/configuration . Restate `LICENSE`: BSL 1.1, no "Public Restate Platform Service", Change License Apache-2.0 four years after release. https://raw.githubusercontent.com/restatedev/restate/main/LICENSE . Inngest README: server and CLI under SSPL with delayed Apache-2.0 publication; SDKs Apache-2.0. https://github.com/inngest/inngest | **DBOS is not Postgres-only.** It supports Postgres or SQLite, with SQLite as the default and Postgres recommended for production. Corrected in F (TL;DR, table row, trigger table, source S17). For us it still runs on our Postgres, so the recommendation does not change. |
| 12 | Langfuse v3 self-hosting needs ClickHouse, Redis and S3-compatible storage | Corrected | Langfuse self-hosting page (labelled "Version: v4"): PostgreSQL, Redis/Valkey, ClickHouse, S3/blob storage. https://langfuse.com/self-hosting . Latest release v4.85.0 ("24 Nov"). https://github.com/langfuse/langfuse/releases | The current major version is **v4**, not v3. It needs Postgres, Redis/Valkey, ClickHouse and S3/blob storage. Report F already says v4.85.0 and lists these, so it was not edited. |
| 13 | Blue Yonder acquired Optoro in 2025; Blue Yonder ships returns test-and-grade and disposition simulation (Aug 2026) | Corrected | Optoro: Blue Yonder release on Business Wire, 18 Aug 2025; closing on 19 Aug 2025 per Digital Commerce 360 and MergerLinks. https://www.businesswire.com/news/home/20250818415001/en/ . Aug 2026: Business Wire release 26 Aug 2026, "Blue Yonder's New Agentic AI Tackles Retail's Costliest Problems: Stockouts and Returns". https://secure.businesswire.com/news/home/20260826662159/en/ ; IT Brief Australia, 27 Aug 2026: Blue Yonder "introduced" features including "test-and-grade workflows and unit-level simulation of disposition outcomes"; no availability date given. https://itbrief.com.au/story/blue-yonder-adds-ai-retail-tools-for-returns-stock | The acquisition is confirmed. The Aug 2026 features were **announced** on 26 Aug 2026. No source read says they are generally available. C said "shipped" and was corrected to "announced". |
| 14 | dlt is Apache-2.0 and has a declarative `rest_api` source | Confirmed | github.com/dlt-hub/dlt: "dlt is released under the Apache 2.0 License". `rest_api` docs: a dict config with `client`, `resource_defaults`, `resources`; paginators json_link, header_link, header_cursor, offset, page_number, cursor, single_page, auto; auth bearer, http_basic, api_key, oauth2_client_credentials. https://dlthub.com/docs/dlt-ecosystem/verified-sources/rest_api/basic | Not re-checked: the dlt 1.32.0 release date (29 Oct 2026). |
| 15 | Open Workflow Spec 1.1 is the renamed CNCF Serverless Workflow; Arazzo 1.1 exists | Confirmed | serverlessworkflow/specification releases: v1.1.0 "Latest", 12 Nov, includes "Rename to Open Workflow Specification (#1155)". https://github.com/serverlessworkflow/specification/releases . OAI/Arazzo-Specification releases: 1.1.0 (18 May; AsyncAPI v3, JSONPath/XPath, `$self`, `querystring`), 1.0.1 (20 Jan), 1.0.0 (25 Sep). https://github.com/OAI/Arazzo-Specification/releases | The GitHub pages show no years. The years in D are consistent with the release order. |

## Code claims (read, not run)

| # | Claim | Verdict | Evidence | Corrected text / note |
|---|---|---|---|---|
| 16 | 131 actions, 79 `agent_allowed`, 12 without a handler | Confirmed | 76 actions in `fixtures/golden/actions_catalog.json`, loaded by `backend/di/services/actions/registry.py:69-87`. Plus 55 `ACTIONS.setdefault` declarations: access 3 (`access.py:200-214`), agent 3 (`agents.py:51,56,63`), case.open 1 (`cases_intake.py:20`), source 5 and mapping 3 (`fabric_sources.py:85-102,579,892,897`), flow 11 (`modeler.py:68-95`) plus `flow.suggestions` (`modeler_suggest.py:32`), model 4 (`models.py:39-92`), org 9 (`org_pack.py`, `org_pilot.py`, `orgs.py`), proposal 2 (`proposals.py:19,26`), workflow 9 (`workflow_builder.py:77`, `workflow_drafts.py:57,59,119`, `workflows.py:108-111,1276`), task 4 (`services/tasks.py:40-48`). That makes 131. `agent_allowed` = `risk != "system" and not forbidden` (`services/agents/catalog.py:40-41`). Forbidden prefixes (`services/agents/forbidden.py:10-20`) cover 28 golden and 24 code-declared actions; the only `system` action (`adapter.acknowledge`) is already forbidden. So 52 are forbidden and **79 allowed**. Comparing every `@implement(...)` with the 131 ids leaves **12 without a handler**: analytics.query, audit.search, sources.health, sources.diagnose, mapping.suggest, mapping.apply, tables.suggestLinks, tables.describe, conflict.suggest, import.clean, event.explain, asset.summary. They answer 501 at `services/actions/pipeline.py:223`. | none |
| 17 | `credentials.rotate` is agent_allowed while other connection-changing actions are not | Corrected | `credentials.rotate` is not under the `source.` prefix, so it is allowed (`actions_catalog.json:597`, risk commit, handler `fabric_sources.py:692`). `source.update/pause/resume/reconnect/disconnect/delete/sync` are forbidden by `"source."` (`forbidden.py:12`). But `mapping.revert` ("Save a new version of a source's field mapping...", act, `fabric_sources.py:897-901`, handler L970) and `tables.update` ("Add, edit or delete a table... in a source table model", act, `actions_catalog.json:726-760`, handler `fabric_records.py:151`) are also agent-allowed. | `credentials.rotate` is the only agent-allowed action that changes a connection's own settings or secret. Two other source-configuration changes, `mapping.revert` and `tables.update`, are agent-allowed too. G §2.8 corrected. |
| 18 | The MCP server has 12 hand-written tools | Confirmed | `backend/di/mcp/tools.py:38-51` (`MODELER_TOOLS`: 2) + `TOOLS_BY_ID` (10 tool ids in `fixtures/golden/tools.json:233-404`) → `TOOLS` (L51); `ACTIONS_OF` has 12 rows (L56-69); `mcp/server.py:57` lists `TOOLS.values()` | none |
| 19 | Tool-fleet and device cases show carbon 0; only the industrial template computes carbon per route | Confirmed | `co2 = EMB.get(cls) or 0 × qty × CO2S` (`repositories/common.py:342`). `EMB` holds only motor, pump, control, drill, batch, it (`common.py:166`). Tool-fleet classes are codes such as CMH, CRH, BRK, DCD, LSR (`modeler/valuers/tool_fleet.py:176,974-976`), and device cases get `cls: "device"` (`services/cases/intake.py:218`), so both give 0. The valuers have no carbon term (no `co2`/`carbon` in `services/modeler/`). The frontend fills `co2: 0` when there is no ranking row (`frontend/src/pages/case/tabs/DecideTabs.tsx:38`). | none |
| 20 | `device.py` defines a 55% recovery floor that is never used | Confirmed | `DG = {..., "floor": 0.55}` (`modeler/valuers/device.py:132-134`). No read of `DG["floor"]` anywhere in `backend/` (the reads of DG are `retc`, `ero`, `hold`, `pen`, `sla`: `device.py:194-271`). GR-D2 is only a text pattern (`modeler/templates.py:126`). | none |
| 21 | Ask uses one Groq model with no model fallback | Confirmed | `DEFAULT_GROQ_MODEL = "openai/gpt-oss-120b"`, one `GROQ_MODEL` override, `ask_provider` ∈ groq/none/off/fallback (`core/config.py:9,55,57`). `get_model()` returns one `GroqModel` or a `NoModel` (`services/ask/model.py:86-104`). The fallback is the rule-based answerer (`services/ask/service.py:23`, `fallback.py`), not another model. | One model and one provider. On failure it falls back to rules, never to another model. |

## Edits made to the reports

- **C**, "Evidence that the window is closing": Blue Yonder "shipped" changed to "announced ... on 26 Aug 2026 (press
  release; general availability not stated)".
- **E**, Oso row: "promises only critical fixes" replaced by "the repository was archived on 22 Oct 2026 and the
  README says the library is no longer maintained".
- **F**, TL;DR, the durable-execution table, the trigger table and source S17: DBOS "Postgres-only" changed to
  "Postgres or SQLite system database (SQLite default, Postgres recommended for production)".
- **G** §2.8, "Inconsistencies to fix": added that `mapping.revert` and `tables.update` are agent-allowed as well.

Not edited, because the reports were already right: D (elkjs dual licence, Langfuse not mentioned), F (Langfuse v4).
Report C's open question on the Camunda 8.10 GA date is answered above (13 Oct 2026).

---

## Round 2 (25 Nov 2026): revision 2 and reports H, I (reports H, I now parked)

Two checkers ran in parallel after revision 2 aligned every report with the Recover concept ([01](01-recover-segments.md)):
- one read the code (nothing was run);
- one checked web claims against primary sources (licence files, PyPI metadata, regulation texts, vendor releases),
  with no company, product or people names of ours in searches.

The lead then re-read the key code evidence (`intake.py:233–239`, `discover.py:31`, `forbidden.py`) and the edits.
**Licence and regulatory findings need review by Kinective's Legal team before anyone relies on them.**

### Summary

| Checked | Confirmed | Corrected | Unconfirmed |
|---|---|---|---|
| 23 web claims | 22 (3 with a detail added or a wording fix: alibi-detect date, "sell, lease, or rent", NIST Rev. 2 scope) | 1 (Timefold; claim from a parked report) | 3 details: the Timefold 1.25.0 note (search snippet only) (claim from a parked report), PTC's "Spring 2026 agentic" item (claim from a parked report), the full Gartner Leader list |
| 11 code claims | 6 | 5 | 0 |
| 36 spot-checked file:line citations | 33 | 3 | 0 |

No claim was false or invented.

### Web claims (licences, regulation, competitors)

Confirmed against the source named:

| Area | Claim | Source |
|---|---|---|
| Licences | scikit-survival GPL-3.0-or-later, lifelines MIT | PyPI metadata |
| Licences | statsforecast, OR-Tools, scim2-models, scim2-tester, Evidently: Apache-2.0 | PyPI metadata |
| Licences | Authlib and jsonpatch BSD-3; factur-x BSD | PyPI metadata |
| Licences | highspy, deepdiff, pydifact, pdfplumber, RapidFuzz, invoice2data 1.0.1 (1 Aug 2026): MIT | PyPI metadata |
| Licences | PuLP is MIT: its LICENSE file is MIT text; old PyPI classifiers said BSD (claim from a parked report) | LICENSE file |
| Licences | pm4py AGPL-3.0-or-later; PyMuPDF AGPL or commercial; python-mip EPL-2.0 | PyPI metadata |
| Licences | Zitadel AGPL-3.0 since v3 | vendor's blog |
| Licences | alibi-detect on BSL 1.1 since 22 Jan 2024; earlier releases stay Apache-2.0 (date added to E) | vendor's licensing FAQ |
| Regulation | Reg. (EU) 2026/1738 is the new End-of-Life Vehicles Regulation (OJ 24 Jul 2026) | EUR-Lex |
| Regulation | US federal law bars rental fleets of 35+ vehicles from renting, leasing or selling vehicles with open recalls; there is no federal bar on dealers retailing used cars with open recalls | 49 U.S.C. 30102(a)(11), 30120(i) |
| Regulation | NIST SP 800-88 Rev. 2 is final (26 Sep 2025) and supersedes Rev. 1 | NIST |
| Regulation | EU battery passport from 18 Feb 2027, a date the Commission calls indicative | European Commission |
| Competitors | ACV MAX Recommendations, 19 Mar 2026 | release |
| Competitors | TRIMEDX-AIQ agentic capabilities, 21 May 2026 | release |
| Competitors | Gartner's first Magic Quadrant for Decision Intelligence Platforms, 26 Jan 2026 | secondary sources; the Gartner page was not reachable |
| Competitors | Aera's prompt-built decision automations, announced 27–28 Oct 2026 | release |
| Competitors | Loop freight-audit agents, 4 May 2026 (claim from a parked report) | release |
| Competitors | Basware AP agents, 24 Feb 2026; its Supplier Agent is planned, not live (claim from a parked report) | release |
| Competitors | PTC service-lifecycle AI, Sep–Oct 2025 (claim from a parked report) | release |
| Competitors | IFS Loops Agent Studio, 23 Apr 2026 (claim from a parked report) | release |
| Names | No customer or prospect names in any report: every company named is a competitor, OSS project, regulator or academic author | local scan |

Corrected:
- **H:** the Timefold Python solver is not "reportedly discontinued". Solver 1.25.0 (12 Aug 2025) dropped Python, and
  the Python repository was archived on 6 Nov 2026. (claim from a parked report)
- **B:**
  - The statute says "sell, lease, or rent", not "loan".
  - NIST Rev. 2 removed the media-specific appendices, including routers and switches, and points to IEEE 2883.
    B's open question on network devices is resolved.

### Code claims

Confirmed:
- `plan_queue` is a heuristic in `services/modeler/valuers/tool_fleet.py:684`, not in `services/engine/`. It fills
  each order once, and the golden files pin it.
- Steps the Modeler assistant adds are never compiled: `compile.py:34–48` reads only rule and path nodes.
- Four of the ten seeded agents list tools that answer 501 (`0023_agent_identity.py:49–53`).
- Group-to-role mapping, flow versions and flow maker-checker exist.
- Device recommerce has no wipe, diagnostics or device-registry mock. Used cars, telecom and medical rental have no
  pack code.
- Detention terms are declared but unused, and the TMS adapter reads rate terms 1–3 only. (claim from a parked report)
- Discovery samples 200 records today (`discover.py:31`).
- `credentials.rotate` is not in `FORBIDDEN_ACTIONS`.
- 33 of 36 spot-checked file:line citations in G §7 and A's "today in repo" columns were right.

Corrected:
- **G:** live tool-fleet cases are planned in a queue of one (`intake.py:233–239`, `queue=[v]`). The planner is not
  skipped. Named orders can come in through the intake facts (`dem`, `intake.py:172–174`), but no source fills them.
  The README was corrected to match.
- **G:** `BASEP` is at `tool_fleet.py:166`, not 167. The resale-price model card's validation line is measured, not
  fixed.
- **I:** every other actual is a ±25% hash, except the pinned lines `LEARN_PIN` and `LINE_EXACT`. (claim from a parked report)
- **A:** the depot-repair adapter has authority over grade and test result, not teardown findings. The `dem` keys
  are lease, so, bid, proj, wo and rcq; there is no `pool` key.
- **F:** only five `org.` actions are forbidden, not `org.*`. The forbidden list also names `outcome.confirm`,
  `adapter.acknowledge` and the `mcp.` prefix.
