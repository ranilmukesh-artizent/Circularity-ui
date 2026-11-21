"""Probe a source's connector against the system it reads (the Connection Fabric's Test connection, B17).

    probe(session, "erp") -> Probe(dns, tcp, auth, read)     each a Check(ok, ms, error)

What is really checked, against source-sim (the mock of every system):
    dns    the system's host name resolves (the host of settings.source_sim_url)
    tcp    a connection to it opens
    auth   the adapter signs in and its first resource answers (401 is an expired or refused credential, 403 missing
           permission)
    read   the first record of the adapter's first resource arrives, timed
Each call is written to the fetch log like a sync's (without a run). No record is stored.
"""

import socket
import time
from dataclasses import dataclass
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from di.config import get_settings
from di.connectors.http import SourceClient, SourceError
from di.connectors.registry import ADAPTERS


@dataclass
class Check:
    ok: bool
    ms: int = 0
    error: str = ""
    status: int | None = None


@dataclass
class Probe:
    dns: Check
    tcp: Check
    auth: Check
    read: Check
    records: int = 0


def _ms(t0: float) -> int:
    return max(1, round((time.perf_counter() - t0) * 1000))


def probe(session: Session, source_id: str) -> Probe:
    adapter = ADAPTERS[source_id]
    url = urlparse(get_settings().source_sim_url)
    host, port = url.hostname or "localhost", url.port or (443 if url.scheme == "https" else 80)
    skipped = Check(False, error="not reached")
    t0 = time.perf_counter()
    try:
        socket.getaddrinfo(host, port)
    except OSError as e:
        return Probe(Check(False, _ms(t0), f"Could not resolve {host}: {e}"), skipped, skipped, skipped)
    dns = Check(True, _ms(t0))
    t0 = time.perf_counter()
    try:
        socket.create_connection((host, port), timeout=3).close()
    except OSError as e:
        return Probe(dns, Check(False, _ms(t0), f"Connection to {host}:{port} failed: {e}"), skipped, skipped)
    tcp = Check(True, _ms(t0))
    client = SourceClient(source_id, get_settings().source_sim_url + adapter.base_path, adapter.auth(), session, None, timeout=10)
    t0 = time.perf_counter()
    try:
        res = adapter.resources()[0]
        records = res.read(client, None)
        try:
            first = next(iter(records), None)
        finally:
            close = getattr(records, "close", None)
            if close:
                close()
        took = _ms(t0)
        return Probe(dns, tcp, Check(True), Check(True, took), 1 if first is not None else 0)
    except SourceError as e:
        if e.kind == "auth":
            return Probe(dns, tcp, Check(False, _ms(t0), str(e), e.status), skipped)
        return Probe(dns, tcp, Check(True), Check(False, _ms(t0), str(e), e.status))
    except Exception as e:  # noqa: BLE001 - an adapter that cannot read its first record fails the sample read
        return Probe(dns, tcp, Check(True), Check(False, _ms(t0), f"{type(e).__name__}: {e}"))
    finally:
        client.close()
