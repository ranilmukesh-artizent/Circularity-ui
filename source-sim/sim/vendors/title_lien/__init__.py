"""Title and lien service mock (plan 9, P9-9.3): the title status, brand and liens of the used-car segment's cars,
synthetic.

Not a demo source: it is registered in sim/core/registry.py EXTRA_SYSTEMS (source id `uc_title`, schema `title_lien`),
so the demo's 21 systems, its screens and its counts stay as they were. di reads it through its adapter
(backend/di/connectors/adapters/title_lien.py), which maps a title to `condition.*` facts keyed by VIN. It reads like an
ordinary JSON API (camelCase); there is no real title service, state agency or lender behind it, and a lien holder is a
code (`H-001` ...), never a name. It models generic evidence only: title, lien and brand rules are state law and differ
(plan 9 research B section 2.2, unconfirmed); any summary of them needs review by Kinective's Legal team.

    GET  /title-lien/api/v2/titles?updatedSince=&limit=&offset=   {items, next, total}
    GET  /title-lien/api/v2/titles/{vin}                           one title
    POST /title-lien/api/v2/lien-release-requests {vin, lienId}    202 {requestId}

A title: {vin, titleStatus: clear | lien | pending, brand: null | salvage | flood | rebuilt | buyback, brandSource:
state title | national title database (null without a brand), liens: [{lienId, holderRef, amount, released, releaseRef,
releasedAt}], checkedAt}. Auth: API key in `x-api-key` (demo key `uc_title-demo-key`); 401 with an error body otherwise.
Paging: `limit` 1-200 (default 25) and `offset`; `next` is the next offset or null. `updatedSince` (ISO 8601) keeps the
titles changed after it. Errors are `{"error": {"code", "message"}}`. A release request may carry an `Idempotency-Key`
header: a repeat answers 202 with the first request id.

Data in Postgres schema `title_lien` (models.py, seed.py): one title per VIN `SYNUC000000000001` ... `...100`, fixed (no
randomness). VINs ...003 and ...070 carry an open lien. The release of ...003 is scheduled 2 simulated days after the
clock's as-of time (handler `title_lien.release`): it sets `released`, `releaseRef` `LR-000003` and `releasedAt`, the
title becomes `clear`, and the outbox gets `title.lien.released` (source `uc_title`, subject the VIN). ...070 never
releases. ...021 carries brand `flood`, ...022 `rebuilt`, ...023 `salvage`. A lien release request is recorded and
answers 202; it changes nothing by itself (the lender's release is the scheduled one).

ASSUMPTION: no seeded title is `pending` (the status exists in the contract only); the brand sources are `state title` for
    ...021 and ...023 and `national title database` for ...022.
ASSUMPTION: the list answers `{items, next, total}` as the other used-car mocks do (the spec names the title document only).
"""

from sim.core.mock import Mock
from sim.vendors.title_lien import routes, seed

MOCK = Mock("uc_title", routes.router, seed.ensure, seed.reset, "Title and lien service (synthetic)")
