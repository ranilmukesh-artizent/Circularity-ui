"""AWS IoT Core seed: the condition-monitoring fleet (docs/backend-steps.md, B5c).

Which devices
- returned assets: every live case whose asset is an industrial motor (MTR-) or a hydraulic pump (PMP-) carries a
  condition-monitoring kit (53 devices). The device was unplugged when the asset came back, so it is offline and its
  shadow and retained messages hold the last report before the return (RT-1048's MTR-2041 is `cm-mtr-2041`).
- in-service pilot: the 24 most recently redeployed or re-leased motors and pumps of the closed decisions (the installed
  base Maximo shows as OPERATING) carry a kit that is online and reports every simulated hour (sim/vendors/aws_iot/fleet.py).
Thing names are `cm-<asset id in lower case>`; attribute assetTag is the asset id used by every other system.

Values (seeded RNG per device, so every reset gives the same fleet)
- operatingHours: the machine's hour counter. For a returned asset it equals Maximo's RUNHOURS meter (the same
  formula, sim/vendors/maximo/seed.run_hours_reading: RT-1048 18,450 h), except for one case in eight, where Maximo's
  reading was keyed at the last service visit and the device counted on until the return (3-8 % more hours). For a
  pilot device: hours before the redeploy plus duty x hours since.
- dutyCyclePct: share of the last 30 days the machine ran. RT-1048 runs 24/7 (96.4 %), as the demo's cost trace says;
  other motors run two shifts (55-70 %), pumps 40-65 %.
- vibrationMmS (velocity RMS) follows the inspection grade, zoned by ISO 10816-3 (group 2, flexible foundation: A
  below 2.3, B below 4.5, C below 7.1, D from 7.1 mm/s); RT-1048 (grade B) 2.8 mm/s.
- bearingTempC follows the grade too; RT-1048 66.0 °C.
- events: a high-vibration alarm when vibration reaches zone D (7.1 mm/s), an over-temperature alarm when the bearing
  reaches 90 °C; returned assets carry the alarms of their last 30 days in service.
- one pilot motor has a wearing bearing: its vibration rises by 0.12 mm/s per simulated day.
Firmware: 2.4.1 everywhere (job fw-2-4-1-rollout, completed); the pilot is being moved to 2.5.0 (job
fw-2-5-0-pilot, in progress): half its devices report 2.5.0, the rest show a shadow delta.
"""

import json
import random
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import insert, text
from sqlalchemy.engine import Connection

from sim import scheduler
from sim.seed import Seed
from sim.vendors.aws_iot import tables as t
from sim.vendors.maximo.seed import ANCHOR, run_hours_reading, site_code

REGION = "ap-south-1"
ACCOUNT = "123456789012"
ARN = f"arn:aws:iot:{REGION}:{ACCOUNT}"
SOURCE = "iot"
TELEMETRY_EVERY = timedelta(hours=1)
FW_OLD, FW_NEW = "2.4.1", "2.5.0"
VIB_ALARM, TEMP_ALARM = 7.1, 90.0  # mm/s (ISO 10816-3 zone D), °C bearing
CLASSES = {"motor": ("motors", "IndustrialMotorMonitor"), "pump": ("pumps", "HydraulicPumpMonitor")}
ROOT, RETURNED, PILOT = "northfield-condition-monitoring", "returned-assets", "in-service-pilot"
PILOT_SIZE = 24
WEB_HOOK = "https://di.northfield.example/api/webhooks/source-sim"  # the integration's HTTPS rule destination
GRADE_BASE = {  # vibration mm/s, bearing °C (ranges)
    "A": ((1.2, 2.0), (52, 60)),
    "B": ((2.4, 3.6), (60, 70)),
    "C": ((4.6, 6.4), (70, 82)),
    "D": ((7.3, 9.5), (84, 96)),
    None: ((2.0, 5.0), (58, 75)),
}


def thing_name(asset_id: str) -> str:
    return "cm-" + asset_id.lower()


def ms(d: datetime) -> int:
    return int(d.timestamp() * 1000)


def zone(v: float) -> str:
    return "A" if v < 2.3 else "B" if v < 4.5 else "C" if v < VIB_ALARM else "D"


def thing_id(name: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"{ARN}:thing/{name}"))


