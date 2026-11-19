"""MasterControl Quality Excellence (qms): controlled documents, certificates, test criteria (the demo's SOURCES.qms).
Read only. Written against source-sim's full MasterControl mock (apps/source-sim/sim/vendors/mastercontrol).

OAuth 2.0 client credentials (POST /mc/api/oauth2/token, client in HTTP Basic); lists page with ?limit= / ?cursor=
(body {"data", "paging": {"nextCursor"}}), deltas with ?modifiedSince= against each record's lastModifiedDate.
- certificates: one record per asset holding all of its certificates (dataFields.ASSET_ID). A delta re-reads the whole
  set of an asset with a change. The cursor is the newest lastModifiedDate; MasterControl moves it when a certificate
  expires, so an expiry arrives as a change.
- policies: one record per asset class joining its Effective reuse policy revision (only Effective revisions are
  policy: drafts, pending and superseded revisions are ignored), other Effective controlled documents and the test
  criteria. Small reference lists, read in full (delta=False).

Facts (qms has authority over certificates and policy)
    condition.<ASSET_ID>     certificates (list: ref, type, issued, expires, certified_life_months, result, status,
                             basis), certificate_expiry, certificate_status (active / expired / revoked), cert_ref,
                             certified_life_months, qualification (passed / failed / requalified), requalified_on,
                             policy, policy_ref, policy_version
    condition.class:<cls>    policy, policy_ref, policy_version, policy_title, standard, required_tests, procedures
Policy map (v<revision> of the class policy): ALLOWED_CAT1/2 → reuse_permitted, ALLOWED_CAT3 →
reuse_with_requalification, RESTRICTED_CAT4 → restricted.
The demo's mapping: CERT_EXPIRY 2027-03-01 → condition.certificates[0].expires (ISO date); REUSE_CLASS ALLOWED_CAT2 →
condition.policy reuse_permitted (Policy map v3.2); TEST_RESULT PASS → condition.qualification passed (Result map).
"""

from collections.abc import Iterator

import httpx

from di.canonical.store import Fact
from di.connectors.base import Adapter, Record, Resource
from di.connectors.generic import keep
from di.connectors.http import OAuthClientCredentials, SourceClient

POLICY = {
    "ALLOWED_CAT1": "reuse_permitted",
    "ALLOWED_CAT2": "reuse_permitted",
    "ALLOWED_CAT3": "reuse_with_requalification",
    "RESTRICTED_CAT4": "restricted",
}
RESULT = {"PASS": "passed", "FAIL": "failed", "PENDING": "pending"}
CERT_ORDER = {"LIFE_CERTIFICATION": 0, "REQUALIFICATION": 1, "DATA_ERASURE": 2}
LIMIT = 1000


