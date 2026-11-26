"""Test helper (plan 9, P9-6.6): put the device registry's check for an IMEI in the canonical store, as the dvreg adapter's
facts do (`condition.device_blacklist`, `device_lock`, `device_finance`, `registry_checked_at`). Since P9-6.6 a received
device with no registry check is held, so a test that opens a device case and wants a recommendation seeds a clear one."""

from datetime import timedelta

from di.core import clock
from di.core.db import SessionLocal
from di.services.canonical import store as canonical
from di.services.canonical.store import Fact


def seed_wipe(imei: str, *, verification: str = "pass", certificate_id: str | None = None, **over: str | None) -> dict:
    """Write the lab's data-wipe certificate (`condition.wipe_certificate`, as the dvlab adapter lands it); return it. Since
    P9-6.7 a received device with no certificate is held, so a test that wants a recommendation seeds one."""
    cert = {
        "certificate_id": certificate_id or f"WC-{imei[-5:]}", "method": "Purge", "tool_version": "4.2.1",
        "verification": verification, "operator": "OP-77", "at": clock.now().isoformat(),
    } | over  # fmt: skip
    with SessionLocal() as s:
        canonical.apply(s, "dvlab", [Fact("condition", f"IMEI:{imei}", "wipe_certificate", cert)])
        s.commit()
    return cert


def seed_registry(
    imei: str,
    *,
    days_ago: float = 1,
    blacklist: str = "clear",
    lock: str = "off",
    finance: str = "clear",
    wipe: bool = True,
    parts: str | None = "genuine",
) -> str:
    """Write the registry check; return its time (ISO). Also a passing wipe certificate unless `wipe` is false, so the
    tests of the registry gate (and the ones that only want a recommendation) are not held by the wipe gate, and a genuine
    parts declaration unless `parts` is None (GR-D9, P9-6.19: no declaration, no listing on Buy Now, Offers or Auction)."""
    at = (clock.now() - timedelta(days=days_ago)).isoformat()
    facts = {"device_blacklist": blacklist, "device_lock": lock, "device_finance": finance, "registry_checked_at": at}
    with SessionLocal() as s:
        canonical.apply(s, "dvreg", [Fact("condition", f"IMEI:{imei}", k, v) for k, v in facts.items()])
        s.commit()
    if parts is not None:
        with SessionLocal() as s:
            canonical.apply(s, "dvlab", [Fact("condition", f"IMEI:{imei}", "parts_status", parts)])
            s.commit()
    if wipe:
        seed_wipe(imei)
    return at