def meta(value, ts: int):
    """Shadow metadata for a value: every leaf gets {"timestamp": epoch seconds}, lists one entry per element."""
    if isinstance(value, dict):
        return {k: meta(v, ts) for k, v in value.items()}
    if isinstance(value, list):
        return [meta(v, ts) for v in value]
    return {"timestamp": ts}


def tenant_code(tenant: str) -> str:
    return tenant.lower().replace(" ", "-")


# ---------------------------------------------------------------- the fleet
def devices(s: Seed) -> list[dict]:
    """Every device with its profile (what the simulation needs) and the facts the seed reports."""
    as_of = s.world.as_of
    out = []
    for case in s.cases.values():
        f = case.facts
        if f.cls not in CLASSES:
            continue
        n = int(f.id.split("-")[1])
        rng = random.Random(f"aws_iot:{f.asset_id}")
        (v0, v1), (t0, t1) = GRADE_BASE.get(f.grade, GRADE_BASE[None])
        vib, temp = round(rng.uniform(v0, v1), 2), round(rng.uniform(t0, t1), 1)
        duty = round(rng.uniform(55, 70) if f.cls == "motor" else rng.uniform(40, 65), 1)
        hours = float(run_hours_reading(f))
        if (n - ANCHOR) % 8 == 5:  # Maximo's meter was keyed at the last service visit; the device counted on
            hours = float(round(hours * (1 + rng.uniform(0.03, 0.08))))
        if f.id == "RT-1048":
            vib, temp, duty = 2.8, 66.0, 96.4  # 24/7 duty (the demo's cost trace)
        last = min(f.received, as_of) - timedelta(minutes=rng.randint(20, 300))
        out.append(
            {
                "asset": f.asset_id, "cls": f.cls, "site": site_code(f.location), "tenant": f.owner, "case": f.id,
                "online": False, "group": RETURNED, "fw": FW_OLD, "fw_desired": FW_OLD, "last": last,
                "profile": {"vib": vib, "temp": temp, "duty": duty, "trend": 0.0, "hours": hours},
                "events": _history(rng, vib, temp, last),
            }
        )  # fmt: skip
    case_assets = {c.facts.asset_id for c in s.cases.values()}
    latest = {}
    for d in s.decisions:
        if d.cls in CLASSES and d.asset_id not in case_assets and (d.asset_id not in latest or d.date >= latest[d.asset_id].date):
            latest[d.asset_id] = d
    pilot = [d for d in latest.values() if d.route in ("redeploy", "relase") and d.status != "cancelled" and d.date <= as_of]
    pilot = sorted(pilot, key=lambda d: (d.date, d.asset_id), reverse=True)[:PILOT_SIZE]
    worn = min((d.asset_id for d in pilot if d.cls == "motor"), default=None)
    for i, d in enumerate(sorted(pilot, key=lambda d: d.asset_id)):
        rng = random.Random(f"aws_iot:{d.asset_id}")
        (v0, v1), (t0, t1) = GRADE_BASE.get(d.grade, GRADE_BASE[None])
        # refurbished: running smoother, below the alarm limits (so the pilot starts with no alarm raised)
        vib, temp = round(min(rng.uniform(v0, v1) * 0.8, 6.8), 2), round(min(rng.uniform(t0, t1) - 4, 84.0), 1)
        duty = round(rng.uniform(55, 70) if d.cls == "motor" else rng.uniform(40, 65), 1)
        since = (as_of - d.date).total_seconds() / 3600
        hours = float(round(rng.uniform(6000, 22000) + since * duty / 100))
        trend = 0.0
        if d.asset_id == worn:
            vib, temp, trend = 5.9, 74.0, 0.12
        out.append(
            {
                "asset": d.asset_id, "cls": d.cls, "site": site_code(d.site), "tenant": d.tenant, "case": None,
                "online": True, "group": PILOT, "fw": FW_NEW if i % 2 == 0 else FW_OLD, "fw_desired": FW_NEW,
                "last": as_of - timedelta(minutes=rng.randint(5, 55)),
                "profile": {"vib": vib, "temp": temp, "duty": duty, "trend": trend, "hours": hours, "since": ms(as_of)},
                "events": [],
            }
        )  # fmt: skip
    return out