class MasterControlAdapter(Adapter):
    source_id = "qms"
    base_path = "/mastercontrol/mc/api"

    def auth(self):
        return OAuthClientCredentials("/oauth2/token", "circularity-di", "circularity-demo-mastercontrol-secret")

    def resources(self):
        return [Resource("policies", self.read_policies, delta=False), Resource("certificates", self.read_certificates)]

    # ------------------------------------------------------------- reading
    def pages(self, client: SourceClient, path: str, **params) -> Iterator[tuple[dict, str]]:
        cursor = None
        while True:
            q = {**params, "limit": str(LIMIT)} | ({"cursor": cursor} if cursor else {})
            body = client.get_json(path, params=q)
            rows = body["data"]
            client.note_records(len(rows))
            url = str(httpx.URL(client.url(path), params=q))
            for row in rows:
                yield row, url
            cursor = (body.get("paging") or {}).get("nextCursor")
            if not cursor or not rows:
                return

    def read_all(self, client: SourceClient, path: str, **params) -> list[dict]:
        return [row for row, _ in self.pages(client, path, **params)]

    def _effective_policies(self, client: SourceClient) -> dict[str, dict]:
        """The Effective revision of each controlled document, by document number (certificates name theirs)."""
        if getattr(client, "_qms_effective", None) is None:
            docs = self.read_all(client, "/v2/controlled-documents", status="Effective")
            client._qms_effective = {d["documentNumber"]: d for d in docs}
        return client._qms_effective

    def read_policies(self, client: SourceClient, since: str | None) -> Iterator[Record]:
        docs = list(self._effective_policies(client).values())
        tests = self.read_all(client, "/v2/test-criteria")
        url = str(httpx.URL(client.url("/v2/controlled-documents"), params={"status": "Effective"}))
        classes = sorted({d["dataFields"].get("ASSET_CLASS") for d in docs if d["dataFields"].get("ASSET_CLASS")})
        for cls in classes:
            mine = [d for d in docs if d["dataFields"].get("ASSET_CLASS") == cls]
            policy = next((d for d in mine if d["infoCardType"] == "Policy" and d["dataFields"].get("REUSE_CLASS")), None)
            payload = {
                "assetClass": cls,
                "policy": policy,
                "documents": [d for d in mine if d is not policy],
                "tests": [x for x in tests if x.get("assetClass") == cls],
            }
            changed = max([d["lastModifiedDate"] for d in mine] + [x["lastModifiedDate"] for x in payload["tests"]])
            yield Record("policies", cls, payload, url, changed)

    def read_certificates(self, client: SourceClient, since: str | None) -> Iterator[Record]:
        groups: dict[str, list[dict]] = {}
        urls: dict[str, str] = {}
        for row, url in self.pages(client, "/v2/certificates", **({"modifiedSince": since} if since else {})):
            asset = row["dataFields"].get("ASSET_ID")
            if asset:
                groups.setdefault(asset, []).append(row)
                urls.setdefault(asset, url)
        policies = self._effective_policies(client) if groups else {}
        for asset in sorted(groups):
            rows, url = groups[asset], urls[asset]
            if since:  # the whole set of the asset, not only what changed
                rows = self.read_all(client, "/v2/certificates", assetId=asset)
                url = str(httpx.URL(client.url("/v2/certificates"), params={"assetId": asset}))
            changed = max(r["lastModifiedDate"] for r in rows)
            yield Record("certificates", asset, {"assetId": asset, "items": rows, "policies": policies}, url, changed)

    # ------------------------------------------------------------- mapping
    def map(self, record: Record) -> list[Fact]:
        if record.resource == "policies":
            return keep(self._class_policy(record.payload))
        return keep(self._certificates(record.payload))

    def _class_policy(self, p: dict) -> list[Fact]:
        key = f"class:{p['assetClass']}"
        pol = p.get("policy")
        tests = [
            {
                "ref": x["testId"],
                "name": x["testName"],
                "method": x.get("method"),
                "acceptance": x.get("acceptanceCriteria"),
                "routes": x.get("mandatoryForRoutes") or [],
            }
            for x in p["tests"]
        ]
        facts = [
            Fact("condition", key, "required_tests", tests, "testId", [x["testId"] for x in p["tests"]], "Test criteria"),
            Fact(
                "condition",
                key,
                "procedures",
                [
                    {"ref": d["documentNumber"], "title": d["title"], "standard": d["dataFields"].get("STANDARD_REF")}
                    for d in p["documents"]
                ],
                "documentNumber",
                [d["documentNumber"] for d in p["documents"]],
                "Pass-through",
            ),
        ]
        if pol:
            rc, rev, f = pol["dataFields"]["REUSE_CLASS"], pol["revision"], pol["dataFields"]
            facts += [
                Fact("condition", key, "policy", POLICY.get(rc, rc.lower()), "REUSE_CLASS", rc, f"Policy map v{rev}"),
                Fact(
                    "condition", key, "policy_ref", pol["documentNumber"], "documentNumber", pol["documentNumber"], "Pass-through"
                ),
                Fact("condition", key, "policy_version", rev, "revision", rev, "Pass-through (Effective revision)"),
                Fact("condition", key, "policy_title", pol.get("title"), "title", pol.get("title"), "Pass-through"),
                Fact("condition", key, "standard", f.get("STANDARD_REF"), "STANDARD_REF", f.get("STANDARD_REF"), "Pass-through"),
            ]
        return facts

    def _certificates(self, p: dict) -> list[Fact]:
        key = p["assetId"]
        certs = sorted(
            p["items"],
            key=lambda c: (c["status"] != "Active", CERT_ORDER.get(c["certificateType"], 9), c["recordId"]),
        )
        if not certs:
            return []
        listed = []
        for c in certs:
            f = c["dataFields"]
            res = f.get("TEST_RESULT") or ""
            listed.append(
                {
                    "ref": c["certificateNumber"],
                    "type": c["certificateType"].lower(),
                    "issued": c.get("issuedDate"),
                    "expires": f.get("CERT_EXPIRY"),
                    "certified_life_months": f.get("CERTIFIED_LIFE_MONTHS"),
                    "result": RESULT.get(res, res.lower() or None),
                    "status": (c.get("status") or "").lower() or None,
                    "basis": f.get("BASIS"),
                }
            )
        main = certs[0]  # the active life certificate (or requalification) when there is one
        mf = main["dataFields"]
        expiry = mf.get("CERT_EXPIRY")
        facts = [
            Fact(
                "condition",
                key,
                "certificates",
                listed,
                "CERT_EXPIRY",
                [c["dataFields"].get("CERT_EXPIRY") for c in certs],
                "ISO date",
            ),
            Fact("condition", key, "certificate_expiry", expiry, "CERT_EXPIRY", expiry, "ISO date"),
            Fact("condition", key, "certificate_status", main["status"].lower(), "status", main["status"], "Status map"),
            Fact(
                "condition",
                key,
                "cert_ref",
                main["certificateNumber"],
                "certificateNumber",
                main["certificateNumber"],
                "Pass-through",
            ),
            Fact(
                "condition",
                key,
                "certified_life_months",
                mf.get("CERTIFIED_LIFE_MONTHS"),
                "CERTIFIED_LIFE_MONTHS",
                mf.get("CERTIFIED_LIFE_MONTHS"),
                "Integer",
            ),
        ]
        result = mf.get("TEST_RESULT")
        if main["certificateType"] == "REQUALIFICATION" and result == "PASS":
            facts += [
                Fact("condition", key, "qualification", "requalified", "TEST_RESULT", result, "Result map (requalification)"),
                Fact(
                    "condition", key, "requalified_on", main.get("issuedDate"), "issuedDate", main.get("issuedDate"), "ISO date"
                ),
            ]
        elif result:
            facts.append(
                Fact("condition", key, "qualification", RESULT.get(result, result.lower()), "TEST_RESULT", result, "Result map")
            )
        rc = mf.get("REUSE_CLASS")
        if rc:
            doc = (p.get("policies") or {}).get(mf.get("DOCUMENT_NUMBER")) or {}
            rev = doc.get("revision")
            facts += [
                Fact(
                    "condition",
                    key,
                    "policy",
                    POLICY.get(rc, rc.lower()),
                    "REUSE_CLASS",
                    rc,
                    f"Policy map v{rev}" if rev else "Policy map",
                ),
                Fact(
                    "condition",
                    key,
                    "policy_ref",
                    mf.get("DOCUMENT_NUMBER"),
                    "DOCUMENT_NUMBER",
                    mf.get("DOCUMENT_NUMBER"),
                    "Pass-through",
                ),
                Fact("condition", key, "policy_version", rev, "revision", rev, "Pass-through (Effective revision)"),
            ]
        return facts


ADAPTER = MasterControlAdapter()
