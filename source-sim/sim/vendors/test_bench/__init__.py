"""Test bench mock (plan 9, P9-10.3): the bench results of returned telecom network equipment, synthetic: functional tests,
firmware, the data wipe and its evidence, boards, weight and battery.

Not a demo source: it is registered in sim/core/registry.py EXTRA_SYSTEMS (source id `tn_bench`, schema `test_bench`), so
the demo's 21 systems, its screens and its counts stay as they were. di reads it through its adapter
(backend/di/connectors/adapters/test_bench.py), which maps a result to `condition.*` facts and `asset.weight_kg`, keyed by
serial (schema.serial_key). No real bench, no real company; the wipe tool is a code (`WipeTool-X`).

    GET  /test-bench/api/results?serial=            one result (404 for an unknown serial); without `serial`, the page
                                                    {results, next} (`limit` 1-200, default 50, and `offset`)
    POST /test-bench/api/wipe-jobs      {serial}    a re-run: 201 with a running job; completes 4 simulated hours later
    POST /test-bench/api/refurb-orders  {serial}    idempotent on the serial
    POST /test-bench/api/teardowns      {serial, boards}  idempotent on the serial and the set of boards

A result is `{serial, tests: {passed, total}, firmware, firmwareLatest, wipe: {status: verified | failed | none, attempts,
tool, toolVersion, scope, verifiedAt, certificateRef}, boards: [{boardId, partNumber, health}], weightKg, battery:
{chemistry, damaged} | null}`. Auth: API key in `x-api-key` (demo key `tn_bench-demo-key`); 401 with an error body
otherwise. Errors are `{"error": {"code", "message"}}`. A write answers 201 with the new document, or 200 with the first
one for a repeat (a repeat wipe job while one runs gets the running job back). When a wipe job completes, the unit's wipe
is `verified` with `attempts` one higher, a certificate `WC-<number>` and the four-item scope; no other write changes a
result.

Data in Postgres schema `test_bench` (models.py, seed.py): results for `SN-TN-0001` ... `0040` and the power units `0100` ...
`0110`, fixed (no randomness). `0001` (`RRU-4410`): 18 of 18, wipe verified (`WC-0001`), firmware current. `0014`: wipe failed
once; `0015`: failed twice. `0040` (`RTR-880`): firmware 5.2, latest 7.1. Power units `0100`-`0110` have no wipe (`none`) and
carry a battery: `lithium` for `0100`-`0105` (`0103` damaged), `lead_acid` for the rest.

ASSUMPTION: the wipe scope of a verified wipe is configuration, credentials, keys, logs (the pack's evidence, not a
standard's wording; NIST SP 800-88 Rev. 2 has no router or switch appendix).
ASSUMPTION: `GET /results` without `serial` lists every result, so the adapter can read the bench in full.
"""

from sim.core.mock import Mock
from sim.vendors.test_bench import routes, seed

MOCK = Mock("tn_bench", routes.router, seed.ensure, seed.reset, "Test bench (synthetic)")
