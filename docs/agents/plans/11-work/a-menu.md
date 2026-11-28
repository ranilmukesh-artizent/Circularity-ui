# Plan 11, section A (menu): report from writer A (second pass)

## What the interrupted writer left, and my verdict
Read the full diff and the three untracked files. The work covered A1, A2, A3 and most of A4 and was sound, so I kept
all of it and changed no code:
- `nav.py`: `SECTION_LAYOUT`, `RELABEL`, `regroup`, `staged_filter`, `has_published_setup`, `landing`; `page()` returns
  `staged` and `landing`. Demo workspace and any org with visible cases count as published; else one query on
  `composition` (status `published`, org-unit scoped for tenant-scoped accounts). Hiding is display only.
- Sections: Home/Set up, Decide (My Tasks, Cases, alerts), Understand (Pulse, Analytics, Reports, Agents), Advanced
  (Modeler, Connection Fabric, Data Checks, MCP & Tools, "Data pipelines and runs", Audit), More (Access, Settings).
- `Sidebar.tsx` + `sidebarView.ts`: Advanced is a real `button` with `aria-expanded`/`aria-controls`, closed by
  default, opens by itself when the current page is inside it, stored in localStorage (try/catch); staged note at the
  foot. `app.css`: rules added only (focus-visible outline, rail and reduced-motion handling).
- `WorkflowBuilder.tsx`: "Build a data pipeline with AI" / "Describe the data pipeline" (text only).
- Tests: `test_nav_staged.py` (pure regroup/filter, 11 accounts, staged monkeypatch), `test_screens_reference.py`
  compares the golden menu with the overlay applied (every golden id still present), `sidebarView.test.ts`.

## Per file
nav.py, test_nav_staged.py, test_screens_reference.py, frontend nav.ts (`navStaged`, `navLanding`), Sidebar.tsx,
sidebarView.ts/.test.ts, app.css, WorkflowBuilder.tsx: as above. `policy.py`, route/schema, `test_mywork_nav.py`: untouched.

## Checks
- mypy nav.py: "Success: no issues found in 1 source file"; ruff: "All checks passed!"
- `docker compose exec -T web npx tsc --noEmit -p .`: no output (clean, including other writers' files at that moment).
- `npx vitest run src/layout/sidebarView.test.ts`: "Tests 5 passed (5)".
- api tests: see the last section (filled in when the run ended).

## Left undone or unsure
- A4: the server answers `landing: "setup"` while staged, and `navLanding()` exists in `api/nav.ts`, but nothing reads it
  yet: the sign-in landing is `landingRoute` in `frontend/src/api/session.ts` (not my file). The reader is a one-liner
  there or in the app router; a lead decision. Policy landings (golden, `can_page`, `home()`) are unchanged: all 11
  accounts still land as today once published.
- Stated plan wording differs from the brief (plan text puts Reports, Audit, Policies elsewhere); I followed the brief.
- `WorkflowBuilder` old text: no unit test asserts it. `frontend/scripts/smoke-p9-8.mjs:607` mentions "Build a workflow
  with AI" only in a comment; its regex matches the Studio's button "Build a workflow", not the modal title. Left alone.
- `has_published_setup` uses raw SQL in the services layer (as `ISSUE_SQL` already does); a repository function would be tidier.

## Lead addition: My Tasks while a setup waits for approval
`staged_filter(groups, published, waiting=False)` (pure) keeps `tasks` when `waiting`. `nav.py` gained
`_composition_in(p, session, status)` (shared by both checks), `has_submitted_setup` (status `submitted`, org-unit
scoped like the published check), and `page()` passes `waiting = not published and has_submitted_setup(...)`.
`test_nav_staged.py`: staged + nothing submitted = Home, Set up, Access; staged + submitted = plus My Tasks (pure test and
an endpoint test for admin). mypy and ruff clean after the change.

## Final api run (after the addition)
`API_TEST_NO_X=1 bash scripts/dev/api-test.sh tests/test_nav_staged.py tests/test_mywork_nav.py tests/test_screens_reference.py`
last line: `64 passed, 1 warning in 142.37s (0:02:22)` (62 passed before the addition).

## Answers to the lead
- `GET /api/auth/me` `home`: unchanged. I did not touch `policy.py` or `routes/auth.py` (no diff in them).
- Frontend applying `landing`: NOT done. `navLanding()` exists in `frontend/src/api/nav.ts` but nothing calls it (grep
  `navLanding` finds only its definition). The first-load-after-sign-in rule must be added where sign-in routes
  (`api/session.ts` `landingRoute` / the app shell), files outside mine. Suggested: apply it once per sign-in (a
  sessionStorage flag set at sign-in), never on a later click on Home.
