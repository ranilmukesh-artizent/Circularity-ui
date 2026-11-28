# J: server gate, one days definition, plural, route names (Analytics)

## 2. The two definitions
- Tile (`di/services/questions/headline.py`): median of (case `created_at`) to (last `closed` row of `case_stage_log`), both database timestamps.
- Rows (`analytics_rows._rec_of`): case document's `received` (the source system's date), else `created_at`, to the same close time.
- Evidence: RT-1131 was received 2026-10-07 (source-sim clock) but created and closed within 0.7 s on 2026-11-28: tile under 1 day, rows 52.2.
- Chosen: the rows' (received to closed): it is the asset's turnaround. `received_at()` now lives in `headline.py` and both use it (naive dates read as UTC). Sub-label: "Median days from received to closed, N cases". Period and "opened" count still use `created_at`.
- A closed case with no close row is left out of the tile (the rows would age it to now); only odd data.

## Changes
- `backend/di/routes/screens/analytics.py`: pack-headline requires `analytics` / `waterfall`.
- `backend/di/services/screens/analytics_rows.py`: pack chart section `waterfall` (rows and CSV/export go through `select`); `row_count`; `channel_of`, `_route_name` falls back to the channel (`rerent:REQ-1` is Re-rent), route_id is the channel so the age key groups by it; `_received` uses `received_at`.
- `backend/di/services/questions/headline.py`, `tool_fleet.py`, `device.py`: days definition and note.
- Frontend `pages/analytics/data/dataView.ts` (`rowCount`), `DataTable.tsx`, `DataDrawer.tsx` (export toasts, filter line), `dataView.test.ts`. The age chart already shows the server's `name`, so the key, drawer chip and sentence follow.
- Tests: `test_analytics_pack_headline.py` (engineer 403 on headline, rows, CSV; planner.a and admin 200; tenant; tile equals median of rows' days; note), `test_analytics_rows.py` (row_count, "1 row" subtitle, route names).

## Checks
- api tests (rows, headline, screens_analytics): 491 passed; headline file rerun after the last edit: 12 passed.
- mypy (2 files): no issues; ruff check: All checks passed; ruff format --check: 11 files already formatted.
- vitest src/pages/analytics src/api: 53 files, 394 passed (data folder rerun after test fix: 22 passed).
- tsc (tsconfig.app.json): only `SetupMode.tsx(108,9)` TS2322, not mine.

## Left
- Headline `route_table` still groups by full route id (fine for tool fleet and device, whose ids have no suffix).
- Not checked in a browser; no smokes.
