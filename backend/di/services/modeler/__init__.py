"""The Modeler's decision policy core (plan 8, phase 2): template packs, flow graphs, compiling a flow into business
rules, applying them after the gate rules, validation, guardrail checks and simulation.

Pure: no Session, no clock and no I/O beyond reading the packaged JSON and the golden files. Ported from the PO
prototype (`docs/reference/po-modeler/recover-app-prototype.html`) and tested against `fixtures/golden/po/`.
"""
