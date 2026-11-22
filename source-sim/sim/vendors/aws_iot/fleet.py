"""The AWS IoT Core message broker, Device Shadow service and rules engine, as the mock runs them (docs/backend-steps.md, B5c).

    publish(conn, topic, payload, qos, retain)   the broker: keeps retained messages, hands the message to the rules
    update_shadow(conn, thing, name, doc)        the Device Shadow service: merge, version, metadata, delta, and the
                                                 $aws/things/<thing>/shadow[/name/<name>]/update/documents message
    report(conn, payload)                        scheduler handler "aws_iot.fleet_report": every online device reports

Rules engine: each enabled topic rule matches its FROM topic filter (MQTT wildcards + and #) and delivers the SELECT
result to its HTTPS destination. The destination is source-sim's outbox (sim/core/events.py), sent as a signed CloudEvent
(sim/core/webhooks.py) of type `aws.iot.rule.<ruleName>` with the SELECT result as data.
SIMPLIFIED (documented): the SELECT is evaluated for the seeded rules' forms only: `*`, `topic()`, `topic(n)`,
`timestamp()` and dotted paths into the JSON payload, each with `AS alias`; no WHERE clause, functions or SQL
versions beyond that. A payload that is not JSON is not delivered (AWS would deliver it base64-encoded with `*`).

The fleet report (every TELEMETRY_EVERY of simulated time): each online device adds duty x elapsed hours to its hour
counter, takes a new sample (seeded RNG per device and hour, around its profile; vibration drifts by its wear trend),
publishes it retained on dt/<fleet>/<thing>/telemetry, raises an alarm on dt/<fleet>/<thing>/events when vibration
enters zone D or the bearing reaches 90 °C (once per excursion), and updates its "condition" shadow. When the clock
has jumped further than one interval, a device reports once for the whole gap (hours still add up), so a clock
advance of days costs one report per device, not one per hour.
"""

import copy
import json
import random
import re
from datetime import datetime
from typing import Any

from sqlalchemy import select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import Connection

from sim.core import clock, events, scheduler
from sim.vendors.aws_iot import models as t
from sim.vendors.aws_iot.seed import (
    SOURCE,
    TELEMETRY_EVERY,
    TEMP_ALARM,
    VIB_ALARM,
    condition_reported,
    event,
    meta,
    ms,
    schedule_telemetry,
    telemetry_payload,
)

HANDLER = "aws_iot.fleet_report"


# ---------------------------------------------------------------- broker and rules
def matches(topic_filter: str, topic: str) -> bool:
    f, tp = topic_filter.split("/"), topic.split("/")
    for i, part in enumerate(f):
        if part == "#":
            return True
        if i >= len(tp) or (part != "+" and part != tp[i]):
            return False
    return len(f) == len(tp)


_ITEM = re.compile(r"^(.+?)(?:\s+AS\s+(\w+))?$", re.I)


def _select_items(sql: str) -> list[tuple[str, str | None]]:
    body = re.match(r"^\s*SELECT\s+(.*)\s+FROM\s+'[^']*'\s*$", sql, re.I | re.S)
    items = []
    for raw in (body.group(1) if body else "*").split(","):
        m = _ITEM.match(raw.strip())
        items.append((m.group(1).strip(), m.group(2)))
    return items


def evaluate(sql: str, topic: str, payload: dict, now_ms: int) -> dict:
    out: dict[str, Any] = {}
    parts = topic.split("/")
    for expr, alias in _select_items(sql):
        if expr == "*":
            out |= payload
            continue
        if expr == "topic()":
            val = topic
        elif m := re.fullmatch(r"topic\((\d+)\)", expr):
            n = int(m.group(1))
            val = parts[n - 1] if 0 < n <= len(parts) else None
        elif expr == "timestamp()":
            val = now_ms
        else:
            val = payload
            for k in expr.split("."):
                val = val.get(k) if isinstance(val, dict) else None
        out[alias or expr.split(".")[-1]] = val
    return out


