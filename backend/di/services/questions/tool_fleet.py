"""The headline of the tool fleet pack in Analytics (plan 11, D1): returned tools, where they went, what they recovered.

Rate: the reuse rate (cases routed to re-issue, refurbish, pool or sale, of the cases with a route). Days: received to closed.
Open: every case not closed. Arithmetic in `di.services.questions.headline`.
"""

from di.services.questions.headline import Spec

SPEC = Spec(
    key="tool_fleet",
    rate_id="reuse_rate",
    rate_label="Reuse rate",
    rate_classes=frozenset({"release", "refurbish", "reuse", "sale"}),
    rate_closed_only=False,
    days_label="Median days to close",
    days_classes=None,
    open_id="open",
    open_label="Still open",
    open_classes=None,
    open_live_only=False,
    route_word="route",
)
