"""MasterControl (qms): controlled documents, certificates, test criteria (the demo's SOURCES.qms). Read only.

OAuth client credentials, pageNumber/pageSize paging, `?updated_since=` deltas (see oracle_lease.GenericAdapter).
- certificates: one record per asset holding all of its certificates (a delta re-reads the whole set of an asset
  with a change). Delta.
- policies: one record per asset class joining its reuse policy, other controlled documents and test criteria. Small
  reference lists, read in full (delta=False).

Facts (qms has authority over certificates and policy)
    condition.<ASSET_ID>     certificates (list: ref, type, issued, expires, certified_life_months, result, status,
                             basis), certificate_expiry, cert_ref, certified_life_months, qualification (passed /
                             failed / requalified), requalified_on, policy, policy_ref, policy_version
    condition.class:<cls>    policy, policy_ref, policy_version, policy_title, standard, required_tests, procedures
Policy map (v<revision> of the class policy): ALLOWED_CAT1/2 → reuse_permitted, ALLOWED_CAT3 →
reuse_with_requalification, RESTRICTED_CAT4 → restricted.
The demo's mapping: CERT_EXPIRY 2027-03-01 → condition.certificates[0].expires (ISO date); REUSE_CLASS ALLOWED_CAT2 →
condition.policy reuse_permitted (Policy map v3.2); TEST_RESULT PASS → condition.qualification passed (Result map).
"""

from di.canonical.store import Fact
from di.connectors.base import Record, Resource
from di.connectors.generic import GenericAdapter, keep

POLICY = {
    "ALLOWED_CAT1": "reuse_permitted",
    "ALLOWED_CAT2": "reuse_permitted",
    "ALLOWED_CAT3": "reuse_with_requalification",
    "RESTRICTED_CAT4": "restricted",
}
RESULT = {"PASS": "passed", "FAIL": "failed", "PENDING": "pending"}
CERT_ORDER = {"LIFE_CERTIFICATION": 0, "REQUALIFICATION": 1, "DATA_ERASURE": 2}


