# Golden data for the screens (B14)

One script per area. Each imports `../golden-sandbox.mjs` (`freshDemo`, `plain`, `writeGolden`) and writes
`fixtures/golden/screens/<area>.json`: what the demo computes for that area's pages, for every account.

    node apps/web/scripts/golden/<area>.mjs
