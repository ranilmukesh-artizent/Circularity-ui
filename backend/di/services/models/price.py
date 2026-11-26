"""The price model of a device (plan 9, P9-6.9, registry entry I-14 `PriceModel`; stories DV-06 and DV-14). Pure.

    PriceModel.fit(rows) -> PriceModel          three LightGBM quantile boosters, conformalised, with held-out metrics
    PriceModel.predict(facts, channel)          (p10, p50, p90) for one device on one channel
    PriceModel.save() / PriceModel.load(d)      the JSON artefact stored in `model_version.factors[0]["artefact"]`
    ModelPredictor(base, model, model_id)       a `Predictor` whose `channel_price` is the model's band; the rest is the base's

A row is `{model, storage_gb, grade, battery_band, functional_fails, age_months, channel, price, on}`: a settled sale of a
device with the lab's facts, or a weekly feed price (`channel` "feed", the lab facts None). Rows are ordered by `on`; the oldest
60% train the boosters (alpha 0.1, 0.5, 0.9: `n_estimators` 200, `learning_rate` 0.05, `num_leaves` 15, seed 7, deterministic,
one thread), the next 20% calibrate MAPIE's conformalised quantile regressor at confidence 0.80 and the newest 20% are the test
the metrics (`mae`, `mape`, interval `coverage`) are measured on. The artefact holds the three boosters as native model text,
the vocabularies of the categorical features and `qhat`, MAPIE's correction (the raw P10 less its lower bound, equal to the
upper bound less the raw P90 for the symmetric method; `fit` checks both). Prediction uses only LightGBM and `qhat`: MAPIE is
loaded in `fit`, never in a request. Categoricals are coded by position in the stored vocabulary; a value not seen in training
is coded -1, which LightGBM treats as missing.

Never does: read the database (`price_rows` does), promote itself (a person proposes and a different person approves,
`model.promote`; an agent never does), or call a language model. A trained statistical model, not a language model: no AgentLoop.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any

import lightgbm as lgb
import numpy as np
from lightgbm import LGBMRegressor

from di.services.engine.predictor import Asset, Predictor, PriceBand

FEATURES = ("model", "storage_gb", "grade", "battery_band", "functional_fails", "age_months", "channel")
CATEGORICAL = ("model", "grade", "battery_band", "channel")
CATEGORICAL_IDX = [FEATURES.index(f) for f in CATEGORICAL]
GRADES = ("A", "B", "C", "D")
BATTERY_BANDS = ("<80", "80-89", "90+")
CHANNELS = ("buynow", "offers", "auction", "market", "wholesale", "feed", "other")
QUANTILES = (0.1, 0.5, 0.9)
CONFIDENCE = 0.80
MIN_ROWS = 300
TOO_FEW = f"A price model needs at least {MIN_ROWS} settled sales or feed rows."
_NAMES = ("p10", "p50", "p90")
_NAN = float("nan")


def battery_band(pct: float | None) -> str | None:
    """The band of the lab's battery health reading: under 80, 80 to 89, 90 and over."""
    if pct is None:
        return None
    return BATTERY_BANDS[0] if pct < 80 else BATTERY_BANDS[1] if pct < 90 else BATTERY_BANDS[2]


def _code(vocab: Sequence[str], v: Any) -> float:
    return float(list(vocab).index(v)) if v in vocab else -1.0


def _num(v: Any) -> float:
    return _NAN if v is None else float(v)


def _vector(vocab: Mapping[str, Sequence[str]], facts: Mapping[str, Any], channel: str) -> list[float]:
    return [
        _code(vocab["model"], facts.get("model")),
        _num(facts.get("storage_gb")),
        _code(vocab["grade"], facts.get("grade")),
        _code(vocab["battery_band"], facts.get("battery_band")),
        _num(facts.get("functional_fails")),
        _num(facts.get("age_months")),
        _code(vocab["channel"], channel),
    ]