def publish(conn: Connection, topic: str, payload: bytes, qos: int = 0, retain: bool = False, at: datetime | None = None) -> int:
    """Publish one message. Returns how many rules delivered it."""
    at = at or clock.now(conn)
    if retain:
        if payload:
            conn.execute(
                pg_insert(t.RETAINED)
                .values(topic=topic, payload=payload, qos=qos, last_modified=ms(at))
                .on_conflict_do_update(index_elements=["topic"], set_={"payload": payload, "qos": qos, "last_modified": ms(at)})
            )
        else:  # an empty retained message clears the topic's retained message (MQTT)
            conn.execute(t.RETAINED.delete().where(t.RETAINED.c.topic == topic))
    try:
        body = json.loads(payload) if payload else None
    except ValueError:
        body = None
    if not isinstance(body, dict):
        return 0
    n = 0
    for r in conn.execute(select(t.RULE).where(t.RULE.c.disabled.is_(False)).order_by(t.RULE.c.rule_name)):
        if matches(r.topic_filter, topic):
            data = evaluate(r.doc["rule"]["sql"], topic, body, ms(at))
            events.emit(conn, SOURCE, f"aws.iot.rule.{r.rule_name}", data.get("thingName") or topic, data, at=at)
            n += 1
    return n


# ---------------------------------------------------------------- Device Shadow service
class ShadowError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


def _merge(base: dict, patch: dict) -> dict:
    """Shadow merge: dicts merge, null deletes, anything else replaces."""
    out = copy.deepcopy(base)
    for k, v in patch.items():
        if v is None:
            out.pop(k, None)
        elif isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def _meta_merge(base: dict, patch: dict, ts: int) -> dict:
    out = copy.deepcopy(base)
    for k, v in patch.items():
        if v is None:
            out.pop(k, None)
        elif isinstance(v, dict) and isinstance(out.get(k), dict) and "timestamp" not in out[k]:
            out[k] = _meta_merge(out[k], v, ts)
        else:
            out[k] = meta(v, ts)
    return out


def delta(desired: dict | None, reported: dict | None) -> dict:
    """The desired values the device has not reported yet."""
    out = {}
    for k, v in (desired or {}).items():
        r = (reported or {}).get(k)
        if isinstance(v, dict) and isinstance(r, dict):
            sub = delta(v, r)
            if sub:
                out[k] = sub
        elif v != r:
            out[k] = v
    return out


def shadow_topic(thing: str, name: str) -> str:
    return f"$aws/things/{thing}/shadow" + (f"/name/{name}" if name else "")


def get_shadow(conn: Connection, thing: str, name: str) -> dict | None:
    row = conn.execute(select(t.SHADOW).where(t.SHADOW.c.thing_name == thing, t.SHADOW.c.shadow_name == name)).first()
    if row is None:
        return None
    state = dict(row.state)
    d = delta(state.get("desired"), state.get("reported"))
    if d:
        state["delta"] = d
    return {"state": state, "metadata": row.metadata, "version": row.version, "timestamp": int(clock.now(conn).timestamp())}


def update_shadow(conn: Connection, thing: str, name: str, doc: Any, at: datetime | None = None) -> dict:
    """UpdateThingShadow. Raises ShadowError the way the service refuses."""
    if not isinstance(doc, dict) or not isinstance(doc.get("state"), dict):
        raise ShadowError(400, "InvalidRequestException", "Missing required node: state")
    state_in = doc["state"]
    bad = set(state_in) - {"desired", "reported"}
    if bad:
        raise ShadowError(400, "InvalidRequestException", f"State contains an invalid node: '{sorted(bad)[0]}'")
    for k, v in state_in.items():
        if v is not None and not isinstance(v, dict):
            raise ShadowError(400, "InvalidRequestException", f"Invalid JSON: {k} node must be an object")
    at = at or clock.now(conn)
    ts = int(at.timestamp())
    row = conn.execute(
        select(t.SHADOW).where(t.SHADOW.c.thing_name == thing, t.SHADOW.c.shadow_name == name).with_for_update()
    ).first()
    if row is not None and "version" in doc and doc["version"] != row.version:
        raise ShadowError(409, "ConflictException", "Version conflict")
    prev_state = dict(row.state) if row else {}
    prev_meta = dict(row.metadata) if row else {}
    version = (row.version if row else 0) + 1
    state, md = dict(prev_state), dict(prev_meta)
    for section in ("desired", "reported"):
        if section not in state_in:
            continue
        if state_in[section] is None:
            state.pop(section, None)
            md.pop(section, None)
        else:
            state[section] = _merge(state.get(section) or {}, state_in[section])
            md[section] = _meta_merge(md.get(section) or {}, state_in[section], ts)
    if row is None:
        conn.execute(
            t.SHADOW.insert().values(thing_name=thing, shadow_name=name, state=state, metadata=md, version=version, updated_at=at)
        )
    else:
        conn.execute(
            update(t.SHADOW)
            .where(t.SHADOW.c.thing_name == thing, t.SHADOW.c.shadow_name == name)
            .values(state=state, metadata=md, version=version, updated_at=at)
        )
    current = {"state": state, "metadata": md, "version": version}
    previous = {"state": prev_state, "metadata": prev_meta, "version": version - 1} if row else None
    publish(
        conn,
        shadow_topic(thing, name) + "/update/documents",
        json.dumps({"previous": previous, "current": current, "timestamp": ts}).encode(),
        at=at,
    )
    out = {"state": dict(state_in),"metadata": {k: meta(v, ts) for k, v in state_in.items() if v},
           "version": version, "timestamp": ts}  # fmt: skip
    if "clientToken" in doc:
        out["clientToken"] = doc["clientToken"]
    return out