def _history(rng: random.Random, vib: float, temp: float, last: datetime) -> list[dict]:
    """The alarms of the last 30 days in service (newest last)."""
    ev = []
    if vib >= VIB_ALARM:
        for _ in range(rng.randint(1, 3)):
            ev.append(("high-vibration", round(vib + rng.uniform(0.2, 1.5), 2), VIB_ALARM, "mm/s"))
    if temp >= 80:
        for _ in range(2 if temp >= TEMP_ALARM else 1):
            ev.append(("over-temperature", round(max(temp, TEMP_ALARM) + rng.uniform(0.5, 4.0), 1), TEMP_ALARM, "degC"))
    stamps = sorted(last - timedelta(hours=rng.randint(2, 30 * 24)) for _ in ev)
    return [event(kind, v, thr, unit, at) for (kind, v, thr, unit), at in zip(ev, stamps, strict=True)]


def event(kind: str, value: float, threshold: float, unit: str, at: datetime) -> dict:
    return {
        "eventId": "evt-" + uuid.uuid5(uuid.NAMESPACE_URL, f"{kind}:{at.isoformat()}:{value}").hex[:16],
        "type": kind,
        "severity": "alarm",
        "ts": ms(at),
        "value": value,
        "threshold": threshold,
        "unit": unit,
    }


def condition_reported(asset: str, hours: float, duty: float, vib: float, temp: float, running: bool, at: datetime,
                       events: list[dict]) -> dict:  # fmt: skip
    return {
        "assetTag": asset,
        "operatingHours": round(hours, 1),
        "dutyCyclePct": round(duty, 1),
        "vibrationMmS": round(vib, 2),
        "vibrationZone": zone(vib),
        "bearingTempC": round(temp, 1),
        "running": running,
        "sampleAt": ms(at),
        "alarms": {"highVibration": vib >= VIB_ALARM, "overTemperature": temp >= TEMP_ALARM},
        "events": events[-5:],
    }


def telemetry_payload(r: dict) -> dict:
    return {k: r[k] for k in ("operatingHours", "dutyCyclePct", "vibrationMmS", "bearingTempC", "running")} | {
        "ts": r["sampleAt"]
    }


# ---------------------------------------------------------------- control-plane documents
def group_doc(name: str, parent: str | None, desc: str, created: datetime) -> dict:
    roots = [] if parent is None else ([{"groupName": ROOT, "groupArn": f"{ARN}:thinggroup/{ROOT}"}] if parent == ROOT else [
        {"groupName": ROOT, "groupArn": f"{ARN}:thinggroup/{ROOT}"},
        {"groupName": parent, "groupArn": f"{ARN}:thinggroup/{parent}"},
    ])  # fmt: skip
    md = {"rootToParentThingGroups": roots, "creationDate": created.timestamp()}
    if parent:
        md["parentGroupName"] = parent
    return {
        "thingGroupName": name,
        "thingGroupId": str(uuid.uuid5(uuid.NAMESPACE_URL, f"{ARN}:thinggroup/{name}")),
        "thingGroupArn": f"{ARN}:thinggroup/{name}",
        "version": 1,
        "thingGroupProperties": {"thingGroupDescription": desc},
        "thingGroupMetadata": md,
    }


RULES = (
    (
        "circularity_telemetry",
        "SELECT topic(3) AS thingName, topic() AS topic, timestamp() AS receivedAt, * FROM 'dt/+/+/telemetry'",
        "Hourly condition telemetry to the Circularity integration (HTTPS destination)",
    ),
    (
        "circularity_condition_events",
        "SELECT topic(3) AS thingName, topic() AS topic, timestamp() AS receivedAt, * FROM 'dt/+/+/events'",
        "Condition alarms (high vibration, over-temperature) to the Circularity integration",
    ),
    (
        "circularity_shadow_changes",
        "SELECT topic(3) AS thingName, topic() AS topic, current.state AS state, current.version AS version, "
        "timestamp AS timestamp FROM '$aws/things/+/shadow/update/documents'",
        "Classic shadow changes (configuration, firmware) to the Circularity integration",
    ),
)


def rule_doc(name: str, sql: str, desc: str, created: datetime) -> dict:
    return {
        "ruleArn": f"{ARN}:rule/{name}",
        "rule": {
            "ruleName": name,
            "sql": sql,
            "description": desc,
            "createdAt": created.timestamp(),
            "actions": [{"http": {"url": WEB_HOOK, "confirmationUrl": WEB_HOOK, "headers": [{"key": "x-rule", "value": name}]}}],
            "ruleDisabled": True,  # not provisioned: di enables the rules when it connects (EnableTopicRule)
            "awsIotSqlVersion": "2016-03-23",
        },
    }


