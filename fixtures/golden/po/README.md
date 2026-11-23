# PO prototype goldens

Reference data for plan 08 (decision platform MVP), dumped from the PO Modeler prototype
`docs/reference/po-modeler/recover-app-prototype.html`.

- Prototype SHA-256: `8b47425112a0b8f00243ac58841a61739254be7aef3d395c2eb47a8939efbab7`
- Written only by `frontend/scripts/dump-po-golden.mjs` (`cd frontend; node scripts/dump-po-golden.mjs`). Never
  hand-edit these files: change the script, re-run it, and check that the diff is only what you intended.
- The script opens the prototype from its `file://` URL in the installed Chrome, adds one line to the Recover app's
  script (a lookup of its closure names, before its final `render()`), and opens the app with its own "Open Recover"
  button. The prototype's seeds stay (`rng(26110)` for the tool-fleet cases, `rng(4242)` for the device lots).
  `Date.now` is pinned to `1767225600000`; the prototype never calls `Math.random`.
- Keys are sorted and numbers rounded to 1e-6, so two runs give byte-identical files.
- Checked by `backend/tests/test_po_golden.py`.

## Files

| File | What |
|---|---|
| `templates.json` | Per template `{key, name, sub, pre, paths, guards, dims, chips, in_prototype_tpl}`; `prototype_tpl_keys`; `ACTORS`, `CLSWORDS`, `FUNCS`, `SITES`. |
| `flows.json` | `tplEquip()` and `tplDevice()` (nodes `n`, edges `e`, `W`, `H`, `band`). |
| `equip_cases.json` | Every case in `CASES` (all fields, in the prototype's sorted order) and `open_ids` (`openCases()`). |
| `equip_decisions.json` | `liveRules()` and, per open case, `decide(c, P, liveRules())`: `best {k, net}`, applied rule ids, per path `{k, ok, net, why}`. |
| `device_lots.json` | `dLots()`. |
| `device_decisions.json` | `compileDevice(PUB.device)` and, per lot, `dDecide(l, base)` plus `dScore` for each channel. |
| `compile_cases.json` | `compileEquip` over 5 flows (below), with each flow. |
| `validate_cases.json` | `fValidate` over the same 5 flows. |
| `apply_cases.json` | `applyRules` on the first 6 open cases × 6 rule sets: the 5 compiled sets and `exclude_every_path` (one exclude per path: the waiver). Fresh `value(c, k, P)` per call. |
| `parse_cases.json` | `parseEquip` and `parseDevice` over the 8 sentences of the task. |
| `textguard_cases.json` | `textGuard` with `MD.tpl` set to `equip` and to `device`, over the same sentences. |
| `sim_cases.json` | `fSim` of the 4 edited flows against `PUB.equip`; `fSim` of the device rule "Lots over 45 days on hand: Auction only" (the flow `buildProposal` builds for it) against `PUB.device`. Flips as `{id, from, to}`. |
| `proposals.json` | `buildProposal(text)` for the 8 sentences, `MD.actor = "pshah"`, once with `MD.tpl = "equip"` and once with `"device"`: `kind, rid, label, msg, g, nid, node, checks, sim`. |

The 5 flows, each built from `PUB.equip`:

- `default`: the published flow.
- `r1_disconnected`: edge `gate>r1` removed and `gate>r2` added (so only BR-01 is cut off from the gate).
- `harvest_removed`: node `p-harvest` and its edges removed.
- `release_grade_c`: rule `r3` / `BR-03` `{action: "prefer", path: "release", scope: {grade: ["C"]}}` between `r2` and `dec`.
- `rule_without_path`: rule `r3` / `BR-03` `{action: "exclude", scope: {}}` with no path, between `r2` and `dec`.

## Where the prototype differs from the plan's spec (MVP-0.3)

The dump follows the prototype; these are recorded for the tasks that use the goldens.

1. **No `TPL.device`.** The prototype's `TPL` (line 2373) has only `equip`; `prototype_tpl_keys` records that. Its
   device engine exists (`GUARDS_D`, `DCH`, `DCN`, `ruleTextD`, `ruleGuardD`, `compileDevice`, `tplDevice`, `dLots`,
   `dDecide`), and `fValidate`, `fSim` and `buildProposal` reach it through `TPL[key]`. The script registers
   `TPL.device = {guards: GUARDS_D, paths: DCH, pname: k => DCN[k], text: ruleTextD, guard: ruleGuardD, compile:
   compileDevice, pre: "DR"}` (`pre` from `tplDevice`'s rule `DR-01`) so those functions run; `in_prototype_tpl` is
   `false` for it. The prototype gives the device template **no name or sub**, so `name` and `sub` are `null` (its
   texts call it "the device recommerce template"); a later task has to choose the name.
2. **No `dims` in `TPL`.** The scope dimensions are taken from the rule inspector's fields (lines 2510-2511):
   equip `cls, grade, ft, site, rulMax, rulMin`; device `brand, grade, band, dohMin, qtyMin`. The labels and the
   device brand and band values are copied from that markup in the script; the equip values are read from
   `CLSWORDS`, `FUNCS` and `SITES`.
3. **The app is in a `<template>`.** The Recover app (with `TPL`, `CASES`, …) is in `<template id="app-recover">` and
   runs only when mounted, inside one closure; hence the lookup line described above.
4. **"Prefer tool pool for grade A or B from Repair center" is `unclear` for equip.** `parseEquip` removes every
   `FUNCS` name from the text before it looks for a path, and "Tool pool" is a `FUNCS` name, so no path is found.
5. **"Skip approval for grade A"** is blocked by `textGuard` for both templates (GR-05 equip, GR-D6 device), so it
   never reaches the parser in `buildProposal`.
