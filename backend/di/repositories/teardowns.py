"""The depot's teardown verdicts (canonical `repair_event`, kind `teardown`; plan 9, P9-3.1) as the remaining-life fit reads them.

Each verdict carries the org of its serial's contract (`contract_line.<serial>` -> `contract.owner_org`); a serial no contract
names is depot-wide history (org None). Read only.
"""

from sqlalchemy import text
from sqlalchemy.orm import Session

from di.services.modeler.evidence import parse_time
from di.services.models.rul import TeardownRow

_SQL = text(
    "SELECT e.data ->> 'serial', e.data ->> 'component', (e.data ->> 'run_hours')::float, e.data ->> 'verdict', "
    "e.data ->> 'observed_at', e.data ->> 'tool_class', k.data ->> 'owner_org' "
    "FROM canonical e "
    "LEFT JOIN canonical l ON l.model = 'contract_line' AND l.key = e.data ->> 'serial' "
    "LEFT JOIN canonical k ON k.model = 'contract' AND k.key = l.data ->> 'contract_id' "
    "WHERE e.model = 'repair_event' AND e.data ->> 'kind' = 'teardown' AND jsonb_typeof(e.data -> 'run_hours') = 'number' "
    "ORDER BY e.key"
)


def rows(s: Session) -> list[tuple[str, TeardownRow]]:
    """(tool class, verdict) of every teardown verdict that has a component, hours, a verdict and a date."""
    out = []
    for serial, comp, hours, verdict, seen, cls, org in s.execute(_SQL):
        at = parse_time(seen)
        if serial and comp and verdict and cls and at is not None:
            out.append((cls, TeardownRow(serial, comp, hours, verdict, at, org)))
    return out
