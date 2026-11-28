"""P9-6.1: the device registry, lab and market mocks (dvreg, dvlab, dvmkt) and the deterministic world they share.

Synthetic, not demo sources: they register beside the demo's systems (sim/core/registry.py EXTRA_SYSTEMS), so the demo's
systems and counts stay as they were. Stories DV-02 ... DV-13 read this data.
"""

import json
from collections import Counter

import pytest
from fastapi.testclient import TestClient

from sim.core.registry import BY_SOURCE_ID, CATALOG_BY_ID, EXTRA_BY_ID, SYSTEMS
from sim.generic.spec import credentials
from sim.generic.specs import device_lab
from sim.main import MOCKS, app
from sim.seed import devices

SAMPLE = "359990000000428"
LAB, REG, MKT = "/device-lab/v1", "/device-registry/v1", "/device-market/v1"


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        for sid in ("dvreg", "dvlab", "dvmkt"):
            c.post("/_sim/reset", params={"system": sid}).raise_for_status()
        yield c


@pytest.fixture(scope="module")
def lab(client):
    c = credentials(device_lab.SPEC)
    tok = client.post(LAB + "/oauth/token", data={"grant_type": "client_credentials"}, auth=(c["client_id"], c["client_secret"]))
    assert tok.status_code == 200, tok.text
    return {"Authorization": "Bearer " + tok.json()["access_token"]}


REG_H = {"X-Api-Key": "dvreg-demo-key"}
MKT_H = {"X-Api-Key": "dvmkt-demo-key"}


def listing(client, path: str, headers: dict, **params) -> list[dict]:
    r = client.get(path, headers=headers, params={"limit": 200} | params)
    assert r.status_code == 200, r.text
    return r.json()["items"]


# ------------------------------------------------------------------ the world
def test_device_world_counts():
    w = devices.build()
    assert len(w.tradeins) == 600
    assert sum(c["blacklist"] != "clear" for c in w.checks) == 15
    assert sum(c["activationLock"] == "on" for c in w.checks) == 24
    assert sum(c["finance"] == "balance_owed" for c in w.checks) == 12
    assert len(w.mismatches()) == 30
    batch = [t["imei"] for t in w.tradeins if t["batchId"] == "BATCH-0007"]
    wiped = {x["imei"] for x in w.wipes}
    assert len(batch) == 40 and sum(i not in wiped for i in batch) == 12
    assert len(w.disputes) == 50
    assert sum(d["partner"] in ("P02", "P04") and d["reason"] == "Screen graded before power-on" for d in w.disputes) == 29
    assert len(w.prices) == 52 * 20 * 4  # 10 models x 2 storage sizes x 4 grades x 52 weeks
    assert len(w.listings) == 60 and len(w.sales) == 400


def test_device_world_is_deterministic():
    a, b = devices.build(), devices.build()
    assert json.dumps(a.as_dict(), sort_keys=True) == json.dumps(b.as_dict(), sort_keys=True)
    assert devices.world() is devices.world()


def test_device_world_shape():
    w = devices.build()
    assert {t["sku"]["model"] for t in w.tradeins} == {m[1] for m in devices.DMOD}
    assert {t["sku"]["storageGb"] for t in w.tradeins} == {128, 256}
    assert all("2026-08-08" <= t["receivedAt"][:10] <= "2026-10-07" for t in w.tradeins)
    s = next(t for t in w.tradeins if t["imei"] == SAMPLE)
    assert (s["sku"]["model"], s["sku"]["storageGb"], s["quote"]["declaredGrade"], s["quote"]["amount"], s["partner"]) == (
        "iPhone 14", 128, "B", 410, "P01")
    assert next(g for g in w.gradings if g["imei"] == SAMPLE)["cosmeticGrade"] == "B"
    assert next(d for d in w.diagnostics if d["imei"] == SAMPLE)["batteryHealthPct"] == 84
    assert not any(d["imei"] == SAMPLE for d in w.disputes) and SAMPLE not in w.mismatches()


def test_device_world_market_facts():
    w = devices.build()
    # a weekly price per SKU and grade, 52 weeks
    assert set(Counter((p["skuKey"], p["grade"]) for p in w.prices).values()) == {52}
    # the successor launch and its realised prices 8-12% below the feed for 3 weeks
    (launch,) = w.launches
    assert (launch["name"], launch["replaces"], launch["launchDate"]) == ("Galaxy S24 successor", "Galaxy S24", "2026-09-14")
    feed = {(p["skuKey"], p["grade"], p["week"]): p["price"] for p in w.prices}
    hit = [s for s in w.sales if s["model"] == "Galaxy S24" and "2026-09-14" <= s["settledAt"][:10] < "2026-10-05"]
    assert hit
    for s in hit:
        ratio = s["price"] / feed[(s["skuKey"], s["grade"], s["week"])]
        assert 0.88 <= ratio <= 0.92, s
    # listings: 12 Offers >= 14 days with no offer, 9 Buy Now unsold >= 21 days
    asof = "2026-10-07T09:00:00+00:00"
    from datetime import datetime

    def age(x):
        return (datetime.fromisoformat(asof) - datetime.fromisoformat(x["listedAt"])).days

    assert sum(x["channel"] == "Offers" and x["offers"] == 0 and age(x) >= 14 for x in w.listings) == 12
    assert sum(x["channel"] == "Buy Now" and age(x) >= 21 for x in w.listings) == 9
    assert all(x["status"] == "live" for x in w.listings)
    # settled sales over 12 weeks; replacement demand for 3 SKUs; a repair quote
    assert all("2026-07-15" <= x["settledAt"][:10] <= "2026-10-07" for x in w.sales)
    assert len(w.replacement_demand) == 3
    d = next(x for x in w.replacement_demand if x["skuKey"] == "iPhone 14|128")
    assert (d["minGrade"], d["units"], d["price"]) == ("B", 5, 340)
    assert any((q["repair"], q["cost"], q["priceUplift"], q["days"]) == ("Battery swap", 24, 28, 5) for q in w.repair_quotes)