def topic_filter(sql: str) -> str:
    return sql.rsplit(" FROM ", 1)[1].strip().strip("'")


def job_doc(job_id: str, group: str, status: str, created: datetime, updated: datetime, completed: datetime | None,
            desc: str, fw: str, counts: dict) -> dict:  # fmt: skip
    d = {
        "jobArn": f"{ARN}:job/{job_id}",
        "jobId": job_id,
        "targetSelection": "SNAPSHOT",
        "status": status,
        "targets": [f"{ARN}:thinggroup/{group}"],
        "description": desc,
        "presignedUrlConfig": {},
        "jobExecutionsRolloutConfig": {"maximumPerMinute": 10},
        "createdAt": created.timestamp(),
        "lastUpdatedAt": updated.timestamp(),
        "jobProcessDetails": {
            "processingTargets": [],
            "numberOfCanceledThings": 0,
            "numberOfSucceededThings": counts.get("succeeded", 0),
            "numberOfFailedThings": 0,
            "numberOfRejectedThings": 0,
            "numberOfQueuedThings": counts.get("queued", 0),
            "numberOfInProgressThings": counts.get("in_progress", 0),
            "numberOfRemovedThings": 0,
            "numberOfTimedOutThings": 0,
        },
        "documentSource": f"https://northfield-iot-jobs.s3.{REGION}.amazonaws.com/firmware/cmk3-{fw}.json",
        "thingGroupId": str(uuid.uuid5(uuid.NAMESPACE_URL, f"{ARN}:thinggroup/{group}")),
    }
    if completed:
        d["completedAt"] = completed.timestamp()
    return d


