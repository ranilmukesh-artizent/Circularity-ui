"""Test helper (plan 9, P9-6.6): put the device registry's check for an IMEI in the canonical store, as the dvreg adapter's
facts do (`condition.device_blacklist`, `device_lock`, `device_finance`, `registry_checked_at`). Since P9-6.6 a received
device with no registry check is held, so a test that opens a device case and wants a recommendation seeds a clear one."""

from datetime import timedelta

from di.core import clock
from di.core.db import SessionLocal
from di.services.canonical import store as canonical
from di.services.canonical.store import Fact


def seed_registry(imei: str, *, days_ago: float = 1, blacklist: str = "clear", lock: str = "off", finance: str = "clear") -> str:
    """Write the registry check; return its time (ISO)."""
    at = (clock.now() - timedelta(days=days_ago)).isoformat()
    facts = {"device_blacklist": blacklist, "device_lock": lock, "device_finance": finance, "registry_checked_at": at}
    with SessionLocal() as s:
        canonical.apply(s, "dvreg", [Fact("condition", f"IMEI:{imei}", k, v) for k, v in facts.items()])
        s.commit()
    return at
