"""B5c contract tests: call the AWS IoT Core mock the way an AWS SDK client does (SigV4, nextToken paging)."""

import base64
import json
from datetime import UTC, datetime, timedelta
from urllib.parse import quote, unquote

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from sim import scheduler, webhooks
from sim.db import engine
from sim.main import app
from sim.seed import seed
from sim.vendors.aws_iot.fleet import HANDLER, matches
from sim.vendors.aws_iot.sigv4 import sign
from sim.vendors.maximo.seed import run_hours_reading

KEY = ("AKIACIRCULARITYDEMO1", "circularity-demo/aws-iot/K7MDENG+bPxRfiCYDI")
VIEWER = ("AKIACIRCULARITYRDONL", "circularity-demo/aws-iot/readonly+R3AD0NLY")
SERVICE = {"iot": "iot", "data": "iotdata"}


RULE_NAMES = ("circularity_condition_events", "circularity_shadow_changes", "circularity_telemetry")
STARTING_RULES: dict[str, bool] = {}  # ruleDisabled per rule right after the reset


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        c.delete("/_sim/faults", params={"system": "iot"})
        c.post("/_sim/reset", params={"system": "iot"}).raise_for_status()
        STARTING_RULES.update({r["ruleName"]: r["ruleDisabled"] for r in call(c, "GET", "iot", "/rules").json()["rules"]})
        for name in RULE_NAMES:  # as di does when it connects the source; most tests watch the deliveries
            assert call(c, "POST", "iot", f"/rules/{name}/enable").status_code == 200
        yield c
        c.delete("/_sim/faults", params={"system": "iot"})
        c.post("/_sim/reset", params={"system": "iot"}).raise_for_status()


def call(client, method, plane, path, params=None, body=b"", key=KEY, service=None, now=None, region="ap-south-1"):
    """One signed request: plane is "iot" (control) or "data"; path is below the plane, already URL-encoded."""
    full = f"/aws-iot/{plane}{path}"
    pairs = [(k, str(v)) for k, v in (params or {}).items()]
    h = sign(method, unquote(full), pairs, "testserver", body, key[0], key[1], region, service or SERVICE[plane], now)
    return client.request(method, full, params=params, content=body or None, headers=h)


def code(r) -> str:
    return r.headers.get("x-amzn-ErrorType", "")


def all_pages(client, plane, path, key, params=None, size=None):
    out, token = [], None
    while True:
        p = dict(params or {})
        if size:
            p["maxResults"] = size
        if token:
            p["nextToken"] = token
        r = call(client, "GET", plane, path, p)
        assert r.status_code == 200, r.text
        body = r.json()
        out += body[key]
        token = body.get("nextToken")
        if not token:
            return out


def outbox(type_: str, after: int = 0) -> list[dict]:
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT data FROM sim.outbox WHERE source = 'iot' AND type = :t AND id > :a ORDER BY id"),
            {"t": type_, "a": after},
        )
        return [r.data for r in rows]


def last_outbox_id() -> int:
    with engine.connect() as conn:
        return conn.execute(text("SELECT coalesce(max(id), 0) FROM sim.outbox")).scalar_one()


