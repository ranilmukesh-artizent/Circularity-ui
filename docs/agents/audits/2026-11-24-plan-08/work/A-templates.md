# Agent A: the tool-fleet and device templates end to end (24 Nov 2026)

Worktree `Circularity-ui-fix`, database `di_fix_a`. No git state changed.

## What was proved
`backend/tests/test_template_e2e.py::test_template_case_end_to_end[tool_fleet|device]` runs as real accounts through
`call()` and the HTTP client:
1. Admin `case.open` for Customer A: stage `awaiting_approval`, the recommendation is one of the template's paths.
2. planner-a: `GET /api/screens/case/{id}` 200, route ids = the template's path ids; `GET /api/screens/modeler?template=<t>&org=Customer A`
   lists the case in `queue` with the same `best`.
3. planner-a `flow.fork` (Customer A), `flow.saveDraft` with `with_rule(..., "XR-1", "exclude", <recommendation>)`,
   `flow.submit`; planner-a's own `flow.approve` is refused; `approver` approves and publishes. The case is untouched.
4. `decision.submit` (planner-a), `decision.decline` (approver, reason), stage `reeval`; planner-a `case.reevaluate`:
   routes still the path ids, the excluded path fails with "Excluded by business rule XR-1: ...", the recommendation
   moves to another path, `rulesApplied == ["XR-1"]`, `was`/`now` in the output match.
5. `decision.submit` + `decision.approve` (approver): stage `approved`, step kinds = `ex_kinds(rec)` = `STEP_TPL[path]`.
   With instructions on and Customer A in pilot mode, exactly one `instruction` row (step 0, the first kind, `queued`);
   `send()` answers `held` (nothing reaches a mock). Case screen and `/analysis` still 200 after approval.
6. `org.pilotReport` (admin): cases_opened, decisions_submitted, decisions_approved, rules_applied_count,
   instructions_held and by_route[path] each +1 versus before the case opened.

## Bug found and fixed (test first)
- **A template case ignored the business rules in its record.** `intake.template_routes` built the routes from the
  valuer run *with* the rules, so a rule-excluded path was already `ok: false` when `apply_business` ran: it found no
  eligible hit and recorded nothing. Tool fleet: `rulesApplied` missing (KeyError). Device: the excluded path's reason
  was the generic "Offers cannot take this lot", not the rule. Failing run (before the fix):
  `FAILED ...[tool_fleet] KeyError: 'rulesApplied'`, `FAILED ...[device] ... 'Offers cannot take this lot'.startswith(...)`.
- Fix (`backend/di/services/cases/intake.py`, `template_routes`): the values and the chosen path still come from the
  valuer run with the rules; each path's `ok`/`why` comes from the valuer run without rules, then `apply_business`
  applies the rules (reason "Excluded by business rule <id>: ...", `rulesApplied`, waiver, prefer) as for an
  industrial case. The recommendation stays the valuer's choice (`best`), so F6 (case = simulation) still holds.

