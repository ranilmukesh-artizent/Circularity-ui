"""AWS IoT Core (iot): device telemetry, the demo's SOURCES.iot ("Operating hours, duty cycle, vibration and
temperature events"; authority over Duty and Operating hours). Read only.
Written against source-sim's AWS IoT Core mock (apps/source-sim/sim/vendors/aws_iot), a synthetic stand-in: no real
AWS account is connected.

Not provisioned at start, as in the demo: the source stays `unavailable` until it is connected
(POST /api/sources/iot/connect, or DI_IOT_CONNECTED=true / `iot_connected` in di/config.py to start connected;
docs/BACKEND_STEPS.md, B5c).

Auth: AWS Signature Version 4 on every call (region ap-south-1; service "iot" for the control plane under /iot,
"iotdata" for the data plane under /data), with the connector's IAM access key. The canonical URI is the full request
path on the mock's host, as the mock documents (sim/vendors/aws_iot/sigv4.py).
Throttling (429 ThrottlingException) is retried with exponential backoff, up to 4 attempts; ExpiredTokenException
(403) is an auth failure, so the source shows auth_expired, as for every connector.

Resource "shadows" (one record per device):
    full read   ListRetainedMessages (each topic's lastModifiedTime) + ListThings (nextToken, maxResults 250), then
                GetThingShadow ?name=condition per thing
    delta read  ListRetainedMessages: the things whose dt/<fleet>/<thing>/telemetry or /events message changed after
                the cursor, then DescribeThing + GetThingShadow ?name=condition for each
    cursor      the newest lastModifiedTime seen (epoch ms, as ISO 8601 UTC)
The topic rules' HTTPS deliveries arrive as CloudEvents `aws.iot.rule.*` at /api/webhooks/source-sim (the shared
receiver, di/connectors/webhook.py), which queues a delta sync of iot while it is connected.

Facts (key: thing attribute assetTag, the asset id every system uses; RT-1048 → MTR-2041, thing cm-mtr-2041)
    asset.<tag>       iot_thing, source_refs [IOT:<thing>], run_hours (operatingHours; iot has authority over
                      Operating hours, so where Maximo's RUNHOURS meter disagrees a conflict opens)
    condition.<tag>   duty_cycle_pct (iot has authority over Duty), vibration_mm_s, vibration_zone (ISO 10816-3),
                      bearing_temp_c, telemetry_events (last 5 alarms), telemetry_at
"""

import hashlib
import hmac
import time
from collections.abc import Iterator
from datetime import UTC, datetime
from urllib.parse import quote

import httpx

from di.canonical.store import Fact
from di.config import get_settings
from di.connectors.base import Adapter, Record, Resource
from di.connectors.http import Auth, SourceClient, SourceError

REGION = "ap-south-1"
ACCESS_KEY = "AKIACIRCULARITYDEMO1"
SECRET_KEY = "circularity-demo/aws-iot/K7MDENG+bPxRfiCYDI"  # demo credential of the synthetic mock
SERVICE = {"iot": "iot", "data": "iotdata"}
SHADOW = "condition"
THROTTLE_TRIES = 4
TOPIC_KINDS = ("telemetry", "events")


# ---------------------------------------------------------------- SigV4
def _hmac(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode(), hashlib.sha256).digest()


def sigv4_headers(method: str, url: httpx.URL, body: bytes, access_key: str, secret: str, region: str, service: str,
                  now: datetime | None = None) -> dict[str, str]:  # fmt: skip
    """Authorization, X-Amz-Date and X-Amz-Content-Sha256 for one request (AWS Signature Version 4)."""
    now = now or datetime.now(UTC)
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    date = amz_date[:8]
    payload_hash = hashlib.sha256(body).hexdigest()
    host = url.netloc.decode()
    headers = {"host": host, "x-amz-content-sha256": payload_hash, "x-amz-date": amz_date}
    signed = sorted(headers)
    query = sorted((quote(k, safe="-_.~"), quote(v, safe="-_.~")) for k, v in url.params.multi_items())
    creq = "\n".join(
        [
            method.upper(),
            quote(url.path, safe="/-_.~"),
            "&".join(f"{k}={v}" for k, v in query),
            "".join(f"{h}:{headers[h]}\n" for h in signed),
            ";".join(signed),
            payload_hash,
        ]
    )
    scope = f"{date}/{region}/{service}/aws4_request"
    sts = "\n".join(["AWS4-HMAC-SHA256", amz_date, scope, hashlib.sha256(creq.encode()).hexdigest()])
    key = _hmac(_hmac(_hmac(_hmac(("AWS4" + secret).encode(), date), region), service), "aws4_request")
    sig = hmac.new(key, sts.encode(), hashlib.sha256).hexdigest()
    return {
        "X-Amz-Date": amz_date,
        "X-Amz-Content-Sha256": payload_hash,
        "Authorization": f"AWS4-HMAC-SHA256 Credential={access_key}/{scope}, SignedHeaders={';'.join(signed)}, Signature={sig}",
    }