# ---------------------------------------------------------------- auth
def test_sigv4_auth(client):
    r = client.get("/aws-iot/iot/things")
    assert r.status_code == 403 and code(r) == "MissingAuthenticationTokenException"
    assert r.json() == {"message": "Missing Authentication Token"} and r.headers["x-amzn-RequestId"]
    assert code(call(client, "GET", "iot", "/things", key=("AKIANOPE", "x"))) == "UnrecognizedClientException"
    bad = call(client, "GET", "iot", "/things", key=(KEY[0], "wrong-secret"))
    assert bad.status_code == 403 and code(bad) == "InvalidSignatureException" and "does not match" in bad.json()["message"]
    assert "correct service" in call(client, "GET", "iot", "/things", service="iotdata").json()["message"]
    assert "valid region" in call(client, "GET", "iot", "/things", region="eu-west-1").json()["message"]
    stale = call(client, "GET", "iot", "/things", now=datetime.now(UTC) - timedelta(minutes=20))
    assert stale.status_code == 403 and stale.json()["message"].startswith("Signature expired")
    # a query changed after signing breaks the signature
    h = sign("GET", "/aws-iot/iot/things", [("maxResults", "5")], "testserver", b"", *KEY, "ap-south-1", "iot")
    assert code(client.get("/aws-iot/iot/things", params={"maxResults": 6}, headers=h)) == "InvalidSignatureException"
    assert call(client, "GET", "iot", "/things", {"maxResults": 5}).status_code == 200
    # the viewer may list things but not read shadows
    assert call(client, "GET", "iot", "/things", key=VIEWER).status_code == 200
    denied = call(client, "GET", "data", "/things/cm-mtr-2041/shadow", key=VIEWER)
    assert denied.status_code == 401 and code(denied) == "UnauthorizedException"
    assert "iot:GetThingShadow" in denied.json()["message"]


# ---------------------------------------------------------------- control plane
def test_list_things_pages_and_filters(client):
    things = all_pages(client, "iot", "/things", "things", size=10)
    names = [x["thingName"] for x in things]
    assert len(names) == len(set(names)) == 77 and names == sorted(names)
    first = call(client, "GET", "iot", "/things", {"maxResults": 10}).json()
    assert len(first["things"]) == 10 and first["nextToken"]
    assert set(first["things"][0]) == {"thingName", "thingTypeName", "thingArn", "attributes", "version"}
    hero = call(client, "GET", "iot", "/things", {"attributeName": "assetTag", "attributeValue": "MTR-2041"}).json()["things"]
    assert [x["thingName"] for x in hero] == ["cm-mtr-2041"]
    pumps = all_pages(client, "iot", "/things", "things", {"thingTypeName": "HydraulicPumpMonitor"})
    assert pumps and all(x["attributes"]["assetTag"].startswith("PMP-") for x in pumps)
    prefix = call(client, "GET", "iot", "/things", {"attributeName": "siteCode", "attributeValue": "WH",
                                                    "usePrefixAttributeValue": "true", "maxResults": 250}).json()  # fmt: skip
    assert prefix["things"] and all(x["attributes"]["siteCode"].startswith("WH") for x in prefix["things"])
    assert code(call(client, "GET", "iot", "/things", {"maxResults": 251})) == "InvalidRequestException"
    assert call(client, "GET", "iot", "/things", {"nextToken": "garbage"}).status_code == 400
    # every motor and pump of the live cases has a kit, linked by its asset tag
    s = seed()
    tags = {x["attributes"]["assetTag"] for x in things}
    assert {c.facts.asset_id for c in s.cases.values() if c.facts.cls in ("motor", "pump")} <= tags


def test_describe_thing_and_groups(client):
    t = call(client, "GET", "iot", "/things/cm-mtr-2041").json()
    assert t["thingArn"] == "arn:aws:iot:ap-south-1:123456789012:thing/cm-mtr-2041" and t["defaultClientId"] == "cm-mtr-2041"
    assert t["attributes"] == {"assetTag": "MTR-2041", "assetClass": "motor", "siteCode": "WH01", "tenantCode": "customer-a",
                               "fleet": "motors", "sensorKit": "CMK-3"}  # fmt: skip
    missing = call(client, "GET", "iot", "/things/cm-nope")
    assert missing.status_code == 404 and code(missing) == "ResourceNotFoundException"
    groups = [g["groupName"] for g in all_pages(client, "iot", "/thing-groups", "thingGroups")]
    assert {"northfield-condition-monitoring", "returned-assets", "in-service-pilot", "returned-WH01"} <= set(groups)
    kids = call(client, "GET", "iot", "/thing-groups", {"parentGroup": "returned-assets"}).json()["thingGroups"]
    assert {g["groupName"] for g in kids} == {"returned-WH01", "returned-WH02", "returned-RC01"}
    g = call(client, "GET", "iot", "/thing-groups/returned-WH01").json()
    assert g["thingGroupMetadata"]["parentGroupName"] == "returned-assets"
    returned = all_pages(client, "iot", "/thing-groups/returned-assets/things", "things", {"recursive": "true"}, 20)
    pilot = all_pages(client, "iot", "/thing-groups/in-service-pilot/things", "things")
    assert len(returned) == 53 and len(pilot) == 24 and "cm-mtr-2041" in returned
    assert call(client, "GET", "iot", "/thing-groups/nope/things").status_code == 404


