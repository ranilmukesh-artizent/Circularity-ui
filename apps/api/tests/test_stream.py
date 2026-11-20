"""B15: live updates. Two sessions see each other's work within a second (docs/backend-steps.md).

These tests talk to the running api server (the one in this container, port 8000) over real HTTP, because a stream
is a long-lived connection that the in-process TestClient cannot hold open alongside other requests. The worker is
stopped for the test run; approvals made here queue instructions that nobody sends, and the reset at the end clears
them.
"""

import json
import threading
import time
from datetime import UTC, datetime, timedelta

import httpx
import jwt
import pytest

from di.config import get_settings
from tests import starting

API = "http://localhost:8000"


def token(user: str) -> str:
    r = httpx.post(f"{API}/api/auth/login", json={"username": user, "password": "x"})
    r.raise_for_status()
    return r.json()["access_token"]


def ticket(user: str) -> str:
    """A stream ticket, as the browser gets one before it opens EventSource (F3)."""
    r = httpx.post(f"{API}/api/auth/stream-ticket", headers={"Authorization": f"Bearer {token(user)}"})
    r.raise_for_status()
    return r.json()["ticket"]


def forged_ticket(sub: str = "admin", seconds: float = 60, **claims) -> str:
    """A ticket signed with the api's secret (the tests share the api's settings), with a chosen lifetime and claims."""
    now = datetime.now(UTC)
    base = {"sub": sub, "iat": now, "exp": now + timedelta(seconds=seconds), "iss": "di-api", "aud": "stream"}
    return jwt.encode(base | claims, get_settings().jwt_secret.get_secret_value(), "HS256")


class Listener:
    """One open stream, read in a thread; events are kept with the time they arrived.

    via: "header" (Authorization: Bearer, for non-browser clients) or "ticket" (?ticket=, as the browser does);
    params: the query string as given (a test's own ticket), instead of either.
    """

    def __init__(self, user: str, via: str = "header", last_event_id: int | None = None, params: dict | None = None):
        self.user, self.events, self.comments = user, [], []
        self._stop = threading.Event()
        self._ready = threading.Event()
        headers: dict[str, str] = {}
        if params is None:
            params = {}
            if via == "ticket":
                params["ticket"] = ticket(user)
            else:
                headers["Authorization"] = f"Bearer {token(user)}"
        if last_event_id is not None:
            headers["Last-Event-ID"] = str(last_event_id)
        self._thread = threading.Thread(target=self._run, args=(params, headers), daemon=True)
        self._thread.start()
        assert self._ready.wait(10), f"{user}: the stream did not open"

    def _run(self, params, headers):
        with httpx.stream("GET", f"{API}/api/stream", params=params, headers=headers, timeout=None) as r:  # noqa: S113 - a stream that stays open: no timeout on purpose
            assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
            msg: dict = {}
            for line in r.iter_lines():
                if self._stop.is_set():
                    return
                if line.startswith(":"):
                    self.comments.append(line)
                    self._ready.set()
                elif line == "":
                    if "data" in msg:
                        self.events.append((time.monotonic(), msg["event"], json.loads(msg["data"]), int(msg["id"])))
                    msg = {}
                else:
                    k, _, v = line.partition(": ")
                    msg[k] = v

    def wait_for(self, pred, timeout: float = 5.0):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            for t, kind, data, eid in self.events:
                if pred(kind, data):
                    return t, kind, data, eid
            time.sleep(0.02)
        return None

    def close(self):
        self._stop.set()


def act(user: str, action: str, body: dict) -> dict:
    r = httpx.post(f"{API}/api/actions/{action}", json=body, headers={"Authorization": f"Bearer {token(user)}"})
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture(autouse=True)
def fresh():
    starting.reset()
    yield
    starting.reset()


def is_case(case_id: str, type_: str):
    return lambda kind, d: kind == "journal" and d["case_id"] == case_id and d["payload"]["type"] == type_


