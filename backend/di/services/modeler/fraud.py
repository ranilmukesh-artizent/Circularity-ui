"""Fraud triage on intake (plan 9, P9-2.11; stories X-15 and DV-02; registry entries I-1 and I-3): the computed score of a
returned asset, from the pack's fraud rules.

Owns: `FraudRule` and `FraudRules` (the pack's part 13 data, `Pack.fraud`), `Signal`, `FraudResult`, the five signals
(`SIGNALS`) and `triage`.
Never does: read a session or the clock (the caller passes the case and the repeat-return counts), hold or release a case,
decline anything, or ask a model. This is the computed score; the model's review of fraud is P9-2.19 and can only add
caution to it (R16). A hold is a hold for a person: `fraud.release` and `fraud.reject` are in `FORBIDDEN_ACTIONS`
(di.services.actions.fraud).

Pack data: `fraud: {version, threshold, rules: [{id, signal, weight, params, source}]}`. A customer may move the threshold
inside the range the pack publishes as `customer_layer.params["fraud.threshold"]` (an overlay `set_param`); a pack with no
`fraud` part never holds a case. The signals read evidence records (I-3, `case["evidenceRecords"]`), so a pack adds a
signal by data only when it reads an evidence type:

    blacklisted             a `blacklist` record with `value.hit` true
    quote_mismatch          a `quote_check` record whose `value.declared` and `value.received` differ in `model` or `capacity`
    repeat_returns          `params.n` or more cases for the same asset key in `params.days` days (`history`, see below)
    refund_before_receipt   a `refund_record` whose `value.refunded_at` is before its `value.received_at`
    serial_not_on_contract  a `contract_clause` record with `value.serial_listed` false

`history` maps a window in days (as text, "90") to the number of cases of the asset key in that window, the current case
included (di.repositories.fraud_history). Asset keys are serials or salted hashes: no customer name, address or account
number enters a signal (organisation policy). Needs review by Kinective's Legal team before a customer relies on it.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from di.services.modeler.evidence import Evidence, evidence_of, parse_time

if TYPE_CHECKING:
    from di.services.modeler.pack import Pack

SignalId = Literal["blacklisted", "quote_mismatch", "repeat_returns", "refund_before_receipt", "serial_not_on_contract"]
SIGNALS: tuple[SignalId, ...] = (
    "blacklisted", "quote_mismatch", "repeat_returns", "refund_before_receipt", "serial_not_on_contract",
)  # fmt: skip
THRESHOLD_PARAM = "fraud.threshold"  # the key of `customer_layer.params` a pack publishes to let a customer move the threshold
QUOTE_FIELDS = ("model", "capacity")


class FraudRule(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    signal: SignalId
    weight: float = Field(gt=0, le=1)
    params: dict[str, Any] = Field(default_factory=dict)
    source: str

    @model_validator(mode="after")
    def _window(self) -> "FraudRule":
        if self.signal == "repeat_returns":
            n, days = self.params.get("n"), self.params.get("days")
            if not (isinstance(n, int) and isinstance(days, int) and not isinstance(n, bool) and not isinstance(days, bool)):
                raise ValueError(f"{self.id}: repeat_returns needs whole-number params n and days")
            if n < 2 or days < 1:
                raise ValueError(f"{self.id}: repeat_returns needs n of at least 2 and days of at least 1")
        return self


class FraudRules(BaseModel):
    """The pack's fraud part: the rule set version, the score a case is held at, and the weighted rules."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    version: str
    threshold: float = Field(gt=0)
    rules: list[FraudRule]

    @model_validator(mode="after")
    def _unique(self) -> "FraudRules":
        ids = [r.id for r in self.rules]
        if len(set(ids)) != len(ids):
            raise ValueError("fraud rule ids must be unique")
        return self


@dataclass(frozen=True)
class Signal:
    id: str
    fired: bool
    value: Any
    source: str
    at: datetime | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "fired": self.fired,
            "value": self.value,
            "source": self.source,
            "at": self.at.isoformat() if self.at else None,
        }


