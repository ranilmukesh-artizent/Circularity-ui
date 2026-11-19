"""What an adapter provides (docs/BACKEND_STEPS.md, B9).

An adapter knows one system's API: how to authenticate, how to page through each resource, how to ask for changes
since a cursor, and how to turn each record into canonical facts.

    class S4Adapter(Adapter):
        source_id = "erp"
        def auth(self): return Basic(...)
        def resources(self): return [Resource("stock", self.read_stock), ...]
        def read_stock(self, client, since): yield Record("stock", ext_id, payload, request_url)   # pages handled inside
        def map(self, record): return [Fact("asset", ..., ...), ...]

The sync runner (sync.py) does the rest: runs, cursors, raw records, the canonical store, freshness, errors.
`since` is the cursor of the last successful sync of that resource (an ISO timestamp), or None for a full read;
an adapter that cannot read deltas ignores it. The cursor saved after a run is the run's start time, so nothing
changed during the run is missed.
"""

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any

from di.canonical.store import Fact
from di.connectors.http import Auth, SourceClient


@dataclass(frozen=True)
class Record:
    resource: str
    ext_id: str
    payload: dict[str, Any]
    request: str | None = None  # the URL it came from (provenance)
    changed: str | None = None  # when the source last changed it, as ISO 8601 UTC ("2026-10-07T09:00:00+00:00"); the delta cursor


Reader = Callable[[SourceClient, str | None], Iterator[Record]]


@dataclass(frozen=True)
class Resource:
    name: str
    read: Reader
    delta: bool = True  # False: always read in full (small reference lists)


class Adapter:
    source_id: str = ""
    base_path: str = ""  # appended to settings.source_sim_url (the mock) or a real system's URL from config

    def auth(self) -> Auth:
        raise NotImplementedError

    def resources(self) -> list[Resource]:
        raise NotImplementedError

    def map(self, record: Record) -> list[Fact]:
        """Canonical facts from one source record. Set resource/ext_id on facts for provenance (sync fills them in if not)."""
        raise NotImplementedError
