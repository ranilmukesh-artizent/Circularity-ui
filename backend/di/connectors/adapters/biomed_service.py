"""Biomedical service system (mr_biomed, plan 9 P9-11.4): service records, field safety notices and assessments. Read only.

Written against source-sim's synthetic biomedical service mock (source-sim/sim/vendors/biomed_service): no real biomedical
system is connected. API key in `x-api-key`; plain JSON arrays (no paging, no change stamps, so every resource is read in
full: Resource.delta False). The mock's service order (`POST /service-orders`) is for the actions of later tasks; nothing is
written here.

Not one of the demo's 21 sources: it starts unregistered (no source_system row), so every demo screen and count is
unchanged. di.connectors.extra registers it and source.reconnect connects it. It implements no registry entry of its own:
it fills the canonical models `condition` and `intervention` for a device, keyed by the source's org unit (schema.tag_key),
which the medical rental pack's gates and valuer read.

Resources and facts (snake case of the source's camelCase fields)
    service      condition.<tag key>     pm_due (pmDue), pm_code (pmCode), certification_expiry (certificationExpiry),
                                         functional_test {result, at}, electrical_safety {standard, result, at}, notes
                                         [{text, kind}], correction_open (bool), correction_ref
                 intervention.<tag key>  repair_estimate (repairEstimate)
    assessments  condition.<tag key>     servicing_assessment: the result (servicing, remanufacturing, full_refurbishment)
`correction_open` and `correction_ref` come from the field safety notices: a notice covers a device when the notice's model
is the device's model and the device's serial number lies in [serialFrom, serialTo]. An open notice wins over a closed one;
`correction_open` is false (no ref) for a device no notice covers. `lastPm`, `faults` and `serialNo` stay in the raw record:
no fact.
"""

from collections.abc import Iterator
from typing import Any

from sqlalchemy import text

from di.connectors.base import Record, Resource
from di.connectors.generic import GenericAdapter, keep
from di.connectors.http import SourceClient
from di.services.canonical.schema import tag_key
from di.services.canonical.store import Fact

CONDITION = {  # source field -> condition field
    "pmDue": "pm_due", "pmCode": "pm_code", "certificationExpiry": "certification_expiry",
    "functionalTest": "functional_test", "electricalSafety": "electrical_safety", "notes": "notes",
}  # fmt: skip


def _org(client: SourceClient) -> str | None:
    """The org unit the source is bound to (None: shared)."""
    return client.session.execute(text("SELECT org_unit_id FROM source_system WHERE id = :i"), {"i": client.source_id}).scalar()


def covering_notice(notices: list[dict], model: Any, serial: Any) -> dict | None:
    """The notice that covers a device (same model, serial in the notice's range); an open one before a closed one."""
    if not isinstance(serial, int) or isinstance(serial, bool):
        return None
    hits = [n for n in notices if n.get("model") == model and n["serialFrom"] <= serial <= n["serialTo"]]
    return next((n for n in hits if n.get("status") == "open"), hits[0] if hits else None)


class BiomedServiceAdapter(GenericAdapter):
    source_id = "mr_biomed"
    base_path = "/biomed-service/api"
    auth_kind = "api_key"
    api_key_header = "x-api-key"
    provisioned = False  # no demo source: registered and connected by a person (di.connectors.extra)
    extra = True
    vendor = "Biomedical service system (synthetic)"
    source_type = "service"
    interval = 60
    owner = "Integration Engineering"

    def resources(self):
        return [Resource("service", self.read_service, delta=False), Resource("assessments", self.read_assessments, delta=False)]

    @staticmethod
    def _list(client: SourceClient, path: str) -> list[dict]:
        rows = client.get_json(path)
        client.note_records(len(rows))
        return rows

    def read_service(self, client: SourceClient, _since: str | None) -> Iterator[Record]:
        org = _org(client)
        notices = self._list(client, "/corrections")
        url = client.url("/assets")
        for d in self._list(client, "/assets"):
            notice = covering_notice(notices, d.get("model"), d.get("serialNo"))
            yield Record("service", str(d["tag"]), d | {"notice": notice, "org_unit_id": org}, url)

    def read_assessments(self, client: SourceClient, _since: str | None) -> Iterator[Record]:
        org = _org(client)
        url = client.url("/assessments")
        for a in self._list(client, "/assessments"):
            yield Record("assessments", str(a["tag"]), a | {"org_unit_id": org}, url)

    def map(self, record: Record) -> list[Fact]:
        p = record.payload
        key = tag_key(p.get("org_unit_id"), p["tag"])
        if record.resource == "assessments":
            return keep(
                [
                    Fact(
                        "condition",
                        key,
                        "servicing_assessment",
                        p.get("result"),
                        "result",
                        p.get("result"),
                        "Result of the assessment",
                    )
                ]
            )
        notice = p.get("notice")
        open_ = bool(notice and notice.get("status") == "open")
        ref = notice.get("correctionRef") if notice else None
        facts = [
            Fact("condition", key, to, p.get(src), src, p.get(src), "Camel case to snake case") for src, to in CONDITION.items()
        ]
        facts.append(
            Fact("condition", key, "correction_open", open_, "notice", notice and notice.get("noticeId"),
                 "True when an open field safety notice covers the device's model and serial")
        )  # fmt: skip
        facts.append(
            Fact(
                "condition",
                key,
                "correction_ref",
                ref,
                "notice",
                notice and notice.get("noticeId"),
                "The covering notice's correction",
            )
        )
        est = p.get("repairEstimate")
        facts.append(Fact("intervention", key, "repair_estimate", est, "repairEstimate", est, "Camel case to snake case"))
        return keep(facts)


ADAPTER = BiomedServiceAdapter()
