"""Decontamination log mock (plan 9, P9-11.3): the medical-device rental company's cleaning records, synthetic.

Not a demo source: it is registered in sim/core/registry.py EXTRA_SYSTEMS (source id `mr_decon`, schema `decon_log`), so
the demo's 21 systems, its screens and its counts stay as they were. di reads it through its adapter
(backend/di/connectors/adapters/decon_log.py), which maps a cycle to `condition.decon_*` facts keyed by device tag. It reads
like an ordinary JSON API (camelCase); there is no real log behind it.

    GET  /decon-log/api/cycles?tag=&updatedSince=   the finished cycles, oldest end first
                                                     [{cycleId, tag, method, enhanced, cycleStartedAt, cycleEndedAt,
                                                       operatorRef, result}]  method is `standard` or `enhanced`,
                                                     result `pass` or `fail`, timestamps ISO 8601 UTC
    POST /decon-log/api/cycles                      {tag, enhanced} schedules a cycle that ends 3 simulated hours later
                                                     and answers 202 {cycleId, tag, enhanced, status: "scheduled",
                                                     scheduledEndAt}; it is listed by GET only when it has ended

Auth: API key in `x-api-key` (demo key `mr_decon-demo-key`); 401 with an error body otherwise. Errors are
`{"error": {"code", "message"}}`. The list is a plain JSON array (small, no paging). `updatedSince` (ISO 8601 date or
timestamp, else 400) keeps the cycles whose record changed after it; `tag` is an exact match.

Two timestamps on purpose (MR-03): a cycle has a start and an end, and the gate that reads the log uses the END of the
cycle: a cycle that ended before the device was checked in does not clean the device that came back.

Write: the POST is idempotent for a tag that already has a scheduled cycle (it answers 200 with that cycle and schedules
nothing more). 422 for a body that is not valid (tag `SYN-MR-XX-0000` form, `enhanced` a boolean when given, default
false), 400 for a body that is not JSON. A cycle that ends (handler `decon_log.complete`, sim/core/scheduler.py) becomes
visible and writes the outbox event `decon.cycle.completed` {cycleId, tag, enhanced, result} (sim/core/events.py).

Data in Postgres schema `decon_log` (models.py, seed.py), fixed (no randomness). Tags are the rental system's returns
(`SYN-MR-IP-0001` ... `0045`, sim.vendors.medical_rental_system.seed), whose check-in times the cycles are placed against:
- `SYN-MR-IP-0005` (story MR-S4): its record ENDED BEFORE its check-in (6 hours before);
- `SYN-MR-IP-0020` ... `0025`: a batch of six returns with no record; four of them (`0020` ... `0023`) get theirs 6
  simulated hours after the seed is loaded (scheduled), `0024` and `0025` never do;
- every other return: one finished cycle that ended after its check-in (3.5 hours after); `0010` and `0011`, the
  isolation-ward returns, were cleaned with the enhanced protocol.

ASSUMPTION: the scheduled cycles of the batch end 6 hours after the seed is loaded (the simulated clock's time then) and
    started 3 hours before that; the other cycles are placed against the rental system's own fixed timeline (26 Nov
    2026), which does not follow the simulated clock.
ASSUMPTION: every seeded cycle passes; operators are codes (`OP-01` ... `OP-04`), no names.
ASSUMPTION: cycle ids are `DC-<tag number>` for the seeded cycles and `DC-1001`, `DC-1002` ... for the ones POSTed.
"""

from sim.core.mock import Mock
from sim.vendors.decon_log import routes, seed

MOCK = Mock("mr_decon", routes.router, seed.ensure, seed.reset, "Decontamination log (synthetic)")
