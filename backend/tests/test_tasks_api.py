"""Plan 2 task 4: CRUD over the job queue at /api/v1/tasks (Admin and Developer only); every write is an action
(task.enqueue, task.retry, task.cancel, task.reprioritise), journalled through the pipeline."""

from sqlalchemy import text

from di.core import jobs
from di.core.db import SessionLocal

URL = "/api/v1/tasks"


def _journal(action: str) -> int:
    with SessionLocal() as s:
        return s.execute(text("SELECT count(*) FROM action_journal WHERE action = :a"), {"a": action}).scalar()


def _set(job_id: int, status: str) -> None:
    with SessionLocal() as s:
        s.execute(text("UPDATE job SET status = :st WHERE id = :i"), {"st": status, "i": job_id})
        s.commit()


def test_a_planner_may_not_see_or_change_tasks(client, login):
    for method, url, body in (("get", URL, None), ("post", URL, {"kind": "ping"}), ("get", f"{URL}/1", None)):
        r = client.request(method, url, json=body, headers=login("planner.a"))
        assert r.status_code == 403, r.text
        assert r.json()["error"]["code"] == "out_of_scope"


def test_signed_out_is_401(client):
    assert client.get(URL).status_code == 401


def test_enqueue_returns_the_task_and_journals_it(client, login):
    before = _journal("task.enqueue")
    r = client.post(URL, json={"kind": "ping", "payload": {"n": 1}, "priority": 7}, headers=login("developer"))
    assert r.status_code == 201, r.text
    t = r.json()
    assert {k: t[k] for k in ("kind", "payload", "status", "priority", "attempts", "max_attempts", "history")} == {
        "kind": "ping", "payload": {"n": 1}, "status": "queued", "priority": 7, "attempts": 0, "max_attempts": 5,
        "history": [],
    }  # fmt: skip
    assert set(t) == {"id", "kind", "payload", "status", "priority", "attempts", "max_attempts", "run_after",
                      "last_error", "history", "created_at", "updated_at"}  # fmt: skip
    assert _journal("task.enqueue") == before + 1
    got = client.get(f"{URL}/{t['id']}", headers=login("admin"))
    assert got.status_code == 200 and got.json()["id"] == t["id"]


def test_enqueue_with_a_dedupe_key_twice_makes_one_task(client, login):
    body = {"kind": "ping", "dedupe_key": "once"}
    a = client.post(URL, json=body, headers=login("developer")).json()
    b = client.post(URL, json=body, headers=login("developer")).json()
    assert a["id"] == b["id"]


def test_an_unknown_kind_is_422(client, login):
    r = client.post(URL, json={"kind": "no.such.kind"}, headers=login("developer"))
    assert r.status_code == 422, r.text
    assert r.json()["error"]["code"] == "validation_error"
    assert client.post(URL, json={}, headers=login("developer")).status_code == 422  # kind is required


def test_a_missing_task_is_404(client, login):
    assert client.get(f"{URL}/999999", headers=login("admin")).status_code == 404
    assert client.delete(f"{URL}/999999", headers=login("admin")).status_code == 404


def test_cancelling_a_running_task_is_409_and_a_queued_one_is_cancelled(client, login):
    with SessionLocal() as s:
        running = jobs.enqueue(s, "ping").id
        queued = jobs.enqueue(s, "ping").id
        s.commit()
    _set(running, "running")
    before = _journal("task.cancel")
    r = client.delete(f"{URL}/{running}", headers=login("developer"))
    assert r.status_code == 409, r.text
    assert r.json()["error"]["code"] == "conflict"
    r = client.patch(f"{URL}/{queued}", json={"action": "cancel"}, headers=login("developer"))
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "cancelled"
    assert _journal("task.cancel") == before + 1  # the refusal is not journalled


def test_retrying_a_dead_task_queues_it_again(client, login):
    with SessionLocal() as s:
        job_id = jobs.enqueue(s, "ping", max_attempts=1).id
        s.commit()
        jobs.fail(s, jobs.claim(s), "boom")
        s.commit()
    before = _journal("task.retry")
    r = client.patch(f"{URL}/{job_id}", json={"action": "retry"}, headers=login("admin"))
    assert r.status_code == 200, r.text
    t = r.json()
    assert (t["status"], t["attempts"], t["history"][0]["error"]) == ("queued", 0, "boom")
    assert _journal("task.retry") == before + 1
    again = client.patch(f"{URL}/{job_id}", json={"action": "retry"}, headers=login("admin"))
    assert again.status_code == 409  # a queued task is not retried


def test_reprioritise_a_queued_task(client, login):
    with SessionLocal() as s:
        job_id = jobs.enqueue(s, "ping").id
        s.commit()
    before = _journal("task.reprioritise")
    r = client.patch(f"{URL}/{job_id}", json={"action": "reprioritise", "priority": 3}, headers=login("developer"))
    assert r.status_code == 200 and r.json()["priority"] == 3
    assert _journal("task.reprioritise") == before + 1
    r = client.patch(f"{URL}/{job_id}", json={"action": "reprioritise"}, headers=login("developer"))
    assert r.status_code == 422  # a priority is needed
    assert client.patch(f"{URL}/{job_id}", json={"action": "explode"}, headers=login("developer")).status_code == 422


def test_list_filters_and_pages(client, login):
    with SessionLocal() as s:
        ids = [jobs.enqueue(s, "ping", {"n": n}).id for n in range(5)]
        other = jobs.enqueue(s, "sync.source", {"source_id": "none"}).id
        s.commit()
    _set(ids[0], "done")
    hdr = login("developer")
    seen: list[int] = []
    cursor = None
    while True:
        params = {"kind": "ping", "limit": 2} | ({"cursor": cursor} if cursor else {})
        page = client.get(URL, params=params, headers=hdr).json()
        assert len(page["items"]) <= 2
        seen += [t["id"] for t in page["items"]]
        cursor = page["next_cursor"]
        if cursor is None:
            break
    assert seen == sorted(ids, reverse=True)  # newest first, every ping once, not the sync
    queued = client.get(URL, params={"status": "queued"}, headers=hdr).json()["items"]
    assert {t["id"] for t in queued} == set(ids[1:]) | {other}
    assert client.get(URL, params={"limit": 0}, headers=hdr).status_code == 422
