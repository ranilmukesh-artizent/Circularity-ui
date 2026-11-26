"""Registers the worked analytics questions of every pack (plan 9; P9-6.17 DV-13, P9-9.19, P9-10.17, P9-11.16).

The questions live in code, not in the pack JSON (the pack schema forbids extra fields; decision 26 Nov 2026): each pack
has one module `questions_<pack>.py` that calls `di.services.device.analytics.register`. Importing this module imports
them all, so `analytics.REGISTRY` holds every pack's questions. Writes nothing.
"""

from di.services.cases import questions_medical_rental, questions_telecom_network, questions_used_cars  # noqa: F401
from di.services.device import analytics  # noqa: F401  (the device pack's own questions)