def test_two_sessions_see_each_others_approvals_within_a_second():
    planner, approver, other = Listener("planner-a", via="ticket"), Listener("approver"), Listener("planner-b", via="ticket")
    try:
        t0 = time.monotonic()
        act("planner-a", "decision.submit", {"case_id": "RT-1048"})
        seen = approver.wait_for(is_case("RT-1048", "action.decision.submit"))
        assert seen is not None, "the Approver did not see the submission"
        assert seen[0] - t0 < 1.0, f"the Approver saw the submission after {seen[0] - t0:.2f} s"

        t1 = time.monotonic()
        act(
            "approver",
            "decision.approve",
            {"case_id": "RT-1048", "rationale": "Redeploy to Site 3 as recommended; evidence reviewed.", "reviewed": True},
        )
        seen = planner.wait_for(is_case("RT-1048", "action.decision.approve"))
        assert seen is not None, "the Planner did not see the approval"
        assert seen[0] - t1 < 1.0, f"the Planner saw the approval after {seen[0] - t1:.2f} s"
        # the stage move and the demo-shaped event arrive too
        assert planner.wait_for(lambda k, d: k == "journal" and d["payload"]["type"] == "case.stage_changed")
        assert planner.wait_for(lambda k, d: k == "event" and d["case_id"] == "RT-1048")

        # Customer B's planner sees nothing of Customer A's case
        time.sleep(0.3)
        assert not [e for e in other.events if e[2]["case_id"] == "RT-1048"]
    finally:
        for s in (planner, approver, other):
            s.close()


def test_a_reconnect_replays_what_was_missed():
    first = Listener("approver")
    try:
        act("planner-a", "decision.submit", {"case_id": "RT-1048"})
        hit = first.wait_for(is_case("RT-1048", "action.decision.submit"))
        assert hit is not None
    finally:
        first.close()
    before = hit[3] - 1  # resume just before the submission
    again = Listener("approver", via="ticket", last_event_id=before)  # also: a stream ticket in the query
    try:
        assert again.wait_for(is_case("RT-1048", "action.decision.submit"), timeout=2)
    finally:
        again.close()


def test_a_warehouse_manager_sees_only_its_warehouse():
    wm2 = Listener("wm-2", via="ticket")  # Warehouse 2; RT-1048 is in Warehouse 1
    try:
        act("planner-a", "decision.submit", {"case_id": "RT-1048"})
        time.sleep(0.5)
        assert not [e for e in wm2.events if e[2]["case_id"] == "RT-1048"]
    finally:
        wm2.close()


def test_the_stream_needs_a_sign_in():
    assert httpx.get(f"{API}/api/stream").status_code == 401
    assert httpx.get(f"{API}/api/stream", params={"ticket": "nonsense"}).status_code == 401
    assert httpx.get(f"{API}/api/stream", headers={"Authorization": "Bearer nonsense"}).status_code == 401


def test_the_url_takes_only_a_live_stream_ticket():
    access = token("admin")
    # the access token never goes in the URL: not as ?ticket=, and ?access_token= is gone (F3)
    assert httpx.get(f"{API}/api/stream", params={"ticket": access}).status_code == 401
    assert httpx.get(f"{API}/api/stream", params={"access_token": access}).status_code == 401
    # a ticket is not a bearer token, not even for the stream
    assert httpx.get(f"{API}/api/stream", headers={"Authorization": f"Bearer {ticket('admin')}"}).status_code == 401
    # expired, another issuer, an unknown account
    for bad in (forged_ticket(seconds=-5), forged_ticket(iss="someone-else"), forged_ticket(sub="nobody")):
        assert httpx.get(f"{API}/api/stream", params={"ticket": bad}).status_code == 401


def test_the_stream_outlives_its_ticket():
    short = Listener("admin", params={"ticket": forged_ticket("admin", seconds=2)})
    try:
        time.sleep(3)  # the ticket has expired; it is checked only when the stream opens
        act("planner-a", "decision.submit", {"case_id": "RT-1048"})
        assert short.wait_for(is_case("RT-1048", "action.decision.submit")) is not None
    finally:
        short.close()
