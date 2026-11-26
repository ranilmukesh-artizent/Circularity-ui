"""Worked analytics questions of the used_cars pack (plan 9, P9-9.19; the shape of P9-6.17, DV-13).

Each question is a pure function of typed rows returning `di.services.device.analytics.Answer`, wrapped in a
`WorkedQuestion` whose compute loads only the rows its `Scope` allows (R21) and registered with `analytics.register`.
Imported by `di.services.questions`, so the action `device.question` and Ask's `device_question` tool answer it by id.
Filled by P9-9.19; empty until then.
"""
