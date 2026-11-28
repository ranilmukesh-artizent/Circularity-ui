# Phase 13 review (P9-13.14, step 5)

Reviewer: writer 97, a read-only review by code reading, 28 Nov 2026, on `lead-merge` (`470528db`, with the fixes of `3acbb78c` and
`3132e4ef`). Scope: the `P9-13.*` commits (`3d10a57f` ... `8b9c9213`) and the PROGRESS rows. No test was run and no stack was started;
every finding was checked at the cited line. Focus: Review Focus 3, 6 and 9, agent and OAuth tokens, no token passthrough, money in
`Decimal`, the industrial parity guards. Accounting, reporting and compliance findings: to be reviewed by Kinective's Legal team before
it is relied on.

## Findings

| # | Severity | Finding | File:line | Verified | Suggested action |
|---|---|---|---|---|---|
| 1 | P1 | An agent's own token (client credentials, `aud` "di") runs write routes that are not actions with no agent check, as its owner. `routes/actions.py` and `resources/router.py` set the preparer and apply `tools_refusal`, but `PUT /api/access/delegations/{scope}` (what the Approver may decide: access, an `access.` family), `POST /api/sources/{id}/connect` and `/disconnect` (`source.` family), `POST /api/journal/undo` and the `/api/v1/tasks` writes check only the owner's permission. The tasks `_run` builds a `CallContext` with no `preparer`, so `task.cancel` (in `FORBIDDEN_ACTIONS`) runs as the owner's. Review Focus 6 (R21) holds on `/api/actions` only. An Admin's agent credential can therefore change access, disconnect a source or cancel a task. (An OAuth token is refused at `/api`: `resolve_mcp`.) | `routes/auth.py:47-51`; `routes/sources.py:48-58`; `routes/actions.py:79-82`; `routes/tasks.py:29-36`, `:61-80`; compare `routes/actions.py:43-48`, `resources/router.py:76`; `core/auth.py:81-84`, `:197` | Yes (code path; not run) | Needs code: one `p.agent_id` refusal for every non-GET route outside actions and resources (a dependency, or `_person(p)` as in `routes/oauth.py:81`), and set `ctx.preparer`/`confirmed=False` plus `tools_refusal` in the tasks `_run`. Test: an agent token on each route gets 403. |
| 2 | P1 | `settlement.resolve` with `accept_erp` closes the case without the reporting check. The last acknowledgement goes through `reporting_missing` and `hold_for_evidence` (X-16, G-REP-1/2); the accept path calls `lifecycle.move(... "closed")` directly. The `device` pack has both `close.credit_settlement` and `close.reporting` (`["G-REP-1"]`), so for a CSRD-scope org Finance can close a device case with no mass and material on file. Review Focus: close only with reporting evidence. **To be reviewed by Kinective's Legal team before it is relied on.** | `services/actions/execution.py:268-277` vs `:183-187`; `services/actions/reporting.py:56-64`; `packs/device.json` (`close`) | Yes | Needs code: in the `accept_erp` branch, call `reporting_missing`; when it lists anything, keep the case `executing`, `hold_for_evidence`, and close later from `case.attachReporting`. Test: device case, CSRD org, mismatch, accept without evidence stays open. |
| 3 | P1 | Review Focus 3: the replay and the Compose back-test decide a case differently from intake, simulation and the chain for the packs with downstream roles. `decide_case` reads the vendor records only when it has a session (`own_vendors`); `replay.run` and Compose's `watch` call it with no session, so G-DS-1's dated vendor qualification (X-14) never applies there and a route with an expired recycler certificate stays eligible. Packs affected: medical_rental, telecom_network, tool_fleet, used_cars (`downstream_roles`). `test_paths_agree_*` pass because their facts carry no vendor records. | `services/cases/decide.py:548-550`; `services/replay/run.py:513-530`; `services/actions/compose.py:548`; `services/replay/telecom.py:144` | Yes | Needs code: pass a session or a vendor snapshot into the replay deciders (as `case["vendors"]`), or record in the decision log that replays do not judge vendors. Test: a pack case with an expired certificate, decided by intake and by `replay`, gives the same route. |
| 4 | P2 | Review Focus 9: vendors are read as they are now, whatever the decision date. `vendor_facts.records` has no `as_of`; a replay as of an earlier date judges today's `cert_valid_to`, `cert_ref` and status (a certificate renewed or revoked since leaks into the past decision). `DATED` also accepts the statuses `lapsed` and `expired`, so a live vendor marked expired with a future `cert_valid_to` qualifies. | `services/cases/vendor_facts.py:16-19`; `services/modeler/vendor_qualification.py:22`, `:64-67` | Yes | Decide with finding 3: a dated vendor snapshot per replay; drop `lapsed`/`expired` from `DATED` for a live decision. |
| 5 | P2 | The fixed-asset retirement posts money as `float` and a fixed currency. `_proceeds` sums the route's terms as floats and the body's `currency` is `"USD"` whatever the case's currency, so a case in another currency retires at its amount in dollars. No cent rounding before the post. **To be reviewed by Kinective's Legal team before it is relied on.** | `services/instructions/writers_asset.py:30`, `:41-47`, `:70-71` | Yes | Sum in `Decimal`, round to cents, take the case's currency (as `settlement._quote` does). |
| 6 | P2 | A malformed ERP answer crashes or passes. The credit writer does `float(doc["amount"])` on the ERP's body (`KeyError`/`TypeError` is a 500, not `Refused`); `settlement._dec` accepts any string (`Decimal("abc")` raises `InvalidOperation`, and `NaN` fails at `quantize`); `settlement.record` treats an answer with an amount but no `memo` as a simulated step and returns "matched". | `services/instructions/writers.py:459`; `services/execution/settlement.py:54-59`, `:138-139` | Yes | Refuse a credit memo with no numeric `amount`; `_dec` returns None on `InvalidOperation` and non-finite values; treat "amount without memo" as a mismatch. |
| 7 | P2 | Redirect URI check of `agent.registerClient` is a prefix test: `http://localhost.example.net/cb` and `http://127.0.0.1.example.net/cb` pass as "localhost". Fragments and wildcards are not refused either. Admin-only, and the authorize step then needs an exact match, so the exposure is a registration mistake. `/oauth/token` has no attempt limit (each try costs one scrypt run; no lockout). | `services/actions/agents.py:182-185`; `routes/oauth.py:57-63` | Yes | Parse with `urlsplit`: scheme https, or http with host exactly `localhost`/`127.0.0.1`/`[::1]`; refuse a fragment. Rate-limit by client id and address. |
| 8 | P2 | `residual.record` stores `gain_loss` as float and takes the lease's currency without comparing it to the ERP proceeds' currency; a USD residual against EUR proceeds yields a number in neither. | `services/execution/residual.py:50-53`, `:72` | Yes | Compare currencies (no line when they differ), store the cent string or keep `Decimal` in the case JSON. |

