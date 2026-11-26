"""Downstream vendor qualification with certificate dates (plan 9, P9-13.3, story X-14; builds on the gate G-DS-1 of I-2). Pure.

    qualify(vendors, route, as_of) -> list[VendorCheck]   each vendor of the route's `downstream_roles`, with why
    chosen(vendors, route, as_of) -> dict | None          the best qualified vendor's check (the decision's `vendor_check`)

`vendors` are the canonical `vendor` records (`id`, `name`, `role`, `cert_ref`, `cert_standard`, `cert_status`,
`cert_valid_to`,
and `rate` when the route has a rate to rank by). A vendor qualifies when its certificate status is approved and `cert_valid_to`
is on or after `as_of`, the decision date (a replay as of an earlier date judges on that date). Reasons: "<name>'s <standard>
certificate <ref> expired on <d MMM yyyy>." or "<name> has no certificate on file."; a certificate that is not approved says
its status. The best qualified vendor has the highest `rate`, the first listed on a tie.
Never does: read the store or the clock, write a case, or choose a route. R2v3, e-Stewards and ISO 14001 are research summaries:
Kinective's Legal team reviews the wording before it is relied on.
"""

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import date, datetime
from typing import Any

# `lapsed`/`expired` only say the certificate ran out (today's read): the date decides, so an earlier replay still qualifies
DATED = frozenset({"approved", "active", "certified", "valid", "lapsed", "expired"})


@dataclass(frozen=True)
class VendorCheck:
    vendor_id: str
    name: str
    qualified: bool
    cert_ref: str | None
    cert_standard: str | None
    valid_to: date | None
    reason: str


def _date(v: Any) -> date | None:
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v)[:10]) if v else None
    except ValueError:
        return None


def show(d: date) -> str:
    """`12 Aug 2026`."""
    return f"{d.day} {d:%b %Y}"


def _check(v: Mapping[str, Any], as_of: date) -> VendorCheck:
    name = str(v.get("name") or v.get("id") or "Vendor")
    ref, std, valid_to = v.get("cert_ref") or None, v.get("cert_standard") or None, _date(v.get("cert_valid_to"))
    status = str(v.get("cert_status") or "").strip().lower()
    head = (str(v.get("id") or ""), name)

    def out(ok: bool, reason: str) -> VendorCheck:
        return VendorCheck(*head, ok, ref, std, valid_to, reason)

    if not ref or valid_to is None:
        return out(False, f"{name} has no certificate on file.")
    what = f"{name}'s {std} certificate {ref}" if std else f"{name}'s certificate {ref}"
    if valid_to < as_of:
        return out(False, f"{what} expired on {show(valid_to)}.")
    if status not in DATED:
        return out(False, f"{what} is {status or 'not approved'}.")
    return out(True, f"{name} · {std + ' ' if std else ''}{ref} valid to {show(valid_to)}")


def qualify(vendors: Sequence[Mapping[str, Any]], route: Mapping[str, Any], as_of: date) -> list[VendorCheck]:
    """A check for each vendor whose `role` is in the route's `downstream_roles` (module docstring)."""
    roles = set(route.get("downstream_roles") or ())
    return [_check(v, as_of) for v in vendors if v.get("role") in roles]


def chosen(vendors: Sequence[Mapping[str, Any]], route: Mapping[str, Any], as_of: date) -> dict[str, Any] | None:
    """The check of the best qualified vendor (highest `rate`, the first on a tie) as a dict, with the route id; None when no
    vendor qualifies."""
    roles = set(route.get("downstream_roles") or ())
    best: tuple[float, VendorCheck] | None = None
    for v in (x for x in vendors if x.get("role") in roles):
        c = _check(v, as_of)
        rate = v.get("rate")
        score = float(rate) if isinstance(rate, int | float) and not isinstance(rate, bool) else 0.0
        if c.qualified and (best is None or score > best[0]):
            best = (score, c)
    if best is None:
        return None
    return {**asdict(best[1]), "valid_to": best[1].valid_to.isoformat() if best[1].valid_to else None, "route": route.get("id")}
