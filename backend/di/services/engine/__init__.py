"""The decision engine (docs/backend-steps.md, B10): pure functions ported from the demo (`index.html`).

- `routes`: a route's net and P10/P50/P90 range (`mkRoute`), a failed gate (`fail`), ranking (`rankRoutes`)
- `gates`: the six gates and the rules that exclude a route (the gate checks in `buildRoutes`)
- `predictor`: the value of each route's terms, behind the `Predictor` interface (`buildRoutes`' formulas)
- `evaluate`: one case from route drafts to ranked routes and a recommendation
- `scenario`: what-if re-ranking under changed assumptions (`case.whatIf`)
- `pool`: the pool optimiser, an exact search over unit allocations (`solvePool`)

Nothing here reads a database or the clock; callers pass the case in. Numbers follow JavaScript's rounding
(`jsmath.js_round`), so the engine gives the demo's figures to the dollar.
"""
