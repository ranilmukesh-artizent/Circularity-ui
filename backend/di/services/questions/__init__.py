"""Registers the worked analytics questions of every pack (plan 9; P9-6.17 DV-13, P9-9.19, P9-10.17, P9-11.16).

The questions live in code, not in the pack JSON (the pack schema forbids extra fields; decision 26 Nov 2026): each pack
has one module here (`used_cars`, `telecom_network`, `medical_rental`) that calls `di.services.device.analytics.register`;
the device pack's own questions are in `di.services.device.analytics`. Importing this package imports them all, so
`analytics.REGISTRY` holds every pack's questions. Outside the case-store layer, so a question may read repositories.
Writes nothing.
"""

from di.services.device import analytics  # noqa: F401  (the device pack's own questions)
from di.services.questions import medical_rental, telecom_network, used_cars  # noqa: F401