# ---------------------------------------------------------------- load
def load(conn: Connection, seed: Seed) -> dict[str, int]:
    as_of = seed.world.as_of
    created = datetime(2026, 4, 2, 6, 30, tzinfo=UTC)
    fleet = devices(seed)
    things, members, shadows, retained = [], [], [], []
    sites = sorted({d["site"] for d in fleet if d["group"] == RETURNED})
    groups = [
        (ROOT, None, "Northfield condition-monitoring kits (CMK-3)"),
        (RETURNED, ROOT, "Kits on returned assets (offline until the asset is redeployed)"),
        (PILOT, ROOT, "Kits on redeployed and re-leased assets in service (pilot)"),
    ] + [(f"returned-{s}", RETURNED, f"Returned assets at {s}") for s in sites]
    for d in fleet:
        name = thing_name(d["asset"])
        fleet_name, ttype = CLASSES[d["cls"]]
        attrs = {
            "assetTag": d["asset"],
            "assetClass": d["cls"],
            "siteCode": d["site"],
            "tenantCode": tenant_code(d["tenant"]),
            "fleet": fleet_name,
            "sensorKit": "CMK-3",
        }
        doc = {
            "defaultClientId": name,
            "thingName": name,
            "thingId": thing_id(name),
            "thingArn": f"{ARN}:thing/{name}",
            "thingTypeName": ttype,
            "attributes": attrs,
            "version": 1,
        }
        things.append(
            {
                "thing_name": name,
                "thing_type": ttype,
                "asset_tag": d["asset"],
                "fleet": fleet_name,
                "online": d["online"],
                "doc": doc,
                "profile": d["profile"],
            }  # fmt: skip
        )
        members.append({"group_name": d["group"], "thing_name": name})
        if d["group"] == RETURNED:
            members.append({"group_name": f"returned-{d['site']}", "thing_name": name})
        last, p = d["last"], d["profile"]
        ts = int(last.timestamp())
        running = d["online"]
        rep = condition_reported(d["asset"], p["hours"], p["duty"], p["vib"], p["temp"], running, last, d["events"])
        shadows.append(
            {
                "thing_name": name,
                "shadow_name": "condition",
                "state": {"reported": rep},
                "metadata": {"reported": meta(rep, ts)},
                "version": max(1, int((last - created).total_seconds() // 3600)),
                "updated_at": last,
            }  # fmt: skip
        )
        desired = {"telemetryIntervalSec": int(TELEMETRY_EVERY.total_seconds()), "firmware": d["fw_desired"]}
        reported = {"telemetryIntervalSec": desired["telemetryIntervalSec"], "firmware": d["fw"], "connected": d["online"],
                    "sensorKit": "CMK-3"}  # fmt: skip
        fw_at = int(created.timestamp()) if d["fw"] == FW_OLD else int((as_of - timedelta(days=2)).timestamp())
        md_desired = meta(desired, fw_at)
        if d["fw_desired"] == FW_NEW:
            md_desired["firmware"] = {"timestamp": int((as_of - timedelta(days=3)).timestamp())}
        shadows.append(
            {
                "thing_name": name,
                "shadow_name": "",
                "state": {"desired": desired, "reported": reported},
                "metadata": {"desired": md_desired, "reported": meta(reported, ts)},
                "version": 3 if d["fw"] == FW_NEW else 2,
                "updated_at": last,
            }  # fmt: skip
        )
        retained.append(
            {
                "topic": f"dt/{fleet_name}/{name}/telemetry",
                "payload": json.dumps(telemetry_payload(rep)).encode(),
                "qos": 1,
                "last_modified": ms(last),
            }  # fmt: skip
        )
        if d["events"]:
            e = d["events"][-1]
            retained.append(
                {"topic": f"dt/{fleet_name}/{name}/events", "payload": json.dumps(e).encode(), "qos": 1, "last_modified": e["ts"]}
            )
    pilot = [d for d in fleet if d["group"] == PILOT]
    done = sum(1 for d in pilot if d["fw"] == FW_NEW)
    jobs = [
        job_doc("fw-2-4-1-rollout", ROOT, "COMPLETED", datetime(2026, 5, 12, 4, 0, tzinfo=UTC),
                datetime(2026, 5, 20, 11, 15, tzinfo=UTC), datetime(2026, 5, 20, 11, 15, tzinfo=UTC),
                "CMK-3 firmware 2.4.1 (vibration RMS filter fix)", FW_OLD, {"succeeded": len(fleet)}),
        job_doc("fw-2-5-0-pilot", PILOT, "IN_PROGRESS", as_of - timedelta(days=3), as_of - timedelta(days=2), None,
                "CMK-3 firmware 2.5.0 (bearing temperature alarm hysteresis), pilot fleet first", FW_NEW,
                {"succeeded": done, "queued": len(pilot) - done - 2, "in_progress": 2}),
    ]  # fmt: skip
    conn.execute(insert(t.THING), things)
    conn.execute(
        insert(t.THING_GROUP), [{"group_name": g, "parent": p, "doc": group_doc(g, p, desc, created)} for g, p, desc in groups]
    )
    conn.execute(insert(t.GROUP_MEMBER), members)
    conn.execute(insert(t.SHADOW), shadows)
    conn.execute(insert(t.RETAINED), retained)
    conn.execute(
        insert(t.RULE),
        [
            {"rule_name": n, "topic_filter": topic_filter(sql), "disabled": True, "doc": rule_doc(n, sql, desc, created)}
            for n, sql, desc in RULES
        ],
    )
    conn.execute(insert(t.JOB), [{"job_id": j["jobId"], "status": j["status"], "doc": j} for j in jobs])
    schedule_telemetry(conn, as_of + TELEMETRY_EVERY)
    return {"thing": len(things), "thing_group": len(groups), "shadow": len(shadows), "retained": len(retained), "job": len(jobs)}


def schedule_telemetry(conn: Connection, due: datetime) -> None:
    from sim.vendors.aws_iot import fleet  # registers the handler

    scheduler.schedule(conn, due, fleet.HANDLER, {}, source=SOURCE)


def create(conn: Connection) -> None:
    conn.execute(text("CREATE SCHEMA IF NOT EXISTS aws_iot"))
    t.metadata.create_all(conn)


def reset(conn: Connection, seed: Seed) -> dict[str, int]:
    t.metadata.drop_all(conn)
    create(conn)
    return load(conn, seed)


def ensure(conn: Connection, seed: Seed) -> None:
    create(conn)
    if conn.execute(text("SELECT count(*) FROM aws_iot.thing")).scalar_one() == 0:
        load(conn, seed)
        return
    from sim.vendors.aws_iot import fleet

    pending = conn.execute(
        text("SELECT count(*) FROM sim.scheduled WHERE handler = :h AND NOT done"), {"h": fleet.HANDLER}
    ).scalar_one()
    if not pending:  # e.g. scheduled work was cleared by a full reset of another kind: keep the fleet reporting
        schedule_telemetry(conn, seed.world.as_of + TELEMETRY_EVERY)
