"""Sims Lifecycle Services (rcy): the partner's signed CSV drop over SFTP (the demo's SOURCES.rcy, "SFTP drop ·
signed manifest"). Read only. A real SFTP client (paramiko) against source-sim's SFTP server (port 2222).

Connection: host from DI_SIMS_SFTP_HOST (default: the host of source_sim_url, i.e. source-sim), port
DI_SIMS_SFTP_PORT (2222), user di-connector / password rcy-demo, the partner's Ed25519 host key pinned (HOST_KEY):
a different key is refused as an auth failure, as is a refused login; no answer is "unavailable".
Every SFTP operation (connect, list, get) is written to fetch_log with method SFTP and SSH_FX status codes (0 = OK).

The drop (/outbound): four CSV files, manifest.json, and a detached signature per file (<file>.sig, HMAC-SHA256 hex
with the partner's signing key). Before a file is used:
    - manifest.json must match its signature;
    - the file must be listed in the manifest, its bytes must hash to the manifest's SHA-256 and size, and its own
      signature must verify.
A file that fails is one failed record (the run is partial, nothing from that file is used); the others import.
Delta: each file's modification time (st_mtime) is the record's `changed`; a read with a cursor only imports files
modified after it (vendor-approvals.csv is still downloaded, verified, for the VND_CERT → vendor lookup). An
unchanged drop reads 0 records and downloads nothing but the listing.

Facts (rcy has authority over vendor certification)
    vendor.<VENDOR_ID>   certification (certified / lapsed / …), cert_ref, cert_status, cert_standard, cert_valid_to,
                         name, material_rates {material: usd_per_t, inr_per_kg, basis, label, valid_from}, rebates,
                         fees, yields {asset class: {material: kg per unit}}, custody_certificates
The demo's mapping: VND_CERT ISO14001-VA → vendor.certification certified (Certificate table); RATE_TNE "Cu 7.8k" →
Cu $7,800 / t (Unit + currency; ₹650/kg at 83.5 INR/USD = $7,784/t).
"""

import contextlib
import csv
import hashlib
import hmac
import io
import json
import os
import socket
import time
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from urllib.parse import urlparse

import paramiko
from sqlalchemy import text

from di.canonical.store import Fact
from di.config import get_settings
from di.connectors.base import Adapter, Record, Resource
from di.connectors.generic import INR_PER_USD, keep
from di.connectors.http import Auth, SourceClient, SourceError

SIGNING_KEY = b"rcy-demo-signing-key"  # the partner's signing key (demo value)
USER, PASSWORD = "di-connector", "rcy-demo"


class SftpLogin(Auth):
    """The SFTP user and password (no HTTP headers): the stored secret, or the partner's demo password."""

    def __init__(self, user: str, password: str):
        self.user, self.password = user, password
HOST_KEY = ("ssh-ed25519", "AAAAC3NzaC1lZDI1NTE5AAAAIICdS6y8VTdaxChH2KIr/5NFdZfbbDo9/WELgbDCNDuf")
DIR = "/outbound"
TIMEOUT = 20
CERT_TABLE = {"APPROVED": "certified", "LAPSED": "lapsed", "SUSPENDED": "suspended", "PENDING": "pending"}
FX_OK, FX_FAILURE = 0, 4  # SSH_FX status codes, stored as the fetch-log status


class IntegrityError(Exception):
    pass


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def signature(data: bytes) -> str:
    return hmac.new(SIGNING_KEY, data, hashlib.sha256).hexdigest()


def verified(data: bytes, sig: bytes | None) -> bool:
    return sig is not None and hmac.compare_digest(signature(data), sig.decode(errors="replace").strip())


def mtime_iso(ts: float | None) -> str:
    if ts is None:  # the drop always sends modification times
        raise ValueError("the SFTP listing has no modification time")
    return datetime.fromtimestamp(int(ts), UTC).isoformat()


def after(ts: float | None, since: str | None) -> bool:
    if not since:
        return True
    if ts is None:  # the drop always sends modification times
        raise ValueError("the SFTP listing has no modification time")
    s = datetime.fromisoformat(since.replace("Z", "+00:00"))
    return datetime.fromtimestamp(int(ts), UTC) > (s if s.tzinfo else s.replace(tzinfo=UTC))


def rate_label(code: str, usd_per_t: int) -> str:
    """Cu, 7784 → 'Cu $7,800 / t' (to the nearest hundred, as the partner quotes)."""
    return f"{code} ${round(usd_per_t, -2):,} / t"


