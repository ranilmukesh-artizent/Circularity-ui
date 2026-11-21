"""What an adapter provides (docs/backend-steps.md, B9).

An adapter knows one system's API: how to authenticate, how to page through each resource, how to ask for changes
since a cursor, and how to turn each record into canonical facts.

    class S4Adapter(Adapter):
        source_id = "erp"
        def auth(self, conn=None, secret=None): return Basic("DI_CONNECTOR", secret or DEMO)
        def resources(self): return [Resource("stock", self.read_stock), ...]
        def read_stock(self, client, since): yield Record("stock", ext_id, payload, request_url)   # pages handled inside
        def map(self, record): return [Fact("asset", ..., ...), ...]

The sync runner (sync.py) does the rest: runs, cursors, raw records, the canonical store, freshness, errors.
`since` is the cursor of the last successful sync of that resource (an ISO timestamp), or None for a full read;
an adapter that cannot read deltas ignores it. The cursor saved after a run is the newest `Record.changed` the run
saw, in the source's own clock (simulated time for the mocks); a resource with failed records keeps its old cursor.
When a source gives no change time per record, the adapter can use the source's clock at the start of the read.
"""

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from di.canonical.store import Fact
from di.connectors.http import Auth, SourceClient

if TYPE_CHECKING:
    from di.connectors.connection import Connection


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
    base_path: str = ""  # with settings.source_sim_url, the seeded URL of its connection (di.connectors.connection)
    protocol: str = "rest"
    # the source's confidence once connected, for a source the demo lists with confidence 0 (no data yet); None: keep it
    connected_confidence: float | None = None

    def auth(self, conn: "Connection | None" = None, secret: str | None = None) -> Auth:
        """How to sign in. `conn` is the source's connection (its URL, for token endpoints outside the base path);
        `secret` the stored credential (di.connectors.secrets), or None: then the adapter's built-in demo credential,
        the synthetic one source-sim accepts. Called with no arguments, it is the demo setup."""
        raise NotImplementedError

    @staticmethod
    def origin(conn: "Connection | None") -> str:
        """scheme://host[:port] of the connection, or of source-sim without one."""
        from di.connectors.connection import sim_url

        return conn.origin if conn is not None else sim_url()

    def resources(self) -> list[Resource]:
        raise NotImplementedError

    def map(self, record: Record) -> list[Fact]:
        """Canonical facts from one source record. Set resource/ext_id on facts for provenance (sync fills them in if not)."""
        raise NotImplementedError
