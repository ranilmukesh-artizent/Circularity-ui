# Plan 11, writer D: finishing pass

Scratch (screenshots, logs, scripts): `C:\Users\ranilmj\AppData\Local\Temp\claude\780921fb27081449\df3f1b00-d9b3-4212-932e-39cbcbf03b94\scratchpad\fin\`
Final screenshots: `...\fin\r2\b-{desk,phone}-{1-empty,2-typed,3-picker,4-search,4b-nomatch}-{light,dark}.png` and `b-{desk,phone}-7-talking-{light,dark}.png`, `b-*-8-after.png`.
The first round (before the fixes) is in `...\fin\r1\a-*.png`.

## Task 1: template screen

Looked at: empty, typed with the suggestion line, picker, picker with a search ("phone"), no match ("zzzz"), the
conversation after "Draft my setup"; 1440x900 and 390x844, light and dark.

Defects seen and fixed:
1. Conversation panel (`.sup-talk`): the assistant's pinned panel kept its Modeler width (about 385 px) in an 860 px box, with
   the right half empty (desk and phone). Fixed: `.sup-talk .as-panel.pinned { width: 100%; border-right: 0 }` (`setup.css`).
2. Picker: Enter or Space on the already-chosen card did nothing (a checked radio fires no click), and an arrow key chose a
   card and closed the dialog at once. Fixed in `TemplateStep.tsx`: the dialog keeps a pending choice (`sel`), arrows move
   it, Enter, Space or a mouse click (`detail > 0`) chooses and closes, Close or Esc resets it.
3. Picker jumped up and down as a search shortened the list (dialog centred). Fixed: anchored at 8vh (4vh on a phone).
4. Phone hit targets: "Draft my setup" 34 px, "Use the template as it is" 28, picker "Close" 28, "Start again", and the "Start
   from that template" link 20 px. Fixed: 44 px under 640 px (`setup.css`); the link got 3 px of padding on desktop (24 px).
5. Search placeholder was cut off on a phone: now "Phones, tools, vehicles…" (the label still names the field).

Checked and fine: no horizontal overflow at either width; one yellow primary on the empty and typed screens; inputs 16 px on
the phone; focus rings visible (box, "Starting from", cards, links); dark mode contrast, dialog and backdrop; text clamps.

Keyboard (script `kb2.mjs`/`kb3.mjs`, 1440 px): "Starting from" opens the dialog (focus on Close), Tab goes to the search, then
to the one checked card; arrows move between cards without closing; Space and Enter choose and close, also on the current
card; focus returns to the "Starting from" button; mouse click on another card changes the template ("Device recommerce")
and closes. Esc in the search box clears it first (Chrome's search input), Esc again closes.

Seen, NOT fixed (outside my files):
- Conversation view: two yellow buttons on screen when the assistant asks "Start from Tool fleet returns / Keep ..." (the
  asking button plus the composer's disabled "Draft"). `layout/assistant` is not mine; the disabled one is faded.
- The assistant asks about the pack again when the text reads like another one, even though the page already offered "Start
  from that template" (behaviour of `SetupMode.tsx` PackChoice, as before).
- Model call: after "Draft my setup" the assistant answered within 10 s (it asked which pack to start from); I did not
  press on to the draft itself in the screenshots, so `compose=<id>` did not appear (no rate-limit message was seen).

## Task 2: smokes

- `frontend/scripts/a10-setup.mjs`: `openSetupTab` takes `pack` (else the Modeler URL's `template`) and puts it in `?pack=`
  (the page now starts from the organisation's default pack, Industrial, and the first sample is that pack's); `describeInAssistant`
  also clicks "Start from <matched>" when the assistant asks which pack to use (it only knew "Draft against ... anyway").
- `smoke-p9-8.mjs`: step 1 opens with `pack: 'tool_fleet'`; after the question the page may move on by itself, so it goes back
  to Business flow and marks it done only if it is not already "Done". `smoke-p9-9.mjs` (`used_cars`), `-10` (`telecom_network`),
  `-11` (`medical_rental`): `pack` in `openSetupTab`. `smoke-a10-t3.mjs`, `smoke-pages.mjs`: unchanged (they read the
  Modeler `template` now, or follow the menu).
- `node --check` clean on all six. Only p9-8 was run; the others are not run (not asked).
- Texts that plan 11 changed and the smokes did not need: "Build a workflow" button (the Studio's button is unchanged,
  only the modal title changed), `G-MED-DECON`/`G-NET-CFG` alternatives still have their text alternatives.

## Task 3: guides (`docs/guides/users/*.md`)

Menu names (Pulse, Cases, Data pipelines and runs; the Pulse page's own heading still says Command Center, noted in the README),
a new "The menu" section in `README.md` (Decide / Understand / Advanced, the staged menu), the planner's Compose section is
now "Set up a business in five steps" (Business flow with the one box and the template picker, Systems with the mapping
rule, Agents, Approve with Access, Publish with "This setup is live" and "Open Pulse"), `developer.md` (data pipeline
wording), "Compose" mentions in approver, executive, developer, README. No other section touched.
Legal note: these guides still say the accounting and reporting texts need review by Kinective's Legal team.

## Task 4: end checks

1. `bash scripts/dev/web-check.sh`: `tsc errors: 0`; `Test Files 157 passed (157)`, `Tests 1101 passed (1101)`.
2. `API_TEST_NO_X=1 bash scripts/dev/api-test.sh tests/test_nav_staged.py tests/test_mywork_nav.py tests/test_screens_reference.py tests/test_ns_ind_parity.py tests/test_composition.py`:
   `83 passed, 1 warning in 392.60s (0:06:32)`. (A first run died at collection: `modeler/compose.py:74` had a literal newline in an
   f-string, written by someone else's edit and fixed minutes later.)
3. `reset.sh`, then smokes. IMPORTANT: another writer was editing the tree the whole time (Analytics headline work: `PackHeadline.ts`
   renamed, `AnalyticsCharts.tsx` split, `compose.py`, `actions/compose.py`, `questions/*`, a `_probe_g1.py`), the api reloaded
   continuously and two fresh-clone stacks loaded the machine. So:
   - `smoke-pages.mjs` as shipped timed out on sign-in (30 s) under load. A copy with a 150 s default timeout
     (`fin/smoke-pages-slow.mjs`): run 1 `admin 15 failing ... wm 0 failing`, all but 3 from "does not provide an export named
     PackHeadlines" (module in flux); run 2 `admin 0, executive 8, planner-a 7, planner-b 0` all from "does not provide an export
     named PoolChart" (again an analytics module mid-edit); I did not let run 2 finish. developer, wm-1, wm-2 (no analytics) were 0 failing.
     No failure was about the menu or Set up. NOT a clean pass: rerun when the tree is quiet.
   - `smoke-p9-8.mjs` (after the script fixes above), last run: `PASS 1` (composition 370), `PASS 2`, `PASS 3`, `PASS 4`, `PASS 5`,
     then `FAIL 6 Send back with a pinned note ... the note is not pinned to the condition node smoke-p9-8.mjs:460`. Steps 7 onward not run.
   - Product defect behind step 6 (not mine to fix, `SetupPage.tsx`): the old Compose panel showed "About: <node>" under a step
     that has a sent-back note (`modeler/compose/ComposePanel.tsx:71`); the Set up page does not render it, so the Agents step
     shows no pin to the node (the Approve step does print the node: "Sent back at ... (condition): reason"). Fix: render
     `c.steps[screen].note.node_id` as "About: ..." in the step header of `SetupPage.tsx`. Then rerun p9-8 from step 6.
   - `reset.sh` run again at the end (worker restarted, the main database is back to the demo).

## Left undone or unsure
- Clean `smoke-pages.mjs` and `smoke-p9-8.mjs` passes (see above); p9-9/10/11 and a10-t3 edits are untested.
- The `SetupPage.tsx` pin (above); the two yellow buttons in the conversation view.
- "Open Pulse" and the staged menu were not re-looked at in a browser by me beyond the screenshots of the template screen.
- Nothing staged or committed.
