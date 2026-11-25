"""Rebuild `di/connectors/mapping_calibration.json` from the gold set (plan 9, P9-8.2). Deterministic: no clock, no random.

    python scripts/fit_mapping_calibration.py            # writes the JSON
    gold_set() / heldout(rows) / fit_all(rows)           # what the test recomputes

The gold set is the demo's Data Mapping rows of the 21 sources (fixtures/golden canonical.json) and the catalogue
templates' rows (di.connectors.catalog.maps): a source field, its sample value when the demo has one, and the canonical
field a person chose. Rows are held out by vendor family: the curve that scores a family's rows is fitted on the other
families' rows only. The pre-ticked threshold is the lowest held-out confidence from which at least 95 % of the rows are
right; no memory, no model (a model never sets a number).
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from di.connectors import catalog, isotonic, mapping, mapping_suggest
from di.core import golden
from di.repositories.reference import lists
from di.services.canonical.schema import MODEL_FIELDS, top_field

OUT = Path(__file__).resolve().parents[1] / "di" / "connectors" / "mapping_calibration.json"
PRECISION = 0.95
CHECK_FLOOR = 0.3
AGREE_BONUS, DISAGREE_FACTOR, MEMORY_BONUS = 0.03, 0.8, 0.05

Row = tuple[str, str, str, str | None]  # family, source field, canonical model.field, sample value


def family(vendor: str) -> str:
    return vendor.split()[0].lower()


def _truth(target: str) -> str | None:
    t = mapping._target(target)
    if t is None:
        return None
    model, field = t[0], top_field(t[1])
    return f"{model}.{field}" if field in MODEL_FIELDS.get(model, {}) else None


def gold_set() -> list[Row]:
    vendors = {s["id"]: s["vendor"] for s in golden.load("sources")["sources"]}
    vendors |= {c["id"]: c["vendor"] for c in lists()["CATALOG"]}
    rows: list[Row] = []
    for sid, maps in golden.load("canonical")["mappings"].items():
        for src, value, target, *_ in maps:
            if (t := _truth(target)) is not None:
                rows.append((family(vendors[sid]), src, t, str(value)))
    for sid in catalog.IDS:
        for r in catalog.maps(sid):
            if (t := _truth(f"{r['model']}.{r['field']}")) is not None:
                rows.append((family(vendors[sid]), r["src"], t, None))
    return rows


def scored(rows: list[Row]) -> list[tuple[str, float, int]]:
    """(family, score of the top candidate (`top_score`), 1 when that candidate is the person's choice) per row."""
    canon = mapping_suggest.canonical_fields()
    out = []
    for fam, src, truth, value in rows:
        p = mapping_suggest.profile([{src: value}] if value is not None else [], src)
        cands = mapping_suggest.raw_candidates(p, canon)
        out.append((fam, mapping_suggest.top_score(cands), int(cands[0].canon.target == truth)))
    return out


def heldout(rows: list[Row]) -> list[tuple[float, int]]:
    """(calibrated confidence, correct) per row, each from a curve fitted without its vendor family."""
    sc = scored(rows)
    out = []
    for fam in sorted({s[0] for s in sc}):
        rest = [s for s in sc if s[0] != fam]
        pts = isotonic.fit([s[1] for s in rest], [s[2] for s in rest])
        out += [(round(isotonic.lookup(pts, s[1]), 4), s[2]) for s in sc if s[0] == fam]
    return out


def threshold(held: list[tuple[float, int]], precision: float = PRECISION) -> float:
    """The lowest confidence from which the held-out rows are right at least `precision` of the time (2.0: none is)."""
    for t in sorted({c for c, _ in held}):
        above = [ok for c, ok in held if c >= t]
        if above and sum(above) / len(above) >= precision:
            return t
    return 2.0


def fit_all(rows: list[Row]) -> dict:
    sc = scored(rows)
    held = heldout(rows)
    return {
        "_note": "Written by backend/scripts/fit_mapping_calibration.py from the gold set; do not edit by hand.",
        "points": [list(p) for p in isotonic.fit([s[1] for s in sc], [s[2] for s in sc])],
        "pre_ticked": threshold(held),
        "check": CHECK_FLOOR,
        "agree_bonus": AGREE_BONUS,
        "disagree_factor": DISAGREE_FACTOR,
        "memory_bonus": MEMORY_BONUS,
        "gold": {
            "rows": len(rows),
            "families": len({r[0] for r in rows}),
            "top1_accuracy": round(sum(s[2] for s in sc) / len(sc), 4),
            "pre_ticked_support": sum(1 for c, _ in held if c >= threshold(held)),
        },
    }


def main() -> None:
    OUT.write_text(json.dumps(fit_all(gold_set()), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
