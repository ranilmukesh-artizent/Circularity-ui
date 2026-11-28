"""The starting-state reset (tests/starting.py, run by scripts/dev/reset.sh) after a contract refresh was approved.

An approved refresh holds refurbished units for its org unit (`unit_reservation`, plan 9 P9-5.3). The reset removes every
org unit the seed does not have, so it must free those holds first: smoke-p9-5 approves FC-30117's proposal in
`tool-fleet-a`, and the next reset failed on the foreign key `unit_reservation_org_unit_id_fkey` (28 Nov, writer 116),
leaving the cases, approvals and instructions of the run in place for the next smoke.
"""

from sqlalchemy import text

from di.core.db import engine
from tests import starting

ORG = "t-reset-fleet"


def test_reset_frees_unit_reservations_before_it_removes_their_org_unit():
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO org_unit (id, parent_id, kind, name) VALUES (:o, 'workspace', 'company', 'Reset fleet') "
                 "ON CONFLICT (id) DO NOTHING"),
            {"o": ORG},
        )  # fmt: skip
        conn.execute(
            text("INSERT INTO unit_reservation (unit_id, org_unit_id, case_id, need_id, status, created_by) "
                 "VALUES ('RU-T001', :o, 'RT-T001', 'RT-T001:AGR-T001', 'held', 'test')"),
            {"o": ORG},
        )  # fmt: skip
    try:
        starting.reset()
        with engine.connect() as conn:
            assert conn.execute(text("SELECT count(*) FROM unit_reservation")).scalar_one() == 0
            assert conn.execute(text("SELECT count(*) FROM org_unit WHERE id = :o"), {"o": ORG}).scalar_one() == 0
    finally:
        with engine.begin() as conn:  # never leave the rows behind for the next test, whatever happened
            conn.execute(text("DELETE FROM unit_reservation WHERE org_unit_id = :o"), {"o": ORG})
            conn.execute(text("DELETE FROM org_unit WHERE id = :o"), {"o": ORG})