@dataclass(frozen=True)
class FraudResult:
    score: float
    signals: list[Signal]
    rule_version: str
    held: bool
    threshold: float = 0.0

    def fired(self) -> list[Signal]:
        return [s for s in self.signals if s.fired]

    def as_dict(self) -> dict[str, Any]:
        """JSON for the stage's run state and the hold's input: the fired signals only (what the person is shown)."""
        return {
            "score": self.score, "threshold": self.threshold, "rule_version": self.rule_version, "held": self.held,
            "signals": [s.as_dict() for s in self.fired()],
        }  # fmt: skip


def threshold_of(pack: "Pack") -> float:
    """The score a case is held at: the customer's `fraud.threshold` parameter when the pack publishes one, else the pack's."""
    own = pack.customer_layer.params.get(THRESHOLD_PARAM)
    return own.value if own is not None else (pack.fraud.threshold if pack.fraud else 0.0)


def _record(case: Mapping[str, Any], type: str) -> Evidence | None:
    return evidence_of(case, type)


def _blacklisted(rule: FraudRule, case: Mapping[str, Any], history: Mapping[str, int]) -> Signal:  # noqa: ARG001 - one signature per signal
    e = _record(case, "blacklist")
    hit = bool(e and e.value.get("hit"))
    return Signal(rule.id, hit, hit, e.source if e and e.source else rule.source, e.at if e else None)


def _differs(declared: Any, received: Any) -> list[str]:
    if not isinstance(declared, Mapping) or not isinstance(received, Mapping):
        return []
    return [
        k
        for k in QUOTE_FIELDS
        if k in declared and k in received and str(declared[k]).strip().lower() != str(received[k]).strip().lower()
    ]


def _quote_mismatch(rule: FraudRule, case: Mapping[str, Any], history: Mapping[str, int]) -> Signal:  # noqa: ARG001
    e = _record(case, "quote_check")
    diff = _differs(e.value.get("declared"), e.value.get("received")) if e else []
    return Signal(rule.id, bool(diff), diff, e.source if e and e.source else rule.source, e.at if e else None)


def _repeat_returns(rule: FraudRule, case: Mapping[str, Any], history: Mapping[str, int]) -> Signal:  # noqa: ARG001
    count = int(history.get(str(rule.params["days"]), 0))
    return Signal(rule.id, count >= int(rule.params["n"]), count, rule.source, None)


def _refund_before_receipt(rule: FraudRule, case: Mapping[str, Any], history: Mapping[str, int]) -> Signal:  # noqa: ARG001
    e = _record(case, "refund_record")
    refunded = parse_time(e.value.get("refunded_at")) if e else None
    received = parse_time(e.value.get("received_at")) if e else None
    early = bool(refunded and received and refunded < received)
    return Signal(rule.id, early, early, e.source if e and e.source else rule.source, e.at if e else None)


def _serial_not_on_contract(rule: FraudRule, case: Mapping[str, Any], history: Mapping[str, int]) -> Signal:  # noqa: ARG001
    e = _record(case, "contract_clause")
    off = bool(e and e.value.get("serial_listed") is False)
    return Signal(rule.id, off, off, e.source if e and e.source else rule.source, e.at if e else None)


_READERS = {
    "blacklisted": _blacklisted, "quote_mismatch": _quote_mismatch, "repeat_returns": _repeat_returns,
    "refund_before_receipt": _refund_before_receipt, "serial_not_on_contract": _serial_not_on_contract,
}  # fmt: skip


def repeat_windows(pack: "Pack") -> list[int]:
    """The windows in days the pack's `repeat_returns` rules count cases in (what the caller reads into `history`)."""
    return sorted({int(r.params["days"]) for r in pack.fraud.rules if r.signal == "repeat_returns"}) if pack.fraud else []


def triage(case: Mapping[str, Any], pack: "Pack", history: Mapping[str, int]) -> FraudResult:
    """The score of the case: the sum of the weights of the signals that fired; held when it reaches the threshold. Pure."""
    rules = pack.fraud
    if rules is None:
        return FraudResult(0.0, [], "", False)
    signals = [_READERS[r.signal](r, case, history) for r in rules.rules]
    score = round(sum(r.weight for r, s in zip(rules.rules, signals, strict=True) if s.fired), 4)
    threshold = threshold_of(pack)
    return FraudResult(score, signals, rules.version, score >= threshold, threshold)