## Left open after the first round (both fixed in the follow-up below)
- **Manual import cannot open template cases.** `connectors/manual.py` `open_cases` passes `facts = {}` for a
  non-industrial template, and `import.commit`'s row checks accept only industrial asset ids (`MTR|PMP|CTL|DRL|BAT|ITE`)
  with no tool class, age band or reference value. Every row of a `tool_fleet`/`device` import is skipped silently
  (`cases_opened: 0, cases_skipped: 1`), though Records.tsx offers both templates (`CASE_TEMPLATES`). Documented by
  `test_import_rows_open_template_cases[tool_fleet|device]`, `xfail(strict=True)`; confirmed with `--runxfail`:
  `AssertionError: {'case_ids': [], 'cases_opened': 0, 'cases_skipped': 1, ...}`. Options: refuse a non-industrial
  template in `import_guard` with a clear message (and drop it from the page's list), or add template columns.
- Re-evaluation of a template case does not record a shadow decision when the flow is in shadow (industrial does via
  `_rebuild`); not tested here.

## Files
- Changed: `backend/di/services/cases/intake.py` (`template_routes` only).
- Added: `backend/tests/test_template_e2e.py` (2 passing, 2 strict xfail).
- Shared files touched: none in the first round; `backend/di/services/actions/fabric_records.py` in the follow-up.

## Commands and results
- `FIX_DB=di_fix_a bash .../work/fixtest.sh tests/test_template_e2e.py` → before fix `2 failed`; after `2 passed, 2 xfailed in 47.32s`.
- `FIX_DB=di_fix_a bash .../work/fixtest.sh tests/test_case_intake.py tests/test_flow_simulate.py tests/test_screens_any_template.py tests/test_routes_adapter.py tests/test_valuer_tool_fleet.py tests/test_valuer_device.py tests/test_writes_decisions.py tests/test_audit_fixes.py tests/test_template_e2e.py`
  → `72 passed, 2 xfailed in 84.24s (0:01:24)`.
- `ruff check` + `ruff format --check` + `mypy di/services/cases/intake.py` on the two files (api image) → `All checks passed!`,
  `2 files already formatted`, `Success: no issues found in 1 source file`.

## Follow-up (coordinator: import opens template cases; shadow for template re-evaluation)
Tests first, in `backend/tests/test_template_e2e.py` (the two xfails became real tests). Failing run before the code:
`FIX_DB=di_fix_a bash .../fixtest.sh tests/test_template_e2e.py` → `4 failed, 3 passed` (import: "T-CMH-9911: asset_id
does not match a known class pattern"; shadow: `AssertionError: []`, no shadow_decision row).

1. **Manual import opens tool-fleet and device cases** (also audit 8.4: refusals are no longer all "skipped").
   - `backend/di/connectors/manual.py`: `TEMPLATE_COLUMNS` (tool_fleet: cls, grade, ft, site, rul; device: brand, model,
     band, grade, ref, qty, doh) and `template_facts(row, template)` (filled columns only; rul/ref/qty/doh as numbers).
     `open_cases` passes them as the intake's facts. A `duplicate` refusal counts as `cases_skipped`; any other refusal
     as `cases_failed`, listed in `case_failures: [{asset_id, code, reason}]` with the intake's code and message.
   - `backend/di/services/actions/fabric_records.py` (shared): `row_errors(r, template)` accepts any id-shaped
     `asset_id` (`[A-Za-z0-9][A-Za-z0-9._-]{0,63}`) for a non-industrial template (other column checks unchanged);
     `import.commit` keeps the template's columns in the stored rows and uses the template's checks for rejected rows.
   - `backend/di/services/cases/intake.py` `tool_fleet_case`: refuses (validation_error) a grade outside A-D, an `ft`
     or `site` the valuer does not know, a non-numeric `rul` (before: a CSV value could crash the valuer with a 500).
   - Tests: `test_import_rows_open_template_cases[tool_fleet|device]` (1 opened, 1 failed with the intake's reason,
     the case's `valuer` snapshot = the row's facts as numbers; the same file again: 0 opened, 1 skipped, 1 failed),
     `test_template_rows_need_an_asset_id`, `test_tool_fleet_facts_are_checked` x4 (written with the fix, not before).
2. **Shadow decision on a template re-evaluation.** `intake.recommend(s, c, rules)`: the recommendation under other
   rules on a copy (shared `_rank` with `_value`). `decisions.reevaluate` (template branch only): after `revalue`, if
   `shadow_rules` finds the flow in shadow, `_record_shadow(ctx, c, shadow, intake.recommend(...))`. Test
   `test_template_reevaluation_records_a_shadow_decision[tool_fleet|device]`: live recommendation unchanged, no
   `rulesApplied`, one row (flow, dver 2, live = the old path, shadow = another path, nets match).

**What the Records page must send (agent B1/B2; I did not edit the frontend):**
- `validateCsv` (Records.tsx:248) must know the chosen template: for `tool_fleet`/`device`, check `asset_id` against
  `^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$` instead of the `(MTR|PMP|CTL|DRL|BAT|ITE)-\d{4}` pattern (else the page rejects
  every template row before the server sees it); re-validate when the template changes.
- Keep and send the template columns in each row: tool_fleet `cls, ft, site, rul`; device `brand, model, band, ref, doh`
  (`grade` comes from `condition_grade` and `qty` from `qty`, as today). `ImportRow` and `importInput`'s `pick`
  (api/integration.ts:359-372) must carry them in `rows` and `rejected`.
- Show the new output: `cases_failed` and `case_failures[{asset_id, code, reason}]` beside "cases opened / already open"
  (`commitImport`'s return type gains both).

Files (follow-up): `backend/di/connectors/manual.py`, `backend/di/services/actions/fabric_records.py` (shared, smallest
edit), `backend/di/services/actions/decisions.py` (template branch of `reevaluate`, 2 lines),
`backend/di/services/cases/intake.py`, `backend/tests/test_template_e2e.py`.

Environment note: `tests/test_fabric_records.py` table tests failed on `di_fix_a` with "No table model for erp" because
the private DB had no `source_system` rows (the api's startup normally registers them). I ran `ensure_sources` once
against `di_fix_a` only (one-off container); then the file passed `9 passed`. Not a code change.

Commands and results (follow-up):
- `FIX_DB=di_fix_a bash .../fixtest.sh tests/test_case_intake.py tests/test_flow_simulate.py tests/test_screens_any_template.py tests/test_routes_adapter.py tests/test_valuer_tool_fleet.py tests/test_valuer_device.py tests/test_writes_decisions.py tests/test_audit_fixes.py tests/test_template_e2e.py tests/test_fabric_records.py tests/test_shadow.py`
  → `92 passed in 108.23s (0:01:48)`.
- `ruff check` + `ruff format --check` on the 5 files → `All checks passed!`, `5 files already formatted`; `mypy` on
  the 4 modules → `Success: no issues found in 4 source files`.
