# ruff: noqa: E501 - long lines in the docstring
"""The telecom replay of plan 9 (P9-10.13; registry entry I-16; story TN-20): the history imported and decided as telecom units.

    items(data)              `history.import_history` of the generator's rows (the ok items; none is held)
    telecom_case(case)       the replayed unit as the decider reads a telecom unit (see below)
    replay(items, flow_ver)  the as-of replay under the flow: a `TelecomReplay` with the report, the new spend avoided, the figures

The history is made by `di.services.modeler.replay_samples.telecom_network` (pure, `mulberry32(1404)`, 1,260 units from 5 to 24 Nov
2026; its shares are the knobs tuned until this replay gave the modelled figures: straight through 84 % +- 1 point, approvals 6 +- 1 a
business day, exceptions 4 +- 1, new spend avoided $1.1M +- 10 %). This half sits outside `di.services.modeler` because it runs the
decider and the replay, which the pure modeler layer may not import. Owns: the telecom case a replayed item is decided as (the gates
read evidence records, not facts, so the evidence a unit's facts name is laid in beside them, and the valuer's list-shaped inputs are
built from the scalar columns). Never does: change the replay (`di.services.replay.run` decides, measures and counts; the generator is
tuned, never it), read a clock or a database. The figures are *modelled*: the counterfactual value of a route not taken is an estimate.
Legal note: export and covered-equipment rules are the pack's data; Kinective's Legal team reviews them before reliance.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from di.repositories.replay import Batch
from di.services.cases.decide import Decision, decide_case
from di.services.modeler.compile import FlowVersion
from di.services.modeler.pack import Pack, load_pack
from di.services.modeler.replay_samples.telecom_network import PACK, rows
from di.services.replay import history
from di.services.replay import run as replay_run

NOW = datetime(2026, 11, 25, tzinfo=UTC)  # the day after the history ends: no row is dated in the future


def items(data: Sequence[Mapping[str, str]] | None = None, pack: Pack | None = None) -> list[dict[str, Any]]:
    """The ok items of `history.import_history` over the rows (it raises if any row is held: the data is clean)."""
    p = pack or load_pack(PACK)
    ok, held = history.import_history([dict(r) for r in (data if data is not None else rows())], p, now=NOW)
    if held:
        raise ValueError(f"{len(held)} rows held: {history.held_reasons(held)}")
    return ok


# ---------------------------------------------------------------- the case a replayed item is decided as
def _yes(v: Any) -> bool:
    return v is True or str(v).strip().lower() in ("yes", "true", "1")


def _record(kind: str, value: Mapping[str, Any], result: str = "pass") -> dict[str, Any]:
    return {"type": kind, "source": "history", "at": "2026-01-01T00:00:00+00:00", "result": result, "value": dict(value)}


def telecom_case(case: Mapping[str, Any]) -> dict[str, Any]:
    """The replayed unit as the decider reads a telecom unit: the facts as flat dotted names and as nested records, the list
    inputs of the valuer built from their scalar columns, and the evidence its facts name (the inventory's match, the bench's
    wipe, the vendor and facility papers, the export classification and screening, a disposal record). A fact the history does
    not hold is no evidence: an unmatched serial, a failed wipe or a bid not screened hold the unit as they do live."""
    c: dict[str, Any] = dict(case)
    model, serial = c.get("asset.model"), str(c.get("id"))
    c["demand.open_site_demand"] = _yes(c.get("demand.open_site_demand"))
    if (bid := c.get("market.broker_bid")) not in (None, ""):
        c["market.broker_bids"] = [{"bidId": f"B-{serial}", "unitPrice": bid, "qty": 1}]
    if (board := c.get("demand.board_value")) not in (None, ""):
        c["demand.board_needs"] = [{"part": "board", "value": board}]
    evidence: list[dict[str, Any]] = []
    if str(c.get("inventory.match")).lower() not in ("no", "false", "0"):
        inv = {"serial": serial, "model": model, "site": "SITE-1", "status": "removed",
               "manufacturer": c.get("asset.manufacturer"), "region": c.get("asset.region")}  # fmt: skip
        evidence.append(_record("inventory_match", inv))
    fails = int(c.get("config.wipe_fail_count") or 0)
    evidence.append(
        _record("config_wipe", {"status": "failed", "attempts": fails}, "fail")
        if fails
        else _record(
            "config_wipe",
            {
                "status": "verified",
                "attempts": 1,
                "scope": ["configuration", "credentials", "keys", "logs"],
                "certificate_ref": f"WC-{serial}",
            },
        )  # fmt: skip
    )
    evidence += [_record("vendor_certificate", {}), _record("treatment_facility_authorisation", {})]
    if c.get("asset.export_class"):
        screening = str(c.get("bid.screening") or "")
        evidence.append(
            _record(
                "export_classification",
                {
                    "export_class": c["asset.export_class"],
                    "class_source": "tn_inv",
                    "bid": {"id": f"B-{serial}", "screening": screening},
                },
            )  # fmt: skip
        )
    if _yes(c.get("disposal.record")):
        evidence.append(_record("disposal_record", {}))
    c["evidenceRecords"] = evidence
    c["network"] = {"model": model, "site": "SITE-1", "facts": [{"fact": "programme", "value": c.get("removal.programme") or ""}]}
    nested = dict(c)
    for k, v in c.items():
        if "." in k:
            group, _, name = k.partition(".")
            if isinstance(nested.get(group), dict) or group not in nested:
                nested.setdefault(group, {})[name] = v
    return nested


# ---------------------------------------------------------------- the replay
@dataclass(frozen=True)
class TelecomReplay:
    """A replay of the history under a flow, with the one figure the report does not carry (new spend avoided)."""

    report: replay_run.ReplayReport
    new_spend_avoided: float
    decided: dict[str, tuple[str | None, float]]  # item id -> (the route the flow chose, its net)
    basis: str = "modelled"

    def figures(self) -> dict[str, Any]:
        r = self.report
        return {"units": r.n_decided, "straight_through_pct": r.straight_through_pct, "approvals_per_day": r.approvals_per_day,
                "exceptions_per_day": r.exceptions_per_day, "new_spend_avoided": round(self.new_spend_avoided),
                "basis": self.basis}  # fmt: skip


def spend_avoided(d: Decision) -> float:
    """The "New spend avoided" of the route the decision chose (a reuse route's value line); 0 for any other route."""
    if d.route not in ("redeploy", "spare"):
        return 0.0
    chosen = next((r for r in d.routes if r["id"] == d.route), {})
    return sum(float(t["amt"]) for t in chosen.get("terms", []) if t.get("label") == "New spend avoided")


def replay(
    data: Sequence[Mapping[str, Any]],
    flow_ver: FlowVersion | None = None,
    *,
    pack: Pack | None = None,
    run_id: int = 0,
    session: Session | None = None,
) -> TelecomReplay:
    """The as-of replay (`di.services.replay.run.replay`, I-16) of `data` (`items()`) under `flow_ver` (default: the flow with no
    rules), each unit decided by the one decider as `telecom_case` builds it. Numbers are code; labelled *modelled*. With a
    `session` the canonical vendors are judged as at intake (review 13 F3)."""
    p = pack or load_pack(PACK)
    spent: list[float] = []
    chose: dict[str, tuple[str | None, float]] = {}

    def decide(case: Mapping[str, Any], pk: Pack, fv: FlowVersion, **kw: Any) -> Decision:
        d = decide_case(telecom_case(case), pk, fv, **kw)
        spent.append(spend_avoided(d))
        chose[str(case["id"])] = (d.route, d.net)
        return d

    first = min(i["decided_at"].date() for i in data)
    last = max(i["decided_at"].date() for i in data)
    batch = Batch(0, PACK, "history", len(data), 0, (first, last), {})
    report = replay_run.replay(
        batch, data, flow_ver or FlowVersion(None, 1, ()), pack=p, decide=decide, run_id=run_id, session=session
    )
    return TelecomReplay(report, round(sum(spent), 2), chose)
