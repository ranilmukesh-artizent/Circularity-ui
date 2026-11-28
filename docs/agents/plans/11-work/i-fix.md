# Plan 11, writer I: two small fixes

## 1. Sent-back pin on Set up
- `frontend/src/pages/modeler/compose/composeView.ts`: `sentBackPin(step)` (pure): by, reason, node for a sent-back step, else null.
- `frontend/src/pages/modeler/compose/SentBackPin.tsx` (new, shared): "Sent back by X: reason", "About: <node>", optional link "Open <step>". `brief` drops the reason line.
- `ComposePanel.tsx`: uses it (`brief`) instead of its own "About:" line.
- `frontend/src/pages/setup/SetupPage.tsx` (+ `setup.css` `.sup-back`): under the step header, one pin per sent-back step; the step in view has no link, others link to `#/setup?compose=<id>&step=<step>`.
- `composeView.test.ts`: `sentBackPin` tests. Smoke p9-8 unchanged (its "About: condition" expectation is right).
- Seen, not fixed: the state line reads "recommend.. Setup 371" (double period, from `stateLine(...) + '. '` in SetupPage).

## 2. Two yellow buttons
Cause: the composer's send button (`btn pri sm`, `AssistantPanel.tsx`, not mine) stays yellow beside the turn's own primary
("Start from <matched>", and "Open in Set up" in the draft turn). `SetupMode.css`: while a panel holds a turn with a primary,
the composer's send is drawn as a plain button (`:has`). Other states: Question options and Starters have no primary.

## Checks
- tsc: no output (clean). vitest setup + compose + assistant: 13 files, 169 tests passed.
- Screenshots: `...\scratchpad\i\pin-agents.png`, `pin-mapping.png` (setup 371 on the dev database, sent back by the approver).
- Not looked at in a browser: the single-yellow conversation state. Nothing staged or committed.
