"""The headline of the device recommerce pack in Analytics (plan 11, D1): devices, the channels they sold on, what they recovered.

Rate: sell-through (closed, of the cases routed to a sale channel). Days: received to closed on a sale channel. Still listed:
approved on a sale channel with the sale not yet reported. Arithmetic in `di.services.questions.headline`. (The device pack's
own worked questions are in `di.services.device.analytics`.)
"""

from di.services.questions.headline import Spec

SPEC = Spec(
    key="device",
    rate_id="sell_through",
    rate_label="Sell-through",
    rate_classes=frozenset({"sale"}),
    rate_closed_only=True,
    days_label="Median days to sell",
    days_classes=frozenset({"sale"}),
    open_id="listed",
    open_label="Still listed",
    open_classes=frozenset({"sale"}),
    open_live_only=True,
    route_word="channel",
)
