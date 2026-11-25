"""Title and lien service (uc_title, plan 9 P9-9.3): the evidence UC-06 and UC-24 gate on. Read only.

Written against source-sim's synthetic title and lien mock (source-sim/sim/vendors/title_lien): no real title service is
connected. API key in `x-api-key`; offset paging (`items`, `next`, `total`); `?updatedSince=` delta reads (a lien
release changes the title, so the next delta sync carries it). Title, lien and brand rules are state law and differ:
the adapter carries generic evidence only, and any rule built on it needs review by Kinective's Legal team.

Not one of the demo's 21 sources: it starts unregistered (no source_system row), so every demo screen and count is
unchanged. di.connectors.extra registers it and source.reconnect connects it (as uc_lease). It implements no registry
entry of its own: it fills the canonical model `condition` for a car, keyed by the source's org unit (schema.vin_key),
which the used-car pack's evidence mappings (title_status, lien_release, title_brand) read. Nothing is written to the
source: the mock's lien release request is for a later task's action.

Resource and facts (snake case of the source's camelCase fields)
    titles   condition.<vin key>   title_status (titleStatus), lien_open (any lien not released), lien_release_ref (the
                                   releaseRef of the latest released lien), title_brand (brand), title_checked_at
                                   (checkedAt)
`brandSource`, the liens' amounts and `holderRef` (a code) stay in the raw record: no fact. A field the source leaves
empty (no brand, no release yet) writes no fact.
"""

from collections.abc import Iterator

from sqlalchemy import text

from di.connectors.base import Record, Resource
from di.connectors.generic import GenericAdapter, keep
from di.connectors.http import SourceClient
from di.services.canonical.schema import vin_key
from di.services.canonical.store import Fact


def _org(client: SourceClient) -> str | None:
    """The org unit the source is bound to (None: shared)."""
    return client.session.execute(text("SELECT org_unit_id FROM source_system WHERE id = :i"), {"i": client.source_id}).scalar()


class TitleLienAdapter(GenericAdapter):
    source_id = "uc_title"
    base_path = "/title-lien/api/v2"
    auth_kind = "api_key"
    api_key_header = "x-api-key"
    since_param = "updatedSince"
    provisioned = False  # no demo source: registered and connected by a person (di.connectors.extra)
    extra = True
    vendor = "Title and lien service (synthetic)"
    source_type = "title"
    interval = 60
    owner = "Integration Engineering"

    def resources(self):
        def titles(client: SourceClient, since: str | None) -> Iterator[Record]:
            org = _org(client)
            for r in self.flat(client, "titles", "/titles", "vin", since):
                yield Record(r.resource, r.ext_id, r.payload | {"org_unit_id": org}, r.request, r.changed)

        return [Resource("titles", titles)]

    def map(self, record: Record) -> list[Fact]:
        p = record.payload
        key = vin_key(p.get("org_unit_id"), p["vin"])
        liens = p.get("liens") or []
        released = [x for x in liens if x.get("released") and x.get("releaseRef")]
        released.sort(key=lambda x: x.get("releasedAt") or "")
        ref = released[-1]["releaseRef"] if released else None
        status, brand, checked = p.get("titleStatus"), p.get("brand"), p.get("checkedAt")
        open_note, ref_note = "True when any lien is not released", "The release reference of the latest released lien"
        facts = [
            Fact("condition", key, "title_status", status, "titleStatus", status, "Pass-through"),
            Fact("condition", key, "lien_open", any(not x.get("released") for x in liens), "liens", liens, open_note),
            Fact("condition", key, "lien_release_ref", ref, "liens", liens, ref_note),
            Fact("condition", key, "title_brand", brand, "brand", brand, "Pass-through"),
            Fact("condition", key, "title_checked_at", checked, "checkedAt", checked, "Pass-through"),
        ]
        return keep(facts)


ADAPTER = TitleLienAdapter()