class MasterControlAdapter(GenericAdapter):
    source_id = "qms"
    base_path = "/mastercontrol/mc/api"
    items_key, next_key, next_param, size_param, page_size = "results", "nextPage", "pageNumber", "pageSize", 200

    def resources(self):
        return [
            Resource("policies", self.read_policies, delta=False),
            Resource(
                "certificates",
                lambda c, s: self.grouped(c, "certificates", "/v2/certificates", "ASSET_ID", s, extra=self._policies),
            ),
        ]

    def _policies(self, client) -> dict:
        """The policy document of each class, by document number (the certificates name theirs)."""
        if getattr(client, "_qms_policies", None) is None:
            docs = self.read_all(client, "/v2/controlled-documents", DOCUMENT_TYPE="POLICY")
            client._qms_policies = {d["DOCUMENT_NUMBER"]: d for d in docs}
        return {"policies": client._qms_policies}

    def read_policies(self, client, since):
        docs = self.read_all(client, "/v2/controlled-documents")
        tests = self.read_all(client, "/v2/test-criteria")
        url = client.url("/v2/controlled-documents")
        for cls in sorted({d["ASSET_CLASS"] for d in docs if d.get("ASSET_CLASS")}):
            mine = [d for d in docs if d.get("ASSET_CLASS") == cls]
            policy = next((d for d in mine if d.get("REUSE_CLASS")), None)
            payload = {
                "ASSET_CLASS": cls,
                "policy": policy,
                "documents": [d for d in mine if d is not policy],
                "tests": [t for t in tests if t.get("ASSET_CLASS") == cls],
            }
            yield Record("policies", cls, payload, url)

    def map(self, record: Record) -> list[Fact]:
        if record.resource == "policies":
            return keep(self._class_policy(record.payload))
        return keep(self._certificates(record.payload))

    def _class_policy(self, p: dict) -> list[Fact]:
        key = f"class:{p['ASSET_CLASS']}"
        pol = p.get("policy") or {}
        tests = [
            {
                "ref": t["TEST_ID"],
                "name": t["TEST_NAME"],
                "method": t.get("METHOD"),
                "acceptance": t.get("ACCEPTANCE_CRITERIA"),
                "routes": t.get("MANDATORY_FOR_ROUTES") or [],
            }
            for t in p["tests"]
        ]
        facts = [
            Fact("condition", key, "required_tests", tests, "TEST_ID", [t["TEST_ID"] for t in p["tests"]], "Test criteria"),
            Fact(
                "condition",
                key,
                "procedures",
                [{"ref": d["DOCUMENT_NUMBER"], "title": d["TITLE"], "standard": d.get("STANDARD_REF")} for d in p["documents"]],
                "DOCUMENT_NUMBER",
                [d["DOCUMENT_NUMBER"] for d in p["documents"]],
                "Pass-through",
            ),
        ]
        if pol:
            rc = pol["REUSE_CLASS"]
            facts += [
                Fact("condition", key, "policy", POLICY.get(rc, rc.lower()), "REUSE_CLASS", rc, f"Policy map v{pol['REVISION']}"),
                Fact(
                    "condition",
                    key,
                    "policy_ref",
                    pol["DOCUMENT_NUMBER"],
                    "DOCUMENT_NUMBER",
                    pol["DOCUMENT_NUMBER"],
                    "Pass-through",
                ),
                Fact("condition", key, "policy_version", pol["REVISION"], "REVISION", pol["REVISION"], "Pass-through"),
                Fact("condition", key, "policy_title", pol.get("TITLE"), "TITLE", pol.get("TITLE"), "Pass-through"),
                Fact(
                    "condition", key, "standard", pol.get("STANDARD_REF"), "STANDARD_REF", pol.get("STANDARD_REF"), "Pass-through"
                ),
            ]
        return facts

    def _certificates(self, p: dict) -> list[Fact]:
        key = p["ASSET_ID"]
        certs = sorted(p["items"], key=lambda c: (CERT_ORDER.get(c.get("CERT_TYPE"), 9), c.get("RECORD_ID")))
        if not certs:
            return []
        listed = [
            {
                "ref": c["CERT_NUMBER"],
                "type": (c.get("CERT_TYPE") or "").lower(),
                "issued": c.get("ISSUE_DATE"),
                "expires": c.get("CERT_EXPIRY"),
                "certified_life_months": c.get("CERTIFIED_LIFE_MONTHS"),
                "result": RESULT.get(c.get("TEST_RESULT") or "", (c.get("TEST_RESULT") or "").lower() or None),
                "status": (c.get("STATUS") or "").lower() or None,
                "basis": c.get("BASIS"),
            }
            for c in certs
        ]
        main = certs[0]  # the life certificate (or requalification) when there is one
        facts = [
            Fact("condition", key, "certificates", listed, "CERT_EXPIRY", [c.get("CERT_EXPIRY") for c in certs], "ISO date"),
            Fact(
                "condition",
                key,
                "certificate_expiry",
                main.get("CERT_EXPIRY"),
                "CERT_EXPIRY",
                main.get("CERT_EXPIRY"),
                "ISO date",
            ),
            Fact("condition", key, "cert_ref", main["CERT_NUMBER"], "CERT_NUMBER", main["CERT_NUMBER"], "Pass-through"),
            Fact(
                "condition",
                key,
                "certified_life_months",
                main.get("CERTIFIED_LIFE_MONTHS"),
                "CERTIFIED_LIFE_MONTHS",
                main.get("CERTIFIED_LIFE_MONTHS"),
                "Integer",
            ),
        ]
        result = main.get("TEST_RESULT")
        if main.get("CERT_TYPE") == "REQUALIFICATION" and result == "PASS":
            facts += [
                Fact("condition", key, "qualification", "requalified", "TEST_RESULT", result, "Result map (requalification)"),
                Fact(
                    "condition", key, "requalified_on", main.get("ISSUE_DATE"), "ISSUE_DATE", main.get("ISSUE_DATE"), "ISO date"
                ),
            ]
        elif result:
            facts.append(
                Fact("condition", key, "qualification", RESULT.get(result, result.lower()), "TEST_RESULT", result, "Result map")
            )
        rc = main.get("REUSE_CLASS")
        if rc:
            pol = (p.get("policies") or {}).get(main.get("DOCUMENT_NUMBER")) or {}
            rev = pol.get("REVISION")
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
                    main.get("DOCUMENT_NUMBER"),
                    "DOCUMENT_NUMBER",
                    main.get("DOCUMENT_NUMBER"),
                    "Pass-through",
                ),
                Fact("condition", key, "policy_version", rev, "REVISION", rev, "Pass-through"),
            ]
        return facts


ADAPTER = MasterControlAdapter()
