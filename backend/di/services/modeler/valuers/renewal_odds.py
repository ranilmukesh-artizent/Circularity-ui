"""The chance that a contract renews, from how its kind of contract ended before (plan 9, P9-5.4, story CR-04). Pure.

    size_band(lines) -> "small" | "medium" | "large"                         by the number of tools on the contract
    segment_of(market, lines) -> {"market", "size"}                         the segment a contract belongs to
    within(history, today, days=730) -> list[row]                           the ended contracts of the last two years
    likelihood(history, segment, with_proposal) -> (float, basis)           the segment's renewal rate, Laplace-smoothed

`history` is the fleet source's `history` resource as it was read (P9-3.1): per ended contract `{contractId, market, lines,
endedAt, outcome: renewed | lapsed, hadProposal, feeBefore, feeAfter}`. A row is in the segment when its market and its size band
(from `lines`) are the segment's; the history has no contract age, so there is no age band. The rate is
`(renewed + 1) / (n + 2)` over the rows of the segment that did, or did not, have a proposal: with no row it is 0.5, never a
guess dressed as data. The basis text names the segment and n and says the figure is "modelled, observational (A section 3.4)":
contracts with a proposal were not chosen at random, so the difference between the two rates is not proven cause.

Never does: read the database or the clock, call a model (a count and a ratio, so no `AgentLoop` belongs here: the odds are a
computed number and a model may never write one), or approve anything. It trains nothing, so there is no `model_version`.
"""

from collections.abc import Mapping, Sequence
from datetime import date, datetime, timedelta
from typing import Any

SIZE_BANDS = (("small", 6), ("medium", 12))  # under 6 tools, under 12, else large
CAVEAT = "modelled, observational (A section 3.4)"


def size_band(lines: int) -> str:
    for name, below in SIZE_BANDS:
        if lines < below:
            return name
    return "large"


def segment_of(market: str, lines: int) -> dict[str, str]:
    return {"market": market, "size": size_band(lines)}


def _ended(row: Mapping[str, Any]) -> date | None:
    raw = row.get("endedAt")
    try:
        return datetime.fromisoformat(str(raw)).date() if raw else None
    except ValueError:
        return None


def within(history: Sequence[Mapping[str, Any]], today: date, days: int = 730) -> list[Mapping[str, Any]]:
    """The rows that ended in the `days` before `today` (a row with no valid end date is left out)."""
    start = today - timedelta(days=days)
    return [r for r in history if (e := _ended(r)) is not None and start <= e <= today]


def likelihood(history: Sequence[Mapping[str, Any]], segment: Mapping[str, str], with_proposal: bool) -> tuple[float, str]:
    """The segment's renewal rate with (or without) a proposal, and the text that says where it comes from."""
    rows = [
        r
        for r in history
        if str(r.get("market")) == segment.get("market")
        and size_band(int(r.get("lines") or 0)) == segment.get("size")
        and bool(r.get("hadProposal")) == with_proposal
    ]
    renewed = sum(1 for r in rows if r.get("outcome") == "renewed")
    n = len(rows)
    p = (renewed + 1) / (n + 2)
    basis = (
        f"{segment.get('market')} contracts of {segment.get('size')} size, {n} ended in two years "
        f"{'with' if with_proposal else 'without'} a proposal, {renewed} renewed: {CAVEAT}"
    )
    return p, basis
