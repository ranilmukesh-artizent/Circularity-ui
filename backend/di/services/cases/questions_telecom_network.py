"""Worked analytics questions of the telecom_network pack (plan 9, P9-10.17; the shape of P9-6.17, DV-13).

Each question is a pure function of typed rows returning `di.services.device.analytics.Answer`, wrapped in a
`WorkedQuestion` whose compute loads only the rows its `Scope` allows (R21) and registered with `analytics.register`.
Imported by `pack_questions`, so the action `device.question` and Ask's `device_question` tool answer it by id.
Filled by P9-10.17; empty until then.
"""