def test_jobs_and_rules(client):
    jobs = call(client, "GET", "iot", "/jobs").json()["jobs"]
    assert {j["jobId"]: j["status"] for j in jobs} == {"fw-2-4-1-rollout": "COMPLETED", "fw-2-5-0-pilot": "IN_PROGRESS"}
    assert [j["jobId"] for j in call(client, "GET", "iot", "/jobs", {"status": "IN_PROGRESS"}).json()["jobs"]] == [
        "fw-2-5-0-pilot"
    ]
    job = call(client, "GET", "iot", "/jobs/fw-2-5-0-pilot").json()
    d = job["job"]["jobProcessDetails"]
    assert job["documentSource"].endswith("cmk3-2.5.0.json")
    assert d["numberOfSucceededThings"] + d["numberOfQueuedThings"] + d["numberOfInProgressThings"] == 24
    assert call(client, "GET", "iot", "/jobs/nope").status_code == 404
    rules = call(client, "GET", "iot", "/rules").json()["rules"]
    assert {r["ruleName"]: r["topicPattern"] for r in rules} == {
        "circularity_condition_events": "dt/+/+/events",
        "circularity_shadow_changes": "$aws/things/+/shadow/update/documents",
        "circularity_telemetry": "dt/+/+/telemetry",
    }
    rule = call(client, "GET", "iot", "/rules/circularity_telemetry").json()["rule"]
    assert rule["sql"].endswith("FROM 'dt/+/+/telemetry'") and rule["actions"][0]["http"]["url"].startswith("https://")
    assert code(call(client, "GET", "iot", "/rules/nope")) == "UnauthorizedException"
    # not provisioned at start: every rule disabled until the integration enables it (EnableTopicRule)
    assert dict.fromkeys(RULE_NAMES, True) == STARTING_RULES
    assert all(r["ruleDisabled"] is False for r in rules)  # the fixture enabled them, as di's connect does
    denied = call(client, "POST", "iot", "/rules/circularity_telemetry/disable", key=VIEWER)
    assert denied.status_code == 401 and "iot:DisableTopicRule" in denied.json()["message"]
    assert code(call(client, "POST", "iot", "/rules/nope/enable")) == "UnauthorizedException"
    assert call(client, "POST", "iot", "/rules/circularity_telemetry/disable").status_code == 200
    assert call(client, "GET", "iot", "/rules/circularity_telemetry").json()["rule"]["ruleDisabled"] is True
    assert call(client, "GET", "iot", "/rules", {"ruleDisabled": "true"}).json()["rules"][0]["ruleName"] == "circularity_telemetry"
    mark = last_outbox_id()  # a disabled rule delivers nothing
    topic = quote("dt/motors/cm-mtr-2041/telemetry", safe="")
    assert call(client, "POST", "data", "/topics/" + topic, body=b'{"operatingHours": 1}').status_code == 200
    assert outbox("aws.iot.rule.circularity_telemetry", mark) == []
    assert call(client, "POST", "iot", "/rules/circularity_telemetry/enable").status_code == 200
    assert matches("dt/+/+/telemetry", "dt/motors/cm-mtr-2041/telemetry")
    assert not matches("$aws/things/+/shadow/update/documents", "$aws/things/x/shadow/name/condition/update/documents")
    assert matches("dt/#", "dt/a/b/c")


