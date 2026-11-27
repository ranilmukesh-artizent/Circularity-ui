"""The Workflow Studio's detail read of a workflow whose source is not in the demo's SOURCES (a source connected from the
catalogue, such as `fleet`): 200 with its graph and its template graph, not a 500 (`KeyError: 'fleet'` while the template
graph was built outside `live_sources`). Smokes p9-3 and p9-6 read `workflow.graph` from this response.
"""

import pytest

from tests.helpers import call, client, h

SID = "fleet"


@pytest.fixture
def workflow():
    assert call("source.reconnect", {"source_id": SID}, "developer")["ok"]
    r = call("workflow.create", {"type": "ingest", "src": SID}, "developer")
    assert r["ok"], r
    wid = r["output"]["id"]
    yield wid
    call("workflow.delete", {"id": wid}, "developer")


def test_detail_of_a_catalogue_source_workflow_has_its_graph(workflow):
    r = client.get(f"/api/screens/workflows/{workflow}", headers=h("developer"))
    assert r.status_code == 200, r.text
    d = r.json()
    conn = next(n for n in d["workflow"]["graph"]["nodes"] if n["k"] == "conn")
    assert conn["ref"] == SID
    assert any(n["k"] == "conn" and n["ref"] == SID for n in d["template"]["nodes"])