class Drop:
    """One SFTP session on the partner's drop, logged to fetch_log."""

    def __init__(self, client: SourceClient, host: str, port: int, user: str = USER, password: str = PASSWORD):
        self.client, self.host, self.port, self.user = client, host, port, user
        self.transport: paramiko.Transport | None = None
        self.sftp: paramiko.SFTPClient | None = None
        t0 = time.perf_counter()
        try:
            sock = socket.create_connection((host, port), timeout=TIMEOUT)
            self.transport = paramiko.Transport(sock)
            self.transport.banner_timeout = self.transport.auth_timeout = TIMEOUT
            self.transport.start_client(timeout=TIMEOUT)
            key = self.transport.get_remote_server_key()
            if (key.get_name(), key.get_base64()) != HOST_KEY:
                raise SourceError("auth", f"rcy: host key {key.get_name()} {key.get_base64()[:16]}… is not the partner's")
            self.transport.auth_password(user, password)
            self.sftp = paramiko.SFTPClient.from_transport(self.transport)
            channel = self.sftp.get_channel() if self.sftp else None
            if channel is None:  # not reached: the transport above is open and authenticated
                raise SourceError("unavailable", f"rcy: SFTP {host}:{port}: no SFTP channel")
            channel.settimeout(TIMEOUT)
        except SourceError as e:
            self._log("connect", self.url(""), FX_FAILURE, None, t0, str(e))
            self.close()
            raise
        except paramiko.AuthenticationException as e:
            self._log("connect", self.url(""), FX_FAILURE, None, t0, f"login refused: {e}")
            self.close()
            raise SourceError("auth", f"rcy: SFTP login refused for {user}") from e
        except (OSError, paramiko.SSHException) as e:
            self._log("connect", self.url(""), FX_FAILURE, None, t0, f"{type(e).__name__}: {e}")
            self.close()
            raise SourceError("unavailable", f"rcy: SFTP {host}:{port}: {type(e).__name__}: {e}") from e
        self._log("connect", self.url(""), FX_OK, None, t0, None)

    def url(self, path: str) -> str:
        return f"sftp://{self.user}@{self.host}:{self.port}{path}"

    def _session(self) -> paramiko.SFTPClient:
        if self.sftp is None:  # not reached: __init__ opens the session or raises
            raise SourceError("unavailable", "rcy: the SFTP session is not open")
        return self.sftp

    def listdir(self, path: str = DIR) -> dict[str, paramiko.SFTPAttributes]:
        t0 = time.perf_counter()
        try:
            entries = {a.filename: a for a in self._session().listdir_attr(path)}
        except (OSError, paramiko.SSHException) as e:
            self._log("list", self.url(path + "/"), FX_FAILURE, None, t0, str(e))
            raise SourceError("unavailable", f"rcy: SFTP list {path}: {e}") from e
        self._log("list", self.url(path + "/"), FX_OK, len(entries), t0, None)
        return entries

    def get(self, name: str) -> bytes | None:
        """A file's bytes, or None if it is not there."""
        path = f"{DIR}/{name}"
        t0 = time.perf_counter()
        try:
            with self._session().open(path, "rb") as f:
                data = f.read()
        except FileNotFoundError:
            self._log("get", self.url(path), 2, None, t0, "no such file")  # SSH_FX_NO_SUCH_FILE
            return None
        except (OSError, paramiko.SSHException) as e:
            self._log("get", self.url(path), FX_FAILURE, None, t0, str(e))
            raise SourceError("unavailable", f"rcy: SFTP get {path}: {e}") from e
        rows = data.count(b"\n") - 1 if name.endswith(".csv") else None
        self._log("get", self.url(path), FX_OK, rows, t0, None)
        return data

    def close(self) -> None:
        for c in (self.sftp, self.transport):
            if c is not None:
                with contextlib.suppress(Exception):  # closing a broken session
                    c.close()

    def _log(self, op: str, url: str, status: int, records: int | None, t0: float, error: str | None) -> None:
        """fetch_log row: method SFTP; the operation leads the URL column's note (connect / list / get)."""
        self.client.session.execute(
            text(
                "INSERT INTO fetch_log (run_id, source_id, method, url, status, records, duration_ms, error) "
                "VALUES (:r, :s, 'SFTP', :u, :st, :n, :d, :e)"
            ),
            {
                "r": self.client.run_id,
                "s": self.client.source_id,
                "u": f"{op.upper()} {url}"[:2000],
                "st": status,
                "n": records,
                "d": int((time.perf_counter() - t0) * 1000),
                "e": (error or None) and error[:500],
            },
        )