# ---------------------------------------------------------------- data plane
def test_shadows_hold_the_condition(client):
    r = call(client, "GET", "data", "/things/cm-mtr-2041/shadow", {"name": "condition"})
    assert r.status_code == 200, r.text
    sh = r.json()
    rep = sh["state"]["reported"]
    assert (rep["assetTag"], rep["operatingHours"], rep["dutyCyclePct"], rep["vibrationMmS"], rep["vibrationZone"],
            rep["bearingTempC"], rep["running"]) == ("MTR-2041", 18450.0, 96.4, 2.8, "B", 66.0, False)  # fmt: skip
    assert sh["metadata"]["reported"]["operatingHours"]["timestamp"] * 1000 <= rep["sampleAt"] + 999
    assert isinstance(sh["version"], int) and isinstance(sh["timestamp"], int) and "delta" not in sh["state"]
    classic = call(client, "GET", "data", "/things/cm-mtr-2041/shadow").json()
    assert classic["state"]["reported"]["connected"] is False and classic["state"]["desired"]["firmware"] == "2.4.1"
    names = call(client, "GET", "data", "/api/things/shadow/ListNamedShadowsForThing/cm-mtr-2041").json()
    assert names["results"] == ["condition"] and isinstance(names["timestamp"], int)
    nope = call(client, "GET", "data", "/things/cm-mtr-2041/shadow", {"name": "nope"})
    assert nope.status_code == 404 and code(nope) == "ResourceNotFoundException"
    # a pilot kit not yet on firmware 2.5.0 shows the pending firmware as delta
    pilot = all_pages(client, "iot", "/thing-groups/in-service-pilot/things", "things")
    deltas = [call(client, "GET", "data", f"/things/{n}/shadow").json()["state"].get("delta") for n in pilot]
    assert deltas.count({"firmware": "2.5.0"}) == 12 and deltas.count(None) == 12
    # every grade-D returned asset is in vibration zone D and has alarms
    d_cases = [c.facts.asset_id for c in seed().cases.values() if c.facts.cls in ("motor", "pump") and c.facts.grade == "D"]
    for a in d_cases:
        rep = call(client, "GET", "data", f"/things/cm-{a.lower()}/shadow", {"name": "condition"}).json()["state"]["reported"]
        assert rep["vibrationZone"] == "D" and any(e["type"] == "high-vibration" for e in rep["events"])


def test_hour_counters_agree_with_maximo_except_where_its_meter_is_old(client):
    s = seed()
    differ = []
    for c in s.cases.values():
        f = c.facts
        if f.cls not in ("motor", "pump"):
            continue
        rep = call(client, "GET", "data", f"/things/cm-{f.asset_id.lower()}/shadow", {"name": "condition"}).json()
        hours, meter = rep["state"]["reported"]["operatingHours"], float(run_hours_reading(f))
        if hours != meter:
            assert 1.03 * meter - 1 <= hours <= 1.08 * meter + 1, f.id
            differ.append(f.id)
    assert "RT-1048" not in differ and 4 <= len(differ) <= 10


def test_update_shadow_versions_delta_and_rule(client):
    path = "/things/cm-mtr-2041/shadow"
    v0 = call(client, "GET", "data", path).json()["version"]
    mark = last_outbox_id()
    body = json.dumps({"state": {"desired": {"telemetryIntervalSec": 900}}, "clientToken": "t-1"}).encode()
    r = call(client, "POST", "data", path, body=body)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["version"] == v0 + 1 and out["clientToken"] == "t-1" and out["metadata"]["desired"]["telemetryIntervalSec"]
    sh = call(client, "GET", "data", path).json()
    assert sh["state"]["delta"] == {"telemetryIntervalSec": 900}
    ev = outbox("aws.iot.rule.circularity_shadow_changes", mark)
    assert ev[-1]["thingName"] == "cm-mtr-2041" and ev[-1]["version"] == v0 + 1
    assert ev[-1]["state"]["desired"]["telemetryIntervalSec"] == 900
    clash = call(client, "POST", "data", path, body=json.dumps({"state": {"desired": {"x": 1}}, "version": v0}).encode())
    assert clash.status_code == 409 and code(clash) == "ConflictException"
    assert code(call(client, "POST", "data", path, body=b'{"nostate": 1}')) == "InvalidRequestException"
    assert call(client, "POST", "data", path, body=b"not json").status_code == 400
    # null removes a key; the delta goes away
    call(client, "POST", "data", path, body=json.dumps({"state": {"desired": {"telemetryIntervalSec": 3600}}}).encode())
    assert "delta" not in call(client, "GET", "data", path).json()["state"]
    assert call(client, "POST", "data", "/things/cm-nope/shadow", body=body).status_code == 404


