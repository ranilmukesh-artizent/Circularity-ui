"""Masking of the sample records a test run shows a person (plan 9, P9-8.15; the masker is P9-8.2's).

Owns: `mask_samples`, which copies a run's `samples` ({node: {before, after, held}}) with every text value that is an email,
a phone number, a person's name or free text over 40 characters replaced by `«masked»` (`mapping_suggest.mask`). It
covers record data and canonical fact values; ids, resources and rejection reasons are shown as they are.
Never does: change what the engine holds or writes (a dry run's records stay as read), or mask numbers.
"""

from typing import Any

from di.connectors.mapping_suggest import mask

Samples = dict[str, dict[str, list[dict[str, Any]]]]


def _value(v: Any) -> Any:
    if isinstance(v, str):
        return mask(v)
    if isinstance(v, dict):
        return {k: _value(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_value(x) for x in v]
    return v


def _record(r: dict[str, Any]) -> dict[str, Any]:
    out = dict(r)
    if isinstance(r.get("data"), dict):
        out["data"] = _value(r["data"])
    if isinstance(r.get("facts"), list):
        out["facts"] = [{**f, "value": _value(f.get("value"))} for f in r["facts"]]
    return out


def mask_samples(samples: Samples) -> Samples:
    """The samples as a person may see them."""
    return {nid: {side: [_record(r) for r in recs] for side, recs in s.items()} for nid, s in samples.items()}