Checked with no finding:
- OAuth (P9-13.10): S256 only, no `plain` (`services/oauth.py:137`); redirect URI exact match at authorize, consent and exchange (`:133`, `:180`, `:224-225`); the code is hashed, single use, 60 seconds, consumed by one `UPDATE ... RETURNING` even when the exchange then fails (`:209-221`); `resource` must be this MCP (`:139`); scopes limited to the client's registration (`:142`, `:186`); no refresh token; token `aud` the MCP resource, `act.sub` the agent, 15 minutes. Consent refuses an agent (`routes/oauth.py:81-83`). A revoked client, a stopped agent or a deactivated owner ends the token at the next request (`core/auth.py:122-132`).
- Audience: an OAuth token is refused at `/api` (`principal` uses aud "di"; `resolve_mcp` picks the audience); the MCP gate refuses a foreign `aud` and checks scope per `tools/call`, batches included (`mcp/server.py:138-151`, `:170-188`); a token for agent A with `X-Agent` B is refused (`mcp/policy.py:226-228`).
- No token passthrough: `mcp/oauth.py` and the gate never forward the caller's token; the connectors build their own credentials per adapter; grep of `connectors`, `services/agents` and `mcp` finds no inbound `Authorization` used as outbound.
- Client credentials (P9-13.9): scrypt hash, constant-time compare, one scrypt run for an unknown client, secret shown once, never logged or listed; revoked credential, disabled agent, kill switch and SCIM-deactivated owner are checked on every request (`core/auth.py:97-120`); `agent.` (issue, revoke, register, list) is forbidden to agents; `settlement.resolve` is forbidden and `case.attachReporting` held.
- Money (settlement, core credit): `Decimal` with `ROUND_HALF_UP` to cents, `pct` an int, match to the cent (`settlement.py:58-64`, `:109`); the retirement and transfer write only the ERP's answer (`execution/asset.py`); the credit and asset steps use the approval reference as the idempotency key.
- Industrial parity: `industrial.json` has no `close` block and `PackClose` defaults all off (`modeler/pack.py:110-116`, `close_kinds`), so the industrial plan has no asset, credit or reporting step; no file under `fixtures/` changed in `3d10a57f^..HEAD`; the `*_industrial_unchanged` tests exist in `test_x13_*`, `test_x14_*`, `test_x16_*`.
- Review Focus 3: `test_paths_agree_<pack>` exists for each of the 13 packs (see finding 3 for what it does not reach).

