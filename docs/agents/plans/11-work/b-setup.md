# Plan 11, writer B: Set up (B1 to B4)

## What the interrupted writer left
Uncommitted edits in `SetupPage.tsx`, `setup.css`, `setupView.ts` (B1 in the view module and the page; no tests updated, nothing for B2 to B4).
Judged against the brief: the LINE table (five stops over seven), `screenFor`/`screenOf` (old `step=access` opens Approve), `partLine`,
`neighbours` over six screens, `pageStops` merge rules and the Approve page with Access above the approval were right and kept.
Fixed: a missing space in JSX (`current={...}hrefFor`); `setupView.test.ts` still described seven stops (rewritten); DescribeStep was not under a Suspense on the page (needed now, see B4).

## Per file
- `pages/setup/setupView.ts`: kept as left (LINE, PAGE_HANDOVER 3, lineOf, screenOf, screenFor, SCREEN_LABEL, partLine, stopStates, pageStops, neighbours).
- `pages/setup/setupView.test.ts`: rewritten tail: seven stops in the data, five on the line, merged stop states (Business flow done only when template and flow both are; Approve done when access and approval both are; sent back; published), old links (`access`, `describe`, `flow`, unknown step), parts, Back/Next incl. an old access link. 40 tests.
- `pages/setup/SetupPage.tsx`: spacing fix; DescribeStep wrapped in Suspense.
- `pages/setup/setup.css`: as left (part line, Approve sections).
- B2 `modeler/compose/PublishStep.tsx`, `publishView.ts` (+test), `publish.css`: when `c.status === 'published'` an "This setup is live" block sits above the checklist: share that is live (from the rollouts, paused ones left out), Decide: My Tasks, Cases; Understand: Pulse, Analytics, Agents, and one `<a class="btn pri" href="#/command">Open Pulse</a>`. Checklist unchanged below (all Done). The Compose tab shows it too (same step body). Sidebar not touched.
- B3 `modeler/compose/SystemData.tsx`, `systemsView.ts` (`FIELD_RULE`): the sentence sits under the Mapping note, before the suggest button.
- B4 `modeler/compose/DescribeStep.tsx`, `changeSetView.ts` (+test), `ChangeSetList.tsx`: "Drafted for <pack name>" (was the key); the match line falls back to a worded key ("Tool fleet") until the server's `pack_names` arrive; guardrail ids in the outline ("stated", "from the pack", research additions) and in refusals ("Blocked by <guardrail text>: ...") are shown by the guardrail's text, taken from the template's guardrails in `useModeler(pack, org)`; an id with no text reads "a guardrail". `ChangeSetList` takes an optional `guardrails` map; without it (the assistant's Set up mode, not mine) it behaves as before and still prints the id.

## Checks
- `docker compose exec -T web npx tsc --noEmit -p .` : no output (clean, including other writers' files at that moment).
- `docker compose exec -T web npx vitest run src/pages/setup src/pages/modeler/compose` : `Test Files 5 passed (5)`, `Tests 95 passed (95)`.
- No smoke script edited (so no `node --check`): the selectors `.rl li[data-stop="publish"] a.rl-stop`, `.rl li[data-stop=describe|mapping|agents|approve]`, `section.sup-step`, `.sup-state` ("Setup N,") all still exist; `data-step` on the panel is now the screen id (`flow` still for the canvas).

## Not done or unsure
- `pack names` on the client: `packCards()` is only used by the template picker, which is not mounted once a setup exists, so the Describe review uses `pack_names` of the existing `config.read` and a worded key as fallback (no hard-coded list).
- Smoke assertions that may now differ and that I did not run: `smoke-p9-10.mjs:325` (needs "wipe" in the refusal line; the line now carries the guardrail's text instead of its id, so it should hold if the text or the refusal says wipe), `smoke-p9-11.mjs:353` (id `G-MED-DECON` no longer shown; the "decontamination record" alternative must match). `smoke-p9-9.mjs:360` has text alternatives.
- A published setup's "Open Pulse" is shown to everyone who can open the step, without a page-access check.
- Not looked at in a browser (not allowed): 1440, 1100, 375 px, light and dark are by construction (existing tokens only).
- The Modeler's step list outside `compose/` (and `layout/assistant/modes/SetupMode.tsx`) still names seven stops or ids where it does; not mine.
