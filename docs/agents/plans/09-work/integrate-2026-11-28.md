# Integration, 28 Nov 2026 (lead-merge)

HEAD: see `git log` (report commit on top of ab285bf8, the SIM_PORT guard commit). Base was 470528db.

## Merges (in order, all without conflict)
1. wt91-smokes (fast-forward)
2. wt92-smokes
3. wt97-review13
4. wt98-p1fixes
5. wt96-gate
6. wt111-mr (with wt103, wt94, wt99, wt107)
7. wt109-p93 (with wt105, wt93, wt102)
8. wt110-repair (with wt106)

No conflicts: git merged every branch, including the smokes p9-3/4/6/8/9..12, by itself. No file was edited by hand during the merges.

## SIM_PORT guard
Added to smoke-mvp, smoke-p9-5, smoke-p9-8 and smoke-rt1048 (exit 2 when the web port is not 5173 and neither SIM_PORT nor SIM_URL is set); one commit, ab285bf8. Already guarded: p9-3, 4, 6, 9, 10, 11, 12. smoke-fabric and smoke-p9-1 (and the other smokes) do not call source-sim, so they have none. `node --check` passes on the four.

## Checks (private stack circsmk93, torn down with `down -v`)
- `wt-check.sh 93` on 15 files (adapter_medical_rental_system, agent_credentials, cr_execution, instructions_send, mr_routing, mr_service_planning, ns_bat, service_desk_options, tf_follow_through, tf_non_return, tf_paths, x14_vendor_qualification, x16_credit_settlement, ns_ind_parity, tn_replay): `127 passed`; ruff check, ruff format, mypy (619 files), lint-imports (6 kept, 0 broken), tsc -b, vitest related, eslint on changed files: all ok.
- `test_adapter_aws_iot.py`: refused by wt-check (it faults source-sim), run through `api-test.sh` on circsmk93: `8 passed`.
- source-sim: `tests/test_broker_marketplace.py tests/test_medical_rental_system.py tests/test_service_desk_mocks.py`: `22 passed`.
- `web-check.sh`: `tsc errors: 0`, `Test Files 150 passed (150)`, `Tests 987 passed (987)`. The script has no eslint or knip step; eslint ran only on changed files (via wt-check). Full-repo eslint and knip were not run.

## Not resolved / notes
- No failures, no order-dependent tests seen, nothing changed to fix a merge.
- Browser smokes were not run (not asked).