def test_retained_messages_and_publish(client):
    topics = all_pages(client, "data", "/retainedMessage", "retainedTopics", size=50)
    by = {x["topic"]: x for x in topics}
    tel = by["dt/motors/cm-mtr-2041/telemetry"]
    assert tel["qos"] == 1 and tel["payloadSize"] > 0 and isinstance(tel["lastModifiedTime"], int)
    assert sum(1 for x in topics if x["topic"].endswith("/telemetry")) == 77
    r = call(client, "GET", "data", "/retainedMessage/" + quote("dt/motors/cm-mtr-2041/telemetry", safe=""))
    assert r.status_code == 200, r.text
    msg = r.json()
    payload = json.loads(base64.b64decode(msg["payload"]))
    assert (
        payload["operatingHours"] == 18450.0
        and payload["dutyCyclePct"] == 96.4
        and msg["lastModifiedTime"] == tel["lastModifiedTime"]
    )
    assert call(client, "GET", "data", "/retainedMessage/" + quote("dt/nope", safe="")).status_code == 404
    assert call(client, "GET", "data", "/retainedMessage", {"maxResults": 201}).status_code == 400
    # a device alarm published retained is kept and delivered by the events rule
    mark = last_outbox_id()
    alarm = {"eventId": "evt-test", "type": "over-temperature", "severity": "alarm", "ts": 1, "value": 93.0, "threshold": 90.0}
    topic = "dt/motors/cm-mtr-2041/events"
    r = call(client, "POST", "data", "/topics/" + quote(topic, safe=""), {"qos": 1, "retain": "true"}, json.dumps(alarm).encode())
    assert r.status_code == 200, r.text
    ev = outbox("aws.iot.rule.circularity_condition_events", mark)
    assert len(ev) == 1 and ev[0]["thingName"] == "cm-mtr-2041" and ev[0]["topic"] == topic and ev[0]["value"] == 93.0
    got = call(client, "GET", "data", "/retainedMessage/" + quote(topic, safe="")).json()
    assert json.loads(base64.b64decode(got["payload"]))["eventId"] == "evt-test"
    # not retained: delivered, not kept; reserved topics refused
    call(client, "POST", "data", "/topics/" + quote("dt/motors/cm-test/events", safe=""), body=json.dumps(alarm).encode())
    assert call(client, "GET", "data", "/retainedMessage/" + quote("dt/motors/cm-test/events", safe="")).status_code == 404
    r = call(client, "POST", "data", "/topics/" + quote("$aws/things/x/shadow/update", safe=""), body=b"{}")
    assert r.status_code == 403 and code(r) == "ForbiddenException"
    assert call(client, "POST", "data", "/topics/a", {"qos": 2}, b"{}").status_code == 400


