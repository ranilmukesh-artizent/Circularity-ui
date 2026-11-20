"""B5b contract tests: the Sims Lifecycle Services drop, read the way a partner SFTP client reads it (asyncssh client).

Each test starts the mock's SFTP server on a free port in this process (the same code the service runs on 2222), so
the tests do not depend on the running service having reloaded. One test also checks the service's port 2222.
"""

import asyncio
import csv
import hashlib
import hmac
import io
import json

import asyncssh
import pytest
from fastapi.testclient import TestClient

from sim.main import app
from sim.vendors.sims import drop, sftp

KEY = b"rcy-demo-signing-key"
CSVS = ["custody-certificates.csv", "material-yields.csv", "partner-rates.csv", "vendor-approvals.csv"]
TIMEOUT = 20


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        c.post("/_sim/reset", params={"system": "rcy"}).raise_for_status()
        yield c
        c.post("/_sim/reset", params={"system": "rcy"}).raise_for_status()


async def _session(fn, port=None, user=sftp.USER, password=sftp.PASSWORD, known_hosts=None):
    server = await sftp.serve(0, "127.0.0.1") if port is None else None
    p = port or server.sockets[0].getsockname()[1]
    try:
        async with asyncssh.connect(  # noqa: SIM117 - the SFTP client needs the connection opened first
            "127.0.0.1", p, username=user, password=password, known_hosts=known_hosts, connect_timeout=TIMEOUT
        ) as conn:
            async with conn.start_sftp_client() as s:
                return await fn(s)
    finally:
        if server is not None:
            server.close()


def run(fn, **kw):
    return asyncio.run(asyncio.wait_for(_session(fn, **kw), TIMEOUT))


async def fetch_all(s) -> dict[str, tuple[bytes, int]]:
    out = {}
    for name in await s.listdir("/outbound"):
        if name in (".", ".."):
            continue
        async with s.open(f"/outbound/{name}", "rb") as f:
            data = await f.read()
        out[name] = (data, (await s.stat(f"/outbound/{name}")).mtime)
    return out


def test_layout_signatures_and_manifest(client):
    files = run(fetch_all)
    names = [*CSVS, "manifest.json"]
    assert sorted(files) == sorted(names + [n + ".sig" for n in names])
    for name, (data, mtime) in files.items():
        assert mtime == 1791190800  # 2026-10-05T09:00:00Z: 2 days before the as-of time
        if not name.endswith(".sig"):
            sig = files[name + ".sig"][0].decode().strip()
            assert hmac.compare_digest(sig, hmac.new(KEY, data, hashlib.sha256).hexdigest()), name
    manifest = json.loads(files["manifest.json"][0])
    assert manifest["partner"] == "Sims Lifecycle Services"
    assert {e["fileName"] for e in manifest["files"]} == set(CSVS)
    for e in manifest["files"]:
        data = files[e["fileName"]][0]
        assert e["sha256"] == hashlib.sha256(data).hexdigest() and e["size"] == len(data)
    rates = {r["MATERIAL"]: r for r in csv.DictReader(io.StringIO(files["partner-rates.csv"][0].decode()))}
    assert rates["Cu"]["RATE_TNE"] == "Cu 7.8k" and rates["Cu"]["RATE_INR_KG"] == "650.00"
    vendors = {r["VENDOR_ID"]: r for r in csv.DictReader(io.StringIO(files["vendor-approvals.csv"][0].decode()))}
    assert vendors["SIMS-MAA"]["VND_CERT"] == "ISO14001-VA" and vendors["SIMS-MAA"]["STATUS"] == "APPROVED"


def test_pinned_host_key_and_login():
    known = asyncssh.import_known_hosts(f"127.0.0.1 {' '.join(sftp.HOST_KEY)}\n")

    async def names(s):
        return await s.listdir("/")

    assert "outbound" in run(names, known_hosts=known)
    with pytest.raises(asyncssh.PermissionDenied):
        run(names, password="wrong")


def test_read_only_and_chrooted(client):
    async def attempts(s):
        out = []
        for op in (
            lambda: s.remove("/outbound/manifest.json"),
            lambda: s.rename("/outbound/manifest.json", "/outbound/m.json"),
            lambda: s.mkdir("/inbound"),
            lambda: s.open("/outbound/new.csv", "w"),
        ):
            try:
                await op()
                out.append("allowed")
            except asyncssh.SFTPPermissionDenied:
                out.append("denied")
        out.append(sorted(await s.listdir("/../../..")))
        return out

    *ops, top = run(attempts)
    assert ops == ["denied"] * 4 and top == [".", "..", "outbound"]
    assert drop.read("manifest.json") is not None


def test_admin_view_tamper_and_reset_regenerates(client):
    listing = client.get("/sims/admin/outbound").json()
    assert listing["sftp"]["port"] == 2222 and listing["sftp"]["hostKey"].startswith("ssh-ed25519 ")
    assert len(listing["files"]) == 10
    original = client.get("/sims/admin/outbound/partner-rates.csv").content
    tampered = original.replace(b"650.00", b"950.00")
    assert client.put("/sims/admin/outbound/partner-rates.csv", content=tampered).status_code == 200
    assert client.put("/sims/admin/outbound/..%2Fx", content=b"x").status_code in (400, 404)

    async def rates(s):
        async with s.open("/outbound/partner-rates.csv", "rb") as f:
            return await f.read(), (await s.stat("/outbound/partner-rates.csv")).mtime

    data, mtime = run(rates)
    assert data == tampered and mtime > 1791190800  # stamped with the simulated time
    sig = drop.read("partner-rates.csv.sig").decode().strip()
    assert sig != hmac.new(KEY, data, hashlib.sha256).hexdigest()  # not signed again

    client.post("/_sim/reset", params={"system": "rcy"}).raise_for_status()
    data, mtime = run(rates)
    assert data == original and mtime == 1791190800

    pub = client.post("/sims/admin/publish").json()
    assert pub["files"] == 10
    data, mtime = run(rates)
    assert data == original and mtime > 1791190800
    client.post("/sims/admin/regenerate").raise_for_status()
    assert run(rates)[1] == 1791190800


def test_service_serves_port_2222(client):
    async def names(s):
        return await s.listdir("/outbound")

    assert "manifest.json" in run(names, port=sftp.port())