def sftp_target() -> tuple[str, int]:
    host = os.environ.get("DI_SIMS_SFTP_HOST") or urlparse(get_settings().source_sim_url).hostname or "localhost"
    return host, int(os.environ.get("DI_SIMS_SFTP_PORT", "2222"))


class SimsAdapter(Adapter):
    source_id = "rcy"
    base_path = "/sims"  # source-sim's admin view; the data itself comes over SFTP (sftp_target)

    def auth(self, conn=None, secret=None) -> Auth:  # noqa: ARG002 - conn: the Adapter interface
        return SftpLogin(USER, secret or PASSWORD)  # no HTTP headers: Drop signs in over SFTP with it

    def resources(self):
        return [Resource("files", self.read_files)]

    def read_files(self, client: SourceClient, since: str | None):
        login = client.auth if isinstance(client.auth, SftpLogin) else SftpLogin(USER, PASSWORD)
        drop = Drop(client, *sftp_target(), user=login.user, password=login.password)
        try:
            yield from self.read_drop(drop, since)
        finally:
            drop.close()

    def read_drop(self, drop: Drop, since: str | None):
        listing = drop.listdir()
        csvs = sorted(n for n in listing if n.endswith(".csv"))
        changed = [n for n in csvs if after(listing[n].st_mtime, since)]
        if not changed:
            return
        manifest, manifest_error = None, None
        mf = drop.get("manifest.json") if "manifest.json" in listing else None
        if mf is None:
            manifest_error = "manifest.json is missing"
        elif not verified(mf, drop.get("manifest.json.sig")):
            manifest_error = "manifest.json: signature does not verify"
        else:
            try:
                manifest = {e["fileName"]: e for e in json.loads(mf)["files"]}
            except (ValueError, KeyError, TypeError) as e:
                manifest_error = f"manifest.json: unreadable ({e})"

        def problem(name: str, data: bytes) -> str | None:
            if manifest_error:
                return manifest_error
            entry = manifest.get(name) if manifest is not None else None  # set whenever there is no manifest_error
            if entry is None:
                return f"{name} is not in the manifest"
            actual = sha256(data)
            if actual != entry.get("sha256"):
                return f"{name}: SHA-256 {actual[:12]}… does not match the manifest ({str(entry.get('sha256'))[:12]}…)"
            if entry.get("size") is not None and entry["size"] != len(data):
                return f"{name}: size {len(data)} does not match the manifest ({entry['size']})"
            if not verified(data, drop.get(name + ".sig") if name + ".sig" in listing else None):
                return f"{name}: signature does not verify"
            return None

        def failed(name: str, error: str, digest: str | None, ts: float | None) -> Record:
            payload = {"file": name, "integrity_error": error, "sha256": digest}
            changed_at: Any = ts and mtime_iso(ts)
            return Record(name.removesuffix(".csv"), name, payload, drop.url(f"{DIR}/{name}"), changed_at)

        tables: dict[str, list[dict]] = {}
        wanted = set(changed) | ({"vendor-approvals.csv"} & set(csvs))  # approvals: the VND_CERT → vendor lookup
        for name in csvs:
            if name not in wanted:
                continue
            data = drop.get(name) or b""
            err = problem(name, data)
            if err:
                if name in changed:
                    yield failed(name, err, sha256(data), listing[name].st_mtime)
                continue
            tables[name] = list(csv.DictReader(io.StringIO(data.decode("utf-8"))))
        if manifest and since is None:  # a file the manifest promises but the drop lacks
            for name in sorted(set(manifest) - set(csvs)):
                yield failed(name, f"{name} is in the manifest but not in {DIR}", None, None)

        def meta(name: str) -> tuple[str, str]:
            return drop.url(f"{DIR}/{name}"), mtime_iso(listing[name].st_mtime)

        approvals = tables.get("vendor-approvals.csv", [])
        vendor_of = {r["VND_CERT"]: r["VENDOR_ID"] for r in approvals}
        if "vendor-approvals.csv" in changed:
            url, ts = meta("vendor-approvals.csv")
            for r in approvals:
                yield Record("vendor-approvals", r["VENDOR_ID"], r, url, ts)
        for name, resource in (
            ("partner-rates.csv", "partner-rates"),
            ("material-yields.csv", "material-yields"),
            ("custody-certificates.csv", "custody-certificates"),
        ):
            if name not in changed or name not in tables:
                continue
            url, ts = meta(name)
            groups: dict[str, list[dict]] = {}
            for r in tables[name]:
                vid = r.get("VENDOR_ID") or vendor_of.get(r.get("VND_CERT") or "")
                if vid:
                    groups.setdefault(vid, []).append(r)
            for vid, rows in sorted(groups.items()):
                yield Record(resource, vid, {"VENDOR_ID": vid, "rows": rows}, url, ts)

    def map(self, record: Record) -> list[Fact]:
        p = record.payload
        if "integrity_error" in p:
            raise IntegrityError(p["integrity_error"])
        if record.resource == "vendor-approvals":
            return keep(self._approval(p))
        key = p["VENDOR_ID"]
        rows = p["rows"]
        if record.resource == "partner-rates":
            rates = {}
            for r in rows:
                inr = Decimal(r["RATE_INR_KG"])
                usd_t = int((inr * 1000 / INR_PER_USD).quantize(Decimal("1")))
                rates[r["MATERIAL"]] = {
                    "usd_per_t": usd_t,
                    "inr_per_kg": float(inr),
                    "basis": r.get("BASIS"),
                    "label": rate_label(r["MATERIAL"], usd_t),
                    "valid_from": r.get("VALID_FROM"),
                }
            return [
                Fact("vendor", key, "material_rates", rates, "RATE_TNE", [r["RATE_TNE"] for r in rows], "Unit + currency"),
                Fact(
                    "vendor",
                    key,
                    "rebates",
                    {m: v["usd_per_t"] for m, v in rates.items() if v["basis"] == "rebate"},
                    "RATE_INR_KG",
                    [f"{r['MATERIAL']} {r['RATE_INR_KG']}" for r in rows if r.get("BASIS") == "rebate"],
                    "INR/kg → USD/t at 83.5 INR/USD",
                ),
                Fact(
                    "vendor",
                    key,
                    "fees",
                    {m: -v["usd_per_t"] for m, v in rates.items() if v["basis"] == "fee"},
                    "RATE_INR_KG",
                    [f"{r['MATERIAL']} {r['RATE_INR_KG']}" for r in rows if r.get("BASIS") == "fee"],
                    "INR/kg → USD/t at 83.5 INR/USD (fee charged)",
                ),
            ]
        if record.resource == "material-yields":
            yields: dict[str, dict[str, float]] = {}
            for r in rows:
                yields.setdefault(r["ASSET_CLASS"], {})[r["MATERIAL"]] = float(r["KG_PER_UNIT"])
            return [
                Fact(
                    "vendor",
                    key,
                    "yields",
                    yields,
                    "KG_PER_UNIT",
                    [f"{r['ASSET_CLASS']} {r['MATERIAL']} {r['KG_PER_UNIT']}" for r in rows],
                    "kg per unit by asset class",
                )
            ]
        if record.resource == "custody-certificates":
            certs = [
                {
                    "ref": r["CERT_ID"],
                    "decision_id": r.get("DECISION_ID"),
                    "asset_id": r.get("ASSET_ID"),
                    "asset_class": r.get("ASSET_CLASS"),
                    "qty": int(r["QTY"]) if r.get("QTY") else None,
                    "route": r.get("ROUTE"),
                    "processed_on": r.get("PROCESSED_ON"),
                }
                for r in rows
            ]
            return [Fact("vendor", key, "custody_certificates", certs, "CERT_ID", [r["CERT_ID"] for r in rows], "Pass-through")]
        return []

    def _approval(self, r: dict) -> list[Fact]:
        key = r["VENDOR_ID"]
        status = r.get("STATUS") or ""
        return [
            Fact(
                "vendor",
                key,
                "certification",
                CERT_TABLE.get(status, status.lower() or None),
                "VND_CERT",
                r["VND_CERT"],
                "Certificate table",
            ),
            Fact("vendor", key, "cert_ref", r["VND_CERT"], "VND_CERT", r["VND_CERT"], "Pass-through"),
            Fact("vendor", key, "cert_status", status.lower() or None, "STATUS", status, "Status map"),
            Fact("vendor", key, "cert_standard", r.get("CERT_STANDARD"), "CERT_STANDARD", r.get("CERT_STANDARD"), "Pass-through"),
            Fact("vendor", key, "cert_valid_to", r.get("VALID_TO"), "VALID_TO", r.get("VALID_TO"), "ISO date"),
            Fact("vendor", key, "name", r.get("VENDOR_NAME"), "VENDOR_NAME", r.get("VENDOR_NAME"), "Pass-through"),
        ]


ADAPTER = SimsAdapter()