@dataclass
class PriceModel:
    vocab: dict[str, list[str]]
    boosters: dict[str, str]  # p10, p50, p90: LightGBM native model text
    qhat: float
    metrics: dict[str, Any]

    def __post_init__(self) -> None:
        self._b = {k: lgb.Booster(model_str=self.boosters[k]) for k in _NAMES}

    # ------------------------------------------------------------ predict
    def _matrix(self, x: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        lo, mid, hi = np.sort(np.stack([self._b[k].predict(x) for k in _NAMES]), axis=0)  # the quantiles do not cross
        mid = np.maximum(mid, 0.0)
        return np.maximum(np.minimum(lo - self.qhat, mid), 0.0), mid, np.maximum(hi + self.qhat, mid)

    def predict(self, facts: Mapping[str, Any], channel: str) -> tuple[float, float, float]:
        """(p10, p50, p90) price of the device on the channel, in the market's currency; p10 <= p50 <= p90."""
        p10, p50, p90 = self._matrix(np.array([_vector(self.vocab, facts, channel)]))
        return float(p10[0]), float(p50[0]), float(p90[0])

    # ------------------------------------------------------------ store
    def save(self) -> dict[str, Any]:
        return {
            "version": 1, "features": list(FEATURES), "vocab": self.vocab, "boosters": self.boosters, "qhat": self.qhat,
            "metrics": self.metrics,
        }  # fmt: skip

    @classmethod
    def load(cls, d: Mapping[str, Any]) -> "PriceModel":
        return cls(
            {k: list(v) for k, v in d["vocab"].items()}, dict(d["boosters"]), float(d["qhat"]), dict(d.get("metrics") or {})
        )

    # ------------------------------------------------------------ fit
    @classmethod
    def fit(cls, rows: Sequence[Mapping[str, Any]]) -> "PriceModel":
        """Train on `rows` (see the module doc); ValueError when there are fewer than `MIN_ROWS`."""
        if len(rows) < MIN_ROWS:
            raise ValueError(TOO_FEW)
        # loaded here only: no request needs MAPIE
        from mapie.regression import ConformalizedQuantileRegressor  # type: ignore[import-untyped]

        ordered = sorted(rows, key=lambda r: r["on"])
        n = len(ordered)
        i1, i2 = int(n * 0.6), int(n * 0.8)
        vocab = {
            "model": sorted({str(r["model"]) for r in ordered}),
            "grade": list(GRADES),
            "battery_band": list(BATTERY_BANDS),
            "channel": list(CHANNELS),
        }
        x = np.array([_vector(vocab, r, str(r["channel"])) for r in ordered])
        y = np.array([float(r["price"]) for r in ordered])
        base = LGBMRegressor(
            objective="quantile", alpha=0.5, n_estimators=200, learning_rate=0.05, num_leaves=15, random_state=7,
            deterministic=True, force_row_wise=True, n_jobs=1, verbose=-1,
        )  # fmt: skip
        cqr = ConformalizedQuantileRegressor(estimator=base, confidence_level=CONFIDENCE)
        cqr.fit(x[:i1], y[:i1], fit_params={"categorical_feature": CATEGORICAL_IDX})
        cqr.conformalize(x[i1:i2], y[i1:i2])
        # MAPIE keeps its three fitted boosters in the private `estimators_` (no public accessor); each carries its alpha.
        fitted = {round(float(e.get_params()["alpha"]), 1): e for e in cqr._mapie_quantile_regressor.estimators_}
        boosters = {k: fitted[q].booster_.model_to_string() for k, q in zip(_NAMES, QUANTILES, strict=True)}
        _, bounds = cqr.predict_interval(x[i1:i2], symmetric_correction=True)
        raw_lo, raw_hi = fitted[0.1].predict(x[i1:i2]), fitted[0.9].predict(x[i1:i2])
        down, up = raw_lo - bounds[:, 0, 0], bounds[:, 1, 0] - raw_hi
        qhat = float(down[0])
        if float(np.ptp(down)) > 1e-6 or float(np.abs(up - qhat).max()) > 1e-6:
            raise RuntimeError("MAPIE's symmetric correction is not one constant; the artefact cannot hold it")
        model = cls(vocab, boosters, qhat, {})
        p10, p50, p90 = model._matrix(x[i2:])
        yt = y[i2:]
        model.metrics = {
            "mae": float(np.mean(np.abs(p50 - yt))),
            "mape": float(np.mean(np.abs(p50 - yt) / np.maximum(yt, 1e-9))),
            "coverage": float(np.mean((yt >= p10) & (yt <= p90))),
            "target": CONFIDENCE, "n_train": i1, "n_conformalize": i2 - i1, "n_test": n - i2,
            "window": {"from": _day(ordered[0]["on"]), "to": _day(ordered[-1]["on"])},
        }  # fmt: skip
        return model


def _day(d: Any) -> str:
    return d.isoformat() if isinstance(d, date) else str(d)


class ModelPredictor:
    """The base predictor with the price model's band for `channel_price`; every other estimate is the base's (so a case's
    draws and every other number are unchanged). `facts` are the device's `model`, `storage_gb`, `grade`, `battery_band`,
    `functional_fails` and `age_months`; an optional `feed_week` (a date) is passed through to the band."""

    def __init__(self, base: Predictor, model: PriceModel, model_id: str | None = None):
        self.base, self.model, self.model_id = base, model, model_id

    def channel_price(self, facts: Mapping[str, Any], channel: str) -> PriceBand:
        p10, p50, p90 = self.model.predict(facts, channel)
        week = facts.get("feed_week")
        return PriceBand(p10, p50, p90, self.model_id, week if isinstance(week, date) else None)

    def market_value(self, a: Asset) -> float:
        return self.base.market_value(a)

    def sale(self, a: Asset, mv: float) -> tuple[int, int]:
        return self.base.sale(a, mv)

    def refurbishment(self, a: Asset, sale: int) -> tuple[int, int]:
        return self.base.refurbishment(a, sale)

    def avoided_purchase(self, a: Asset) -> int:
        return self.base.avoided_purchase(a)

    def prep_cost(self, a: Asset) -> int:
        return self.base.prep_cost(a)

    def service_cost(self, a: Asset) -> int:
        return self.base.service_cost(a)

    def residual(self, a: Asset) -> int:
        return self.base.residual(a)

    def lease_income(self, a: Asset) -> int:
        return self.base.lease_income(a)

    def parts_value(self, a: Asset, internal: bool) -> int:
        return self.base.parts_value(a, internal)

    def material(self, a: Asset) -> tuple[int, int]:
        return self.base.material(a)