# ------------------------------------------------------------------ registration
def test_device_mocks_registered_as_extra(client):
    assert [s.source_id for s in SYSTEMS][-1] == "iot" and len(SYSTEMS) == 21
    for sid in ("dvreg", "dvlab", "dvmkt"):
        assert EXTRA_BY_ID[sid].style == "generic-rest"
        assert sid not in BY_SOURCE_ID and sid not in CATALOG_BY_ID and sid in MOCKS
    assert (EXTRA_BY_ID["dvreg"].base_path, EXTRA_BY_ID["dvlab"].base_path, EXTRA_BY_ID["dvmkt"].base_path) == (
        REG, LAB, MKT)
    listed = [s["source_id"] for s in client.get("/_sim/systems").json()]
    demo = [s.source_id for s in SYSTEMS]
    assert listed[:21] == demo and {"dvreg", "dvlab", "dvmkt"} <= set(listed[21:])
    assert client.get("/health").json()["systems"] == 21


# ------------------------------------------------------------------ served
def test_sample_device_served(client, lab):
    (t,) = listing(client, LAB + "/tradeins", lab, imei=SAMPLE)
    assert t["quote"]["amount"] == 410 and t["quote"]["declaredGrade"] == "B" and t["sku"]["model"] == "iPhone 14"
    (c,) = listing(client, REG + "/checks", REG_H, imei=SAMPLE)
    assert (c["blacklist"], c["activationLock"], c["finance"]) == ("clear", "off", "clear")
    assert client.get(REG + "/checks").status_code == 401 and client.get(LAB + "/tradeins").status_code == 401


def test_photo_is_a_labelled_svg_data_uri(client, lab):
    photos = listing(client, LAB + "/photos", lab, imei=SAMPLE)
    assert {p["view"] for p in photos} == {"front", "back", "screen"}
    assert all(p["image"].startswith("data:image/svg+xml") and len(p["image"]) < 2000 for p in photos)
    assert any("front" in p["image"] for p in photos if p["view"] == "front")


def test_lot_w_0001_bids(client):
    (lot,) = listing(client, MKT + "/lots", MKT_H, lotRef="LOT-W-0001")
    assert (lot["model"], lot["grade"], lot["units"]) == ("Galaxy S23", "C", 100)
    bids = listing(client, MKT + "/bids", MKT_H, lotRef="LOT-W-0001")
    assert sorted(b["buyerCode"] for b in bids) == [f"B0{i}" for i in range(1, 7)]
    net = {b["buyerCode"]: b["amount"] - b["fees"] - b["logistics"] for b in bids}
    assert max(b["amount"] for b in bids) == next(b["amount"] for b in bids if b["buyerCode"] == "B05")
    best = max((v, k) for k, v in net.items() if k != "B05")
    assert best[0] == 310 and best[0] * lot["units"] == 31_000


def test_wipe_create_emits_event(client, lab):
    batch = {t["imei"] for t in listing(client, LAB + "/tradeins", lab, batchId="BATCH-0007")}
    wiped = {w["imei"] for off in (0, 200, 400) for w in listing(client, LAB + "/wipes", lab, offset=off)}
    todo = sorted(batch - wiped)
    assert len(batch) == 40 and len(todo) == 12
    r = client.post(LAB + "/wipes", headers=lab, json={"imei": todo[0], "method": "Purge", "verification": "pass", "operator": "OP-03"})
    assert r.status_code == 201, r.text
    assert r.json()["imei"] == todo[0]
    from sqlalchemy import text

    from sim.core.db import engine

    with engine.connect() as conn:
        n = conn.execute(
            text("select count(*) from sim.outbox where source = 'dvlab' and type = 'devicelab.wipe.created' and subject = :s"),
            {"s": r.json()["certificateId"]},
        ).scalar()
    assert n == 1


def test_sales_give_every_sku_twenty_sold_devices():
    """GR-D8 of the device pack needs 20 sales of a SKU in 90 days (`min_sales_90d`): the seed sells at least 20 distinct
    devices of every SKU, each sale of devices of its own SKU (lead decision 28 Nov: the seed, never the guardrail)."""
    w = devices.build()
    sku = {t["imei"]: devices.sku_key(t["sku"]["model"], t["sku"]["storageGb"]) for t in w.tradeins}
    sold: dict[str, set[str]] = {}
    for s in w.sales:
        assert all(sku[i] == s["skuKey"] for i in s["imeis"])
        sold.setdefault(s["skuKey"], set()).update(s["imeis"])
    assert len(sold) == 20 and min(len(v) for v in sold.values()) >= 20


def test_listing_post_is_stamped_listed_now(client):
    """A listing the app posts carries no `listedAt`: the market stamps it at the simulated time (the dvmkt sync reads it)."""
    body = {"listingId": "RT-9999:offers", "imei": SAMPLE, "skuKey": "iPhone 14|128", "grade": "B", "channel": "Offers",
            "price": 300.0, "offers": 0, "status": "live"}  # fmt: skip
    r = client.post(MKT + "/listings", headers=MKT_H, json=body)
    assert r.status_code == 201, r.text
    assert r.json()["listedAt"] and r.json()["listedAt"] == r.json()["createdAt"]
    stamped = {"listedAt": "2026-10-01T09:00:00+00:00"}
    r = client.post(MKT + "/listings", headers=MKT_H, json=body | {"listingId": "RT-9999:auction"} | stamped)
    assert r.status_code == 201 and r.json()["listedAt"] == stamped["listedAt"]
