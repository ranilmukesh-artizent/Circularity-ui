"""The demo's reference lists (fixtures/golden/screens/reference.json, served by /api/screens/reference) and srcCh,
the channels a source offers."""

import re

from di.core import golden


def lists() -> dict:
    """Every reference list, keyed by the demo's name (cached by golden.load: treat as read-only)."""
    return golden.load("screens/reference")


def channels(s: dict) -> list[str]:
    """srcCh: api, event and file, from the source's mode and auth."""
    m = f"{s.get('mode', '')} {s.get('auth', '')}".lower()
    out = []
    if re.search("api|poll", m):
        out.append("api")
    if re.search("event|webhook", m):
        out.append("event")
    if re.search("csv|sftp", m):
        out.append("file")
    return out
