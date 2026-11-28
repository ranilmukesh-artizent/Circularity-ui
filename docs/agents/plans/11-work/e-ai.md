# Writer E, plan 11 section C (C1, C2, C3)

## How `compose.start` works (as found)

1. `start_guard` checks length (MAX_TEXT 4000), the pack key, the org unit and tenant reach.
2. `start` loads `active_pack(session, key, org)` for the given `pack_key`, or for every pack when none is given.
3. `_draft` calls `config_agent.draft_change_set(text, org, packs, answer, drafter=pack_author.make_drafter(ctx))`.
4. `make_drafter` runs the router's `author` model in an `agent_run` of its own (no tools) and returns a `ModelDraft`
   (pack, typed ops, assumed ids, kpis, systems, optional question), or None when no model answered or the loop raised.
5. `_accept` checks every draft: the pack must be in the call, deterministic controls win, weaker values and compliance
   skips go to `blocked`, `apply_overlay` must pass. A refusal is retried once with the error; then `_deterministic`
   (rules only) answers with `by_model` false. A drafter returning None goes straight to the rules.
6. The row stores `reading` (with `by_model`), `change_set` (with `by_model`), `steps` (`new_steps()`), status `draft`.
7. A rate limit or "no model" never reaches the UI as an error: the call succeeds with `by_model` false. Only a
   `ChangeSetError` becomes `validation_error`. `config.read` (called first by SetupMode) also asks a model.
8. `compose.answer` re-drafts live with the chosen option.

## What changed

- `backend/di/services/modeler/compose.py`: pure helpers `normalise_prompt`, `draft_key` (sha256 of pack version + normalised
  prompt), `stored_draft`, `write_stored_draft`, `STORED_DIR` (`packs/stored_drafts/`).
- `backend/di/services/actions/compose.py`: `StoredFirst` drafter wraps the live one. For `answer is None` and no earlier
  refusal it returns the stored `ModelDraft` for the sample prompt, which then goes through `draft_change_set` / `_accept`
  like a live answer; a refusal, another text, an answer or a missing/invalid stored file falls to the model.
  The mark is `steps.describe.draft_source` = `stored` | `model` | `rules` (`by_model` stays true for a stored draft, since
  it passed the model checks; the `log` text says "from a stored draft" / "by the rules"). `compose.answer` updates the
  value to `model` or `rules`. No new table, no migration; `markStep` keeps the extra key.
- `backend/scripts/build_stored_drafts.py`: builds drafts through the real `make_drafter` and `draft_change_set` with
  retries (20, 45, 90 s) and 15 s between prompts; only a draft a model gave and the checks accepted is written.
- `backend/di/services/modeler/packs/stored_drafts/{tool_fleet,device,industrial}.json`: built, checked in.
- `backend/tests/test_compose_stored_drafts.py`: key, round trip, misses, stored path (loop double never called), other text
  calls the model, no model gives `rules`, a stored draft of a pack not in the call is refused and falls through,
  other pack version misses, `compose.answer` goes live and updates the source.
- `frontend/src/layout/assistant/modes/setupProgress.ts` (+ test): `progressStatus` (Reading, Matching, Drafting, then
  after 25 s "Still drafting: free-tier models can take up to a minute"), `draftSource`, `sourceLine` ("Used the stored draft
  for this sample"), `plainFailure`, `templateHref`, `isSamplePrompt`.
- `SetupMode.tsx`: a 1 s timer patches the turn status from the helper while a draft runs; a `Waiting` line with
  `role="status" aria-live="polite"`; the source line uses `sourceLine`; when no model answered: one sentence plus
  "Try again in a minute, or use the template as it is." and a link to `#/setup?new=1&pack=<pack>&org=<org>`.
  A text that is a sample prompt of the picked pack skips `config.read` (which would call a model) and goes straight to
  `compose.start`. `SetupMode.css`: `.st-notice`, reduced-motion rule (no new motion).

## Stored drafts

Built 9 of 9 (tool_fleet 3, device 3, industrial 3); none failed, no retry was needed. The models returned 0 operations for
eight prompts and 1 for industrial prompt 2: the limits the prompts state are taken by the deterministic reading in `_accept`
at start time, so the stored model part is mostly pack choice, kpis, systems and question.

## Checks

- `export MSYS_NO_PATHCONV=1; API_TEST_NO_X=1 bash scripts/dev/api-test.sh tests/test_compose_stored_drafts.py tests/test_composition.py`
  last line: `23 passed, 1 warning in 214.28s (0:03:34)`. (Run before the frontend-only change that skips `config.read` for sample
  prompts; no backend file changed after it.)
- `docker compose exec -T api sh -c "ruff format ...; ruff check ...; ruff format --check ...; mypy ..."` on the four Python
  files: `All checks passed!`, `4 files already formatted`, `Success: no issues found in 3 source files`. `lint-imports`
  printed nothing in the captured output, so it is not confirmed.
- `docker compose exec -T web npx tsc --noEmit -p .`: no output (clean, including files I do not own).
- `docker compose exec -T web npx vitest run src/layout/assistant`: `Test Files 8 passed (8)`, `Tests 69 passed (69)`.

## Left or uncertain

- The pack's one question is not stored: after a stored draft the person's answer goes to `compose.answer`, a live model
  call (or rules when none answers).
- Set up's own page (`TemplateStep.tsx`, writer B) may call `compose.start` itself; it gets the stored draft on the server
  side, but its progress text is B's. `config.read` still calls a model for any text that is not a sample prompt.
- No server stages exist; the stages are time-driven and worded as "what is being done", not as confirmed steps.
- The 429 detection in `plainFailure` is a text match; a real rate limit today never fails `compose.start` (it falls back to
  the rules), so the visible C3 case is `draft_source === 'rules'`.
- No browser check was run (not allowed in the brief).
- The npm and Python files I edited were normalised to LF (repo attribute `eol=lf`); `actions/compose.py` and
  `modeler/compose.py` were CRLF in the working copy before this change.
