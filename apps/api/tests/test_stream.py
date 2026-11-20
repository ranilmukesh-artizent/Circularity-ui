"""B15: live updates. Two sessions see each other's work within a second (docs/BACKEND_STEPS.md).

These tests talk to the running api server (the one in this container, port 8000) over real HTTP, because a stream
is a long-lived connection that the in-process TestClient cannot hold open alongside other requests. The worker is
stopped for the test run; approvals made here queue instructions that nobody sends, and the reset at the end clears
them.
"""

import json
import threading
import time

import httpx
import pytest

from tests import starting

API = "http://localhost:8000"


def token(user: str) -> str:
    r = httpx.post(f"{API}/api/auth/login", json={"username": user, "password": "x"})
    r.raise_for_status()
    return r.json()["access_token"]


class Listener:
    """One open stream, read in a thread; events are kept with the time they arrived."""

    def __init__(self, user: str, via_query: bool = False, last_event_id: int | None = None):
        self.user, self.events, self.comments = user, [], []
        self._stop = threading.Event()
        self._ready = threading.Event()
        params, headers = {}, {}
        t = token(user)
        if via_query:
            params["access_token"] = t
        else:
            headers["Authorization"] = f"Bearer {t}"
        if last_event_id is not None:
            headers["Last-Event-ID"] = str(last_event_id)
        self._thread = threading.Thread(target=self._run, args=(params, headers), daemon=True)
        self._thread.start()
        assert self._ready.wait(10), f"{user}: the stream did not open"

    def _run(self, params, headers):
        with httpx.stream("GET", f"{API}/api/stream", params=params, headers=headers, timeout=None) as r:
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
    planner, approver, other = Listener("planner-a"), Listener("approver"), Listener("planner-b")
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
    again = Listener("approver", via_query=True, last_event_id=before)  # also: the token as a query parameter
    try:
        assert again.wait_for(is_case("RT-1048", "action.decision.submit"), timeout=2)
    finally:
        again.close()


def test_a_warehouse_manager_sees_only_its_warehouse():
    wm2 = Listener("wm-2")  # Warehouse 2; RT-1048 is in Warehouse 1
    try:
        act("planner-a", "decision.submit", {"case_id": "RT-1048"})
        time.sleep(0.5)
        assert not [e for e in wm2.events if e[2]["case_id"] == "RT-1048"]
    finally:
        wm2.close()


def test_the_stream_needs_a_sign_in():
    assert httpx.get(f"{API}/api/stream").status_code == 401
    assert httpx.get(f"{API}/api/stream", params={"access_token": "nonsense"}).status_code == 401