def test_online_kits_report_on_the_simulated_clock(client):
    pilot = sorted(all_pages(client, "iot", "/thing-groups/in-service-pilot/things", "things"))
    name = pilot[0]
    before = call(client, "GET", "data", f"/things/{name}/shadow", {"name": "condition"}).json()
    mark = last_outbox_id()
    client.post("/_sim/clock/advance", json={"hours": 2, "minutes": 5}).raise_for_status()
    scheduler.tick()
    after = call(client, "GET", "data", f"/things/{name}/shadow", {"name": "condition"}).json()
    rb, ra = before["state"]["reported"], after["state"]["reported"]
    assert after["version"] > before["version"] and ra["sampleAt"] > rb["sampleAt"]
    elapsed_h = (ra["sampleAt"] - rb["sampleAt"]) / 3_600_000
    assert 0 < ra["operatingHours"] - rb["operatingHours"] <= elapsed_h + 0.2
    tel = [e for e in outbox("aws.iot.rule.circularity_telemetry", mark) if e["thingName"] == name]
    assert tel and tel[-1]["operatingHours"] == ra["operatingHours"] and tel[-1]["topic"].endswith(f"/{name}/telemetry")
    retained = call(client, "GET", "data", "/retainedMessage/" + quote(tel[-1]["topic"], safe="")).json()
    assert retained["lastModifiedTime"] == ra["sampleAt"]
    # offline kits (returned assets) do not report
    hero = call(client, "GET", "data", "/things/cm-mtr-2041/shadow", {"name": "condition"}).json()["state"]["reported"]
    assert hero["operatingHours"] == 18450.0
    # one chain of reports stays scheduled
    with engine.connect() as conn:
        pending = conn.execute(text("SELECT count(*) FROM sim.scheduled WHERE handler = :h AND NOT done"), {"h": HANDLER})
        assert pending.scalar_one() == 1


def test_faults_answer_in_the_aws_shape(client):
    client.post("/_sim/faults", json={"system": "iot", "kind": "error", "value": 429})
    r = call(client, "GET", "iot", "/things")
    assert r.status_code == 429 and code(r) == "ThrottlingException" and r.json()["message"] == "Rate exceeded"
    client.delete("/_sim/faults", params={"system": "iot"})
    client.post("/_sim/faults", json={"system": "iot", "kind": "error", "value": 500})
    assert code(call(client, "GET", "data", "/retainedMessage")) == "InternalFailureException"
    client.delete("/_sim/faults", params={"system": "iot"})
    client.post("/_sim/faults", json={"system": "iot", "kind": "unavailable"})
    r = call(client, "GET", "iot", "/things")
    assert r.status_code == 503 and code(r) == "ServiceUnavailableException"
    client.delete("/_sim/faults", params={"system": "iot"})
    client.post("/_sim/faults", json={"system": "iot", "kind": "token_expired"})
    r = call(client, "GET", "iot", "/things")
    assert r.status_code == 403 and code(r) == "ExpiredTokenException"
    client.delete("/_sim/faults", params={"system": "iot"})
    assert call(client, "GET", "iot", "/things").status_code == 200


def test_rule_deliveries_are_signed_cloudevents(client):
    with engine.begin() as conn:
        conn.execute(text("UPDATE sim.outbox SET delivered_at = now() WHERE delivered_at IS NULL"))
    sub = client.post("/_sim/webhooks", json={"url": "http://receiver/iot", "sources": ["iot"], "secret": "iot-s3cret"}).json()[
        "id"
    ]
    try:
        alarm = {"eventId": "evt-hook", "type": "high-vibration", "severity": "alarm", "ts": 2, "value": 7.6, "threshold": 7.1}
        topic = "dt/pumps/cm-pmp-test/events"
        call(client, "POST", "data", "/topics/" + quote(topic, safe=""), body=json.dumps(alarm).encode())
        received = []

        def post(url, body, headers):
            if url == "http://receiver/iot":
                received.append((body, headers))
            return 204

        webhooks.deliver(post)
        evs = [(json.loads(b), h) for b, h in received]
        mine = [(e, h, b) for (e, h), (b, _) in zip(evs, received, strict=True) if e["data"].get("eventId") == "evt-hook"]
        assert len(mine) == 1
        ev, headers, body = mine[0]
        assert ev["specversion"] == "1.0" and ev["source"] == "/source-sim/iot"
        assert ev["type"] == "aws.iot.rule.circularity_condition_events" and ev["subject"] == "cm-pmp-test"
        assert headers["x-sim-signature"] == webhooks.sign("iot-s3cret", body)
        assert headers["x-sim-signature"] != webhooks.sign("other", body)
    finally:
        client.delete(f"/_sim/webhooks/{sub}")
