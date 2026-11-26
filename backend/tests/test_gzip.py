"""Plan 3 task 1: JSON answers are gzip-compressed (>= 1000 bytes), streams never are (di.core.gzip)."""

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.testclient import TestClient

from di.core.gzip import NO_GZIP_PREFIXES, GzipExceptStreams
from tests.helpers import client, h

GZ = {"Accept-Encoding": "gzip"}


def test_a_large_json_answer_is_gzip_compressed():
    r = client.get("/api/screens/reference", headers={**h("admin"), **GZ})
    assert r.status_code == 200 and r.headers.get("content-encoding") == "gzip"
    assert r.json()  # the client inflated it


def test_a_small_answer_is_not_compressed():
    r = client.get("/api/health/live", headers=GZ)
    assert r.status_code == 200 and "content-encoding" not in r.headers


def test_ask_is_not_compressed():
    r = client.post("/api/ask", json={"question": "Brief me"}, headers={**h("planner.a"), **GZ})
    assert r.status_code == 200 and "content-encoding" not in r.headers


def test_the_live_stream_and_mcp_are_left_alone():
    assert {"/api/stream", "/api/ask", "/mcp"} <= set(NO_GZIP_PREFIXES)


def test_an_event_stream_is_never_compressed_wherever_it_is_served():
    app = FastAPI()

    @app.get("/anywhere")
    def anywhere():
        return StreamingResponse(iter(["data: " + "x" * 3000 + "\n\n"]), media_type="text/event-stream")

    app.add_middleware(GzipExceptStreams)
    r = TestClient(app).get("/anywhere", headers={**GZ, "Accept": "text/event-stream"})
    assert "content-encoding" not in r.headers and r.text.startswith("data: ")
