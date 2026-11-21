"""Probe a source's connection against the system it reads (the Connection Fabric's Test connection; B17, plan 6 A5).

    probe(session, "erp")                        → Probe(dns, tcp, tls, auth, perms, read)   each a Check
    probe_connection(session, sid, adapter, conn, secret)   the same for a connection not stored yet (a catalogue
                                                            system being connected)

Every check is real, against the connection's own URL (di.connectors.connection):
    dns    the host resolves; `detail` is the address it resolved to
    tcp    a connection to host:port opens
    tls    https: a TLS handshake with certificate verification; `detail` is the protocol and the certificate's expiry.
           http: no handshake, `warn` set and `detail` "Not encrypted: http"
    auth   the stored credential has not expired, and the adapter signs in (401: refused or expired)
    perms  one record is read from each read resource; the first refused (403, or any 4xx) is named
    read   the first record of the first resource, timed
Each call is written to the fetch log like a sync's (without a run). No record is stored.
"""

import socket
import ssl
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from di import clock
from di.connectors import connection, secrets
from di.connectors.http import SourceClient, SourceError
from di.connectors.registry import adapter_for


@dataclass
class Check:
    ok: bool
    ms: int = 0
    error: str = ""
    status: int | None = None
    detail: str = ""
    warn: bool = False


SKIPPED = Check(False, error="not reached")


@dataclass
class Probe:
    dns: Check
    tcp: Check = field(default_factory=lambda: SKIPPED)
    tls: Check = field(default_factory=lambda: SKIPPED)
    auth: Check = field(default_factory=lambda: SKIPPED)
    perms: Check = field(default_factory=lambda: SKIPPED)
    read: Check = field(default_factory=lambda: SKIPPED)
    records: int = 0
    resources: int = 0
    host: str = ""


def _ms(t0: float) -> int:
    return max(1, round((time.perf_counter() - t0) * 1000))


def probe(session: Session, source_id: str) -> Probe:
    adapter = adapter_for(session, source_id)
    if adapter is None:
        raise KeyError(f"No connector for {source_id}")
    conn = connection.connection_for(session, source_id) or connection.default_for(adapter)
    meta = secrets.secret_meta(session, source_id)
    expired = meta.expires_at if meta and meta.expires_at and meta.expires_at <= clock.now() else None
    return probe_connection(session, source_id, adapter, conn, secrets.active_secret(session, source_id), expired)


def _tls(host: str, port: int) -> Check:
    t0 = time.perf_counter()
    try:
        ctx = ssl.create_default_context()
        with socket.create_connection((host, port), timeout=5) as raw, ctx.wrap_socket(raw, server_hostname=host) as s:
            version, cert = s.version(), s.getpeercert() or {}
        ends = cert.get("notAfter")
        until = (
            datetime.fromtimestamp(ssl.cert_time_to_seconds(ends), UTC).date().isoformat()
            if isinstance(ends, str) and ends
            else "unknown"
        )
        return Check(True, _ms(t0), detail=f"{version} · certificate valid until {until}")
    except (OSError, ssl.SSLError, ValueError) as e:
        return Check(False, _ms(t0), f"TLS handshake with {host} failed: {e}")


def _first(res, client: SourceClient):
    records = res.read(client, None)
    try:
        return next(iter(records), None)
    finally:
        close = getattr(records, "close", None)
        if close:
            close()


def probe_connection(session: Session, source_id: str, adapter, conn, secret: str | None, expired=None) -> Probe:
    url = urlparse(conn.base_url)
    host, port = url.hostname or "", url.port or (443 if url.scheme == "https" else 80)
    t0 = time.perf_counter()
    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except (OSError, UnicodeError) as e:
        return Probe(Check(False, _ms(t0), f"Could not resolve {host or conn.base_url}: {e}"), host=host)
    dns = Check(True, _ms(t0), detail=str(infos[0][4][0]))
    t0 = time.perf_counter()
    try:
        socket.create_connection((host, port), timeout=3).close()
    except OSError as e:
        return Probe(dns, Check(False, _ms(t0), f"Connection to {host}:{port} failed: {e}"), host=host)
    tcp = Check(True, _ms(t0))
    tls = _tls(host, port) if url.scheme == "https" else Check(True, detail=f"Not encrypted: {url.scheme}", warn=True)
    if not tls.ok:
        return Probe(dns, tcp, tls, host=host)
    if expired is not None:
        gone = Check(False, error=f"Credential expired on {expired.date().isoformat()}", status=401)
        return Probe(dns, tcp, tls, gone, host=host)
    client = SourceClient(source_id, conn.base_url, adapter.auth(conn, secret), session, None, timeout=10)
    resources = adapter.resources()
    out = Probe(dns, tcp, tls, Check(True), resources=len(resources), host=host)
    try:
        for i, res in enumerate(resources):
            t0 = time.perf_counter()
            try:
                first = _first(res, client)
            except SourceError as e:
                if e.status == 401 or (e.kind == "auth" and e.status != 403):
                    out.auth = Check(False, _ms(t0), str(e), e.status or 401)
                    return out
                if e.kind == "unavailable" and i == 0:
                    out.perms = Check(True)
                    out.read = Check(False, _ms(t0), str(e), e.status)
                    return out
                why = "Access refused for" if e.status == 403 else "Could not read"
                out.perms = Check(False, _ms(t0), f"{why} {res.name} (HTTP {e.status or '?'})", e.status)
                return out
            except Exception as e:  # noqa: BLE001 - a reader that cannot read a record fails the sample read
                out.perms = Check(True)
                out.read = Check(False, _ms(t0), f"{res.name}: {type(e).__name__}: {e}")
                return out
            if i == 0:
                out.read, out.records = Check(True, _ms(t0)), 1 if first is not None else 0
        out.perms = Check(True)
        if not resources:
            out.read = Check(False, error="No read resources are configured")
        return out
    finally:
        client.close()
