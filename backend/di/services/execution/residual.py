"""The lease residual's gain or loss on the case (plan 9, P9-13.2, story X-13).

    residual_result(case, asset_answer) -> Residual | None   residual and proceeds of a leased asset, and the difference
    evidence(asset)                                          the case's `lease_residual` evidence record, from the asset's facts
    record(case, asset_answer)                               set `case["finance"]["residual"]` (the retire acknowledgement's call)

The residual is the lease contract's (`asset.lease_residual`, written by the lease adapter, read as the evidence of I-3 type
`lease_residual`: {contract_ref, residual, currency}); the proceeds are the ERP's answer to the retirement
(`case["finance"]["asset"]`, P9-13.1). `gain_loss = proceeds - residual`, in Decimal, rounded to cents. A case with no
`lease_residual` evidence, or no proceeds yet, has no residual line.

Never does: post anything (the used-car close's `residual` writer posts a lease return's gain or loss, P9-9.20: this is the
platform's read of the same difference on the case), touch an industrial lease, or read the store. Pure.
"""

from dataclasses import asdict, dataclass
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

from di.services.modeler.evidence import evidence_of

TYPE = "lease_residual"


@dataclass(frozen=True)
class Residual:
    contract_ref: str
    residual: Decimal
    proceeds: Decimal
    gain_loss: Decimal
    currency: str


def _money(v: Any) -> Decimal | None:
    try:
        return Decimal(str(v)).quantize(Decimal("0.01"), ROUND_HALF_UP) if v is not None else None
    except InvalidOperation:
        return None


def residual_result(case: dict[str, Any], asset_answer: dict[str, Any] | None) -> Residual | None:
    """The residual against the proceeds, or None when the case has no lease residual evidence or the ERP gave no proceeds."""
    ev = evidence_of(case, TYPE)
    if ev is None or ev.result != "pass":
        return None
    residual, proceeds = _money(ev.value.get("residual")), _money((asset_answer or {}).get("proceeds"))
    if residual is None or proceeds is None:
        return None
    return Residual(
        str(ev.value.get("contract_ref") or ""), residual, proceeds, proceeds - residual,
        str(ev.value.get("currency") or (asset_answer or {}).get("currency") or "USD"),
    )  # fmt: skip


def evidence(asset: dict[str, Any], at: datetime | str, source: str = "lease") -> list[dict[str, Any]]:
    """The `lease_residual` evidence record of an asset with the lease's `lease_ref` and `lease_residual` ([] otherwise)."""
    if not asset.get("lease_ref") or _money(asset.get("lease_residual")) is None:
        return []
    return [{
        "type": TYPE, "result": "pass", "at": at.isoformat() if isinstance(at, datetime) else at, "source": source,
        "value": {"contract_ref": asset["lease_ref"], "residual": float(asset["lease_residual"]),
                  "currency": asset.get("lease_residual_currency") or "USD"},
    }]  # fmt: skip


def record(case: dict[str, Any], asset_answer: dict[str, Any] | None) -> None:
    """Store `finance.residual` (floats, for the case's JSON) when the case has one; leave the case as it was otherwise."""
    r = residual_result(case, asset_answer)
    if r is not None:
        d = asdict(r)
        stored = {k: (float(v) if isinstance(v, Decimal) else v) for k, v in d.items()}
        case["finance"] = {**(case.get("finance") or {}), "residual": stored}
