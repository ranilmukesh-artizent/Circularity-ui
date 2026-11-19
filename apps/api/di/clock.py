"""The workspace clock: what "now" is for every action (the journal's time, approval times, due dates).

The demo runs at a pinned as-of time (7 Oct 2026, 09:00 UTC), and its answers (approval times, "who acted when",
escalation clocks) depend on it. Until the backend follows source-sim's simulated clock (B13), now is that as-of
time, so the backend gives the demo's answers.
"""

from datetime import UTC, datetime

from di import golden


def as_of() -> datetime:
    return datetime.fromisoformat(golden.load("world")["as_of"].replace("Z", "+00:00")).astimezone(UTC)


def now() -> datetime:
    return as_of()
