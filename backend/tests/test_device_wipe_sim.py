"""Plan 9, P9-6.2 (serial-only): a data-wipe certificate posted in the device lab mock lands in the canonical store within
one delta sync of `dvlab`. It changes the shared source-sim (it posts a wipe), so it resets the `dvlab` mock before and
after (`/_sim/reset`) and the parallel suite leaves it to the serial run (any file that calls `/_sim/`; the lead runs it
through api-test.sh). Skipped, with the reason, when source-sim does not serve the device mocks (restart it, R14).
Story id: DV-04.
"""

import httpx
import pytest
from sqlalchemy import text

from di.connectors.sync import run_sync
from di.core.config import get_settings
from di.core.db import SessionLocal, engine
from di.services.canonical import store
from tests import starting
from tests.helpers import call

SIM = get_settings().source_sim_url
LAB_API = SIM + "/device-lab/v1"


def served() -> bool:
    try:
        return httpx.get(LAB_API + "/tradeins", params={"limit": 1}, timeout=10).status_code in (200, 401)
    except httpx.HTTPError:
        return False


pytestmark = pytest.mark.skipif(not served(), reason="source-sim does not serve the device mocks: restart it (R14)")


def _reset_mock() -> None:
    httpx.post(SIM + "/_sim/reset", params={"system": "dvlab"}, timeout=60).raise_for_status()


def _clean() -> None:
    starting.reset()
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM provenance WHERE source_id = 'dvlab'"))
        conn.execute(
            text(
                "DELETE FROM canonical c WHERE c.model IN ('condition', 'asset') AND c.key LIKE 'IMEI:%' "
                "AND NOT EXISTS (SELECT 1 FROM provenance p WHERE p.model = c.model AND p.key = c.key)"
            )
        )


def setup_module():
    _reset_mock()
    _clean()


def teardown_module():
    _reset_mock()
    _clean()


def test_dv04_wipe_posted_in_the_mock_lands_its_certificate_within_one_sync():
    token = httpx.post(
        LAB_API + "/oauth/token",
        data={"grant_type": "client_credentials", "client_id": "di-connector", "client_secret": "dvlab-demo-secret"},
        timeout=10,
    ).json()["access_token"]
    head = {"Authorization": f"Bearer {token}"}
    assert call("source.reconnect", {"source_id": "dvlab"}, "developer")["ok"]
    assert run_sync("dvlab", "manual", full=True)["status"] == "ok"
    todo = httpx.get(LAB_API + "/tradeins", params={"batchId": "BATCH-0007", "limit": 200}, headers=head, timeout=30).json()[
        "items"
    ]
    with engine.connect() as conn:
        done = set(
            conn.execute(text("SELECT key FROM canonical WHERE model = 'condition' AND data ? 'wipe_certificate'")).scalars()
        )
    waiting = [t["imei"] for t in todo if f"IMEI:{t['imei']}" not in done]
    assert len(waiting) == 12  # the mock starts with 12 devices of BATCH-0007 without a certificate
    imei = waiting[0]
    posted = httpx.post(
        LAB_API + "/wipes",
        json={
            "imei": imei,
            "method": "Purge",
            "toolVersion": "4.2.1",
            "verification": "pass",
            "operator": "OP-77",
            "at": "2026-10-07T09:30:00+00:00",
        },
        headers=head,
        timeout=30,
    )
    assert posted.status_code in (200, 201), posted.text
    assert run_sync("dvlab", "webhook")["status"] == "ok"  # the delta sync the wipe event queues
    with SessionLocal() as s:
        rec = store.get(s, "condition", f"IMEI:{imei}")
    assert rec is not None
    cert = rec["data"]["wipe_certificate"]
    assert cert["operator"] == "OP-77" and cert["verification"] == "pass" and cert["method"] == "Purge"