# ---------------------------------------------------------------- the fleet report on the simulated clock
def sample(thing: str, profile: dict, at: datetime) -> tuple[float, float, float, bool]:
    """(vibration, bearing temperature, 30-day duty, running) of one device at one time: seeded per device and hour."""
    rng = random.Random(f"{thing}|{int(at.timestamp() // 3600)}")
    days = max(0.0, (ms(at) - profile.get("since", ms(at))) / 86_400_000)
    vib = max(0.3, profile["vib"] + profile.get("trend", 0.0) * days + rng.gauss(0, 0.15))
    temp = profile["temp"] + rng.gauss(0, 1.2) + 2.0 * (vib - profile["vib"])
    duty = min(100.0, max(0.0, profile["duty"] + rng.gauss(0, 1.5)))
    return round(vib, 2), round(temp, 1), round(duty, 1), rng.random() < profile["duty"] / 100


def report_device(conn: Connection, thing, at: datetime) -> None:
    shadow = conn.execute(
        select(t.SHADOW.c.state).where(t.SHADOW.c.thing_name == thing.thing_name, t.SHADOW.c.shadow_name == "condition")
    ).scalar()
    prev = (shadow or {}).get("reported") or {}
    last_ms = prev.get("sampleAt") or ms(at)
    hours_run = max(0.0, (ms(at) - last_ms) / 3_600_000) * thing.profile["duty"] / 100
    hours = float(prev.get("operatingHours") or thing.profile["hours"]) + hours_run
    vib, temp, duty, running = sample(thing.thing_name, thing.profile, at)
    was = prev.get("alarms") or {}
    evs = list(prev.get("events") or [])
    base = f"dt/{thing.fleet}/{thing.thing_name}"
    raised = []
    if vib >= VIB_ALARM and not was.get("highVibration"):
        raised.append(event("high-vibration", vib, VIB_ALARM, "mm/s", at))
    if temp >= TEMP_ALARM and not was.get("overTemperature"):
        raised.append(event("over-temperature", temp, TEMP_ALARM, "degC", at))
    rep = condition_reported(thing.asset_tag, hours, duty, vib, temp, running, at, evs + raised)
    publish(conn, base + "/telemetry", json.dumps(telemetry_payload(rep)).encode(), qos=1, retain=True, at=at)
    for e in raised:
        publish(conn, base + "/events", json.dumps(e).encode(), qos=1, retain=True, at=at)
    update_shadow(conn, thing.thing_name, "condition", {"state": {"reported": rep}}, at=at)


@scheduler.handler(HANDLER)
def report(conn: Connection, payload: dict) -> None:  # noqa: ARG001 - scheduled handlers take (conn, payload)
    now = clock.now(conn)
    for thing in conn.execute(select(t.THING).where(t.THING.c.online.is_(True)).order_by(t.THING.c.thing_name)).all():
        report_device(conn, thing, now)
    # one chain of reports: schedule the next unless one is already waiting (this row is still pending while it runs)
    waiting = conn.execute(
        text("SELECT count(*) FROM sim.scheduled WHERE handler = :h AND NOT done AND due_at > :n"), {"h": HANDLER, "n": now}
    ).scalar_one()
    if not waiting:
        schedule_telemetry(conn, now + TELEMETRY_EVERY)