## Needs code

- F1 and F2, F3 (P1): agent token on non-action routes; `accept_erp` close with reporting evidence; vendors in the replay paths.
- F4 to F8 (P2) as listed.

## Whole plan: open findings of the phase reviews 0 to 12 (state at `470528db`)

| Phase | Open, state |
|---|---|
| 0 | #1 (autopilot `decision.submit` as the opener) for the person; #2 (`workflow.create`/`publish` of a decision workflow) kept by parity. #3, #4 fixed. |
| 1 | Findings 1 to 6 went to the P9-1.15 fixes; not re-checked here. |
| 2 | #2 (open transaction while the model reads, P9-2.24) open; #1, #3, #4 fixed. |
| 3 | Fixed: 2 to 5, 9, 11 (`2ccafc2a`). Open: 6, 7, 8, 10, 12 to 15. |
| 4 | Fixed: F1 to F4, F7 tests (`d2eab8df`). Open: F5, F6, F8 to F14. |
| 5 | Fixed H1, M1 to M7, L7 (`3b38c8d0`). Open: L1, L2, L4, L5, L6, L8, L9, T1. |
| 6 | Fixed F1, F2, F4, F5, F7, F9, F10 (`d8a1ac38`). Open: F3, F6, F8, 11 to 18. |
| 7 | P1 (canary replay bound to draft content) fixed (`3acbb78c`). Open: F2 to F5 (P2). |
| 8 | P1 (SCIM Admin email) fixed (`3acbb78c`). Open: F2 to F5 (P2). |
| 9 | Open: F1 (decision), F2, F3, F4 (P2). |
| 10 | Open: F1 (decision), F2, F3 (P2). |
| 11 | P1 (missing service and safety evidence) fixed (`3132e4ef`). Open: F2 to F5 (P2). |
| 12 | P1 G-DATA-1 and G-DATA-2 fixed (`3acbb78c`). Open: F3 to F7 (P2). |
| 13 | New: findings 1 to 3 (P1), 4 to 8 (P2) above. |

Of the earlier High/P1 findings only phase 2 #2 (open transaction while the model reads) is known to stay open, besides the phase 1 items not re-checked; the open P2 items and the phase 0 owner decisions are for the lead to sequence.