class SigV4(Auth):
    """Requests are signed one by one (the signature covers the URL), so this adds no fixed headers."""

    def __init__(self, access_key: str, secret: str, region: str):
        self.access_key, self.secret, self.region = access_key, secret, region


# ---------------------------------------------------------------- helpers
def ms_to_iso(v: int | None) -> str | None:
    return datetime.fromtimestamp(v / 1000, UTC).isoformat(timespec="milliseconds") if v else None


def iso_to_ms(v: str) -> int:
    d = datetime.fromisoformat(v.replace("Z", "+00:00"))
    return int(round((d if d.tzinfo else d.replace(tzinfo=UTC)).timestamp() * 1000))


def utc(v: int | None) -> str | None:
    """Epoch ms → '2026-10-02T21:41:00Z'."""
    return datetime.fromtimestamp(v / 1000, UTC).isoformat(timespec="seconds").replace("+00:00", "Z") if v else None


def thing_of(topic: str) -> str | None:
    """dt/<fleet>/<thing>/telemetry|events → thing."""
    p = topic.split("/")
    return p[2] if len(p) == 4 and p[0] == "dt" and p[3] in TOPIC_KINDS else None


class AwsIotAdapter(Adapter):
    source_id = "iot"
    base_path = "/aws-iot"
    connected_confidence = 92.0  # the source's confidence once connected (the demo's 0 means "no data")

    @property
    def provisioned(self) -> bool:
        """Whether the source starts connected (registered `live`); the demo starts it not provisioned."""
        return get_settings().iot_connected

    def auth(self):
        return SigV4(ACCESS_KEY, SECRET_KEY, REGION)

    def set_delivery(self, enabled: bool) -> int:
        """Enable (on connect) or disable (on disconnect) the topic rules that deliver telemetry to Circularity
        (EnableTopicRule / DisableTopicRule). Not provisioned means no rule delivers, so the shared event outbox is not
        filled with telemetry nobody receives. Returns the number of rules changed."""
        base = get_settings().source_sim_url.rstrip("/") + self.base_path

        def signed(c: httpx.Client, method: str, path: str) -> httpx.Response:
            url = httpx.URL(base + path)
            r = c.request(method, url, headers=sigv4_headers(method, url, b"", ACCESS_KEY, SECRET_KEY, REGION, "iot"))
            r.raise_for_status()
            return r

        with httpx.Client(timeout=15) as c:
            rules = signed(c, "GET", "/iot/rules").json().get("rules", [])
            todo = [r["ruleName"] for r in rules if r["ruleDisabled"] == enabled]
            for name in todo:
                signed(c, "POST", f"/iot/rules/{quote(name, safe='')}/{'enable' if enabled else 'disable'}")
        return len(todo)

    def resources(self):
        return [Resource("shadows", self.read_shadows)]

    # ------------------------------------------------------------- calls
    def call(self, client: SourceClient, plane: str, path: str, params: dict | None = None) -> httpx.Response:
        """One signed GET (plane "iot" or "data"); throttling is retried with backoff."""
        params = {k: str(v) for k, v in (params or {}).items()}
        rel = f"/{plane}{path}"
        for attempt in range(THROTTLE_TRIES):
            url = httpx.URL(client.url(rel), params=params)
            headers = sigv4_headers("GET", url, b"", ACCESS_KEY, SECRET_KEY, REGION, SERVICE[plane])
            try:
                return client.request("GET", rel, params=params, headers=headers)
            except SourceError as e:
                if e.status != 429 or attempt == THROTTLE_TRIES - 1:
                    raise
                time.sleep(0.25 * 2**attempt)
        raise AssertionError("unreachable")

    def pages(self, client: SourceClient, plane: str, path: str, key: str, size: int, **params) -> Iterator[tuple[dict, str]]:
        token = None
        while True:
            q = {**params, "maxResults": size} | ({"nextToken": token} if token else {})
            r = self.call(client, plane, path, q)
            body = r.json()
            items = body.get(key) or []
            client.note_records(len(items))
            for it in items:
                yield it, str(r.request.url)
            token = body.get("nextToken")
            if not token or not items:
                return

    def retained(self, client: SourceClient) -> dict[str, int]:
        """thing → newest lastModifiedTime (epoch ms) of its telemetry and events topics."""
        out: dict[str, int] = {}
        for t, _ in self.pages(client, "data", "/retainedMessage", "retainedTopics", 200):
            thing = thing_of(t["topic"])
            if thing:
                out[thing] = max(out.get(thing, 0), int(t["lastModifiedTime"]))
        return out

    def shadow(self, client: SourceClient, thing: str) -> tuple[dict | None, str]:
        try:
            r = self.call(client, "data", f"/things/{thing}/shadow", {"name": SHADOW})
        except SourceError as e:
            if e.status == 404:  # a kit that never reported has no condition shadow
                return None, ""
            raise
        return r.json(), str(r.request.url)

    # ------------------------------------------------------------- reading
    def read_shadows(self, client: SourceClient, since: str | None) -> Iterator[Record]:
        changed = self.retained(client)
        if since is None:
            things = [(t, None) for t, _ in self.pages(client, "iot", "/things", "things", 250)]
        else:
            after = iso_to_ms(since)
            names = sorted(n for n, lm in changed.items() if lm > after)
            things = [(self.call(client, "iot", f"/things/{n}").json(), None) for n in names]
        for t, _ in things:
            name = t["thingName"]
            shadow, url = self.shadow(client, name)
            if shadow is None:
                continue
            payload = {"thing": {k: t.get(k) for k in ("thingName", "thingTypeName", "thingArn", "attributes")}, "shadow": shadow}
            yield Record("shadows", name, payload, url, ms_to_iso(changed.get(name)))

    # ------------------------------------------------------------- mapping
    def map(self, record: Record) -> list[Fact]:
        thing = record.payload["thing"]
        key = (thing.get("attributes") or {}).get("assetTag")
        if not key:
            return []
        name = thing["thingName"]
        rep = (((record.payload.get("shadow") or {}).get("state") or {}).get("reported")) or {}
        out: list[Fact] = []

        def fact(model, field, value, sf, sv, transform):
            if value is not None:
                out.append(Fact(model, key, field, value, sf, sv, transform))

        sr = "state.reported."
        fact("asset", "iot_thing", name, "thingName", name, "Pass-through")
        fact("asset", "source_refs", [f"IOT:{name}"], "thingName", name, "Prefixed with system")
        h = rep.get("operatingHours")
        fact(
            "asset",
            "run_hours",
            h,
            sr + "operatingHours",
            f"{h:,.1f} h" if h is not None else None,
            "Device hour counter; hours kept",
        )
        d = rep.get("dutyCyclePct")
        fact("condition", "duty_cycle_pct", d, sr + "dutyCyclePct", f"{d} %" if d is not None else None,
             "Share of the last 30 days running; percent kept")  # fmt: skip
        v = rep.get("vibrationMmS")
        fact(
            "condition",
            "vibration_mm_s",
            v,
            sr + "vibrationMmS",
            f"{v} mm/s" if v is not None else None,
            "Velocity RMS; unit kept",
        )
        fact("condition", "vibration_zone", rep.get("vibrationZone"), sr + "vibrationZone", rep.get("vibrationZone"),
             "ISO 10816-3 zone (A-D)")  # fmt: skip
        tc = rep.get("bearingTempC")
        fact("condition", "bearing_temp_c", tc, sr + "bearingTempC", f"{tc} °C" if tc is not None else None, "Unit kept")
        if "events" in rep:
            evs = [
                {
                    "type": e.get("type"),
                    "at": utc(e.get("ts")),
                    "value": e.get("value"),
                    "threshold": e.get("threshold"),
                    "unit": e.get("unit"),
                }  # fmt: skip
                for e in rep.get("events") or []
            ]
            fact("condition", "telemetry_events", evs, sr + "events", None, "Last 5 alarms; epoch ms → UTC")
        fact("condition", "telemetry_at", utc(rep.get("sampleAt")), sr + "sampleAt", rep.get("sampleAt"), "Epoch ms → UTC")
        return out


ADAPTER = AwsIotAdapter()
