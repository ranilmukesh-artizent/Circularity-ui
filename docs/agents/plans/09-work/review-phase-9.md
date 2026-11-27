# Phase 9 review (P9-9.22): used cars

Reviewer: read-only code review (writer 85), 27 Nov 2026, on `lead-merge` (HEAD `76d6bd30`). Scope: the `P9-9.*` commits
(`04494320` pack, `aa16f763` intake, `fb2535c9`/`ce67a6a5`/`43481d72` gates, `ce59c4c2` valuer, `3031b7fd` lot and recon,
`f527617b` replay, `f7a2f02a` close, and the mocks). No test was run; every finding was checked by reading the code at the cited
line. The gate wording is title, odometer and recall law: To be reviewed by Kinective's Legal team before it is relied on.

## Findings

| # | Severity | Finding | File:line | Verified | Suggested action |
|---|---|---|---|---|---|
| 1 | P2 | The odometer exemption (old car) returns "pass" before the photo-against-lease comparison. A car that is exempt from the disclosure statement but whose photo reading differs from the lease record by more than the tolerance is not held for a second inspection. The exemption covers the statement, not the tamper check. To be reviewed by Kinective's Legal team before it is relied on. | `services/modeler/gate_checks/vehicle.py:160-161` (comparison at `:168-173`) | Yes | Needs a decision, then code: run the mismatch check before the exemption. |
| 2 | P2 | The recall check's age is not judged when the case carries no `gateNow` (`now is not None and ...`): a case read without the time passes with a stale or old check. | `services/modeler/gate_checks/vehicle.py:197` | Yes | Treat a missing `gateNow` as stale (ask for the check), or make `gate_hold` always set it. |
| 3 | P2 | An unknown lien reads as no lien: `lien_open = bool(data.get("lien_open"))`, and the replay does the same. A title service that answers `title_status: clear` without a lien flag clears G-VEH-TITLE. The mock writes both fields, a real source may not. | `services/cases/title_evidence.py:58`; `services/cases/car_facts.py:64`; `services/modeler/gate_checks/vehicle.py:95-105` | Yes | Keep `lien_open` as None when absent and let `title_result` fail it ("lien status not on file"). |
| 4 | P2 | Money is `Decimal` in the valuer and the close, but every figure leaves as `float` after a cent rounding, and the posted amount comes back through `Decimal(str(float))`. Only an input that is not a cent multiple can differ; the rounding is half up. Noted against the constraint, not a defect. | `services/modeler/valuers/used_cars.py:48-49`; `services/cases/close_used_cars.py:83-84`, `:300` | Yes | None, or carry strings through the held proposal. |

## Checked, no findings

- Money in `Decimal`: valuer `_d/_c` (`used_cars.py:35-60`), residual, excess mileage and wear (`close_used_cars.py:127-148`), all rounded half up to the cent.
- Agents never approve: `usedCar.post` is `HELD_FOR_PERSON` (every agent-prepared post becomes a proposal for Finance); `view.share`, `lot.approve` and the decision actions are in `FORBIDDEN_ACTIONS`; `usedCar.close` only prepares posts (`close_used_cars.py:155-197`, `forbidden.py`).
- Tenant boundary: the car's canonical records are keyed `schema.vin_key(org, vin)` (`canonical/schema.py:81`), so a VIN of another org is a different record; `usedCar.close` and `usedCar.post` are `scope="case"` (pipeline step 5) and refuse a case that is not a live used-car case.
- Review Focus 1: the title, odometer and recall gates are `Compliance` and locked in the pack (`packs/used_cars.json` guardrails); a diversion that skips a Compliance guardrail is refused by type (`services/modeler/overlay.py:202-206`), so G-VEH-BRAND being `locked: false` is not a gap.
- Open recall: an open recall that names no campaign is still open (`vehicle.py:200-203`, fix `43481d72`); a rental fleet of 35 or more is blocked on every route.
- Replay (Review Focus 9 and 3): `car_facts.replay_case` builds the same evidence a stored car has, from the history row only; no clock or session (`car_facts.py:46-88`).
- Parity: no file under `fixtures/golden/` changed in the range; the industrial pack is refused by a replay.

## Needs code

- F1 (decision first), F2, F3 as listed. F4: none.
