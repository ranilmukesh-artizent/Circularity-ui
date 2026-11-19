"""MasterControl (the demo's SOURCES.qms): reuse policies, certifications, test criteria.
Read: GET /v2/controlled-documents, /v2/certificates, /v2/test-criteria. No writes.

Field names follow the demo's MAPPINGS.qms (CERT_EXPIRY, REUSE_CLASS, TEST_RESULT). A life certificate exists for every
case the demo can certify (its caseRul): the certified period and the QMS reference are computed exactly as the demo
does, so RT-1048 (MTR-2041) is certified for 24 months under QMS-2906. CERT_EXPIRY is the first day of the month
before the next inspection (RT-1048: Apr 2027 -> 2027-03-01, the MAPPINGS example).
"""

from datetime import date, timedelta

from sim.generic.spec import Auth, Paging, Resource, Spec
from sim.generic.specs.assetwise import STANDARDS, case_rul, month_date
from sim.seed import Seed

# class -> (reuse class, policy title, revision)
REUSE = {
    "motor": ("ALLOWED_CAT2", "Reuse and redeployment of industrial motors", "3.2"),
    "pump": ("ALLOWED_CAT2", "Reuse and redeployment of hydraulic pumps", "3.2"),
    "control": ("ALLOWED_CAT3", "Reuse of control units and PLCs (requalification required)", "2.4"),
    "drill": ("ALLOWED_CAT1", "Reuse and resale of power tools", "1.9"),
    "batch": ("RESTRICTED_CAT4", "Reuse of tool-fleet batches with Li-ion cells", "2.0"),
    "it": ("ALLOWED_CAT2", "Reuse and resale of IT electronics (data erasure required)", "4.1"),
}
OTHER_DOCS = [
    ("SOP-DATA-ERASE", "Data sanitization before release of IT assets", "4.0", "it", "NIST SP 800-88"),
    ("SOP-LIION-REQUAL", "Requalification of used Li-ion cells and packs", "1.3", "batch", "IEC 62133-2"),
    ("POL-RECYCLER-CERT", "Certification requirements for recycler and exit partners", "2.1", None, "ISO 14001 / R2v3"),
    ("POL-LIFE-CERT", "Certification of remaining operating life", "3.0", None, None),
]
# class -> [(test name, method, acceptance criteria)] (the demo's workshop operations, EX_OPS)
TESTS = {
    "motor": [
        ("Surge and insulation test", "Surge comparison + insulation resistance at 500 V DC", ">= 100 MOhm; no surge mismatch"),
        ("Load test bench", "3 h at rated load", "Temperature rise within class F; current within 5 % of nameplate"),
        ("Balancing", "Dynamic balancing of the rotor", "Balance grade G2.5"),
        ("Vibration check", "Velocity RMS at bearings", "<= 2.8 mm/s"),
    ],
    "pump": [
        ("Test rig", "Flow and pressure at rated speed", "Volumetric efficiency >= 85 %"),
        ("Flushing rig", "Fluid cleanliness after flush", "ISO 4406 18/16/13 or better"),
    ],
    "control": [
        ("Burn-in rack", "8 h powered burn-in", "No resets; self-test errors <= 2"),
        ("Functional test station", "I/O and communication test", "All channels pass"),
    ],
    "drill": [
        ("Battery cycler", "Capacity test over 2 cycles", ">= 70 % of rated capacity"),
        ("Function test", "No-load and load run", "No abnormal noise, sparking or overheating"),
    ],
    "batch": [
        ("Battery cycler", "Capacity test per pack", ">= 60 % state of health"),
        ("Function test", "Sample function test per lot", "All sampled tools pass"),
    ],
    "it": [
        ("Imaging station", "Reimage and data erasure verification", "Erasure certificate issued"),
        ("Battery test", "Full charge and discharge", ">= 60 % state of health"),
    ],
}
REQUALIFIED = {"CTL-0122": date(2026, 9, 12)}  # the demo's conflict CF-32: QMS says requalified 12 Sep


def _add_months(d: date, months: int) -> date:
    y, m = divmod(d.month - 1 + months, 12)
    return date(d.year + y, m + 1, 1)


def seed(s: Seed) -> dict[str, list[dict]]:
    as_of = s.world.as_of.date()
    docs = [
        {
            "DOCUMENT_NUMBER": f"POL-REUSE-{s.world.classes[cls].pre}",
            "TITLE": title,
            "DOCUMENT_TYPE": "POLICY",
            "ASSET_CLASS": cls,
            "REVISION": rev,
            "STATUS": "EFFECTIVE",
            "EFFECTIVE_DATE": "2026-04-01",
            "REUSE_CLASS": reuse,
            "STANDARD_REF": STANDARDS[cls][1],
            "OWNER": "Quality Assurance",
        }
        for cls, (reuse, title, rev) in REUSE.items()
    ] + [
        {
            "DOCUMENT_NUMBER": num,
            "TITLE": title,
            "DOCUMENT_TYPE": "SOP" if num.startswith("SOP") else "POLICY",
            "ASSET_CLASS": cls,
            "REVISION": rev,
            "STATUS": "EFFECTIVE",
            "EFFECTIVE_DATE": "2026-01-15",
            "REUSE_CLASS": None,
            "STANDARD_REF": ref,
            "OWNER": "Quality Assurance",
        }
        for num, title, rev, cls, ref in OTHER_DOCS
    ]
    criteria = []
    for cls, tests in TESTS.items():
        pre = s.world.classes[cls].pre
        for i, (name, method, accept) in enumerate(tests, 1):
            criteria.append(
                {
                    "TEST_ID": f"TC-{pre}-{i:02d}",
                    "TEST_NAME": name,
                    "ASSET_CLASS": cls,
                    "METHOD": method,
                    "ACCEPTANCE_CRITERIA": accept,
                    "STANDARD_REF": STANDARDS[cls][1],
                    "MANDATORY_FOR_ROUTES": ["redeploy", "relase", "resale"] if i == 1 else ["redeploy", "relase"],
                    "DOCUMENT_NUMBER": f"POL-REUSE-{pre}",
                }
            )
    certs = []
    for case in s.cases.values():
        f = case.facts
        issued = min(f.received.date() + timedelta(days=1), as_of)
        rul = case_rul(f)
        if rul:
            nxt = month_date(f.next_inspection)
            expiry = _add_months(nxt, -1) if nxt else _add_months(issued, rul["cert_months"])
            certs.append(
                {
                    "RECORD_ID": f"CERT-{f.asset_id}",
                    "CERT_NUMBER": rul["cert_ref"],
                    "CERT_TYPE": "LIFE_CERTIFICATION",
                    "ASSET_ID": f.asset_id,
                    "ASSET_CLASS": f.cls,
                    "CERTIFIED_LIFE_MONTHS": rul["cert_months"],
                    "ISSUE_DATE": issued.isoformat(),
                    "CERT_EXPIRY": expiry.isoformat(),
                    "TEST_RESULT": "PASS",
                    "REUSE_CLASS": REUSE[f.cls][0],
                    "DOCUMENT_NUMBER": f"POL-REUSE-{s.world.classes[f.cls].pre}",
                    "BASIS": "Certified by the EAM diagnostic and quality process after "
                    + (f"grade {f.grade} inspection" if f.grade else "inspection")
                    + " and any part replacement",
                    "STATUS": "ACTIVE",
                }
            )
        if f.cls == "it" and f.spec.get("Data erasure") == "Certified":
            certs.append(
                {
                    "RECORD_ID": f"DE-{f.asset_id}",
                    "CERT_NUMBER": f"DE-{f.asset_id}",
                    "CERT_TYPE": "DATA_ERASURE",
                    "ASSET_ID": f.asset_id,
                    "ASSET_CLASS": f.cls,
                    "CERTIFIED_LIFE_MONTHS": None,
                    "ISSUE_DATE": issued.isoformat(),
                    "CERT_EXPIRY": None,
                    "TEST_RESULT": "PASS",
                    "REUSE_CLASS": REUSE[f.cls][0],
                    "DOCUMENT_NUMBER": "SOP-DATA-ERASE",
                    "BASIS": f"{f.qty} of {f.qty} devices erased (NIST SP 800-88 purge)",
                    "STATUS": "ACTIVE",
                }
            )
    for asset, when in REQUALIFIED.items():
        certs.append(
            {
                "RECORD_ID": f"CERT-{asset}",
                "CERT_NUMBER": f"RQ-{asset}",
                "CERT_TYPE": "REQUALIFICATION",
                "ASSET_ID": asset,
                "ASSET_CLASS": "control",
                "CERTIFIED_LIFE_MONTHS": 12,
                "ISSUE_DATE": when.isoformat(),
                "CERT_EXPIRY": _add_months(when, 12).isoformat(),
                "TEST_RESULT": "PASS",
                "REUSE_CLASS": REUSE["control"][0],
                "DOCUMENT_NUMBER": "POL-REUSE-CTL",
                "BASIS": "Requalified after burn-in and functional test",
                "STATUS": "ACTIVE",
            }
        )
    return {"controlled-documents": docs, "certificates": certs, "test-criteria": criteria}


SPEC = Spec(
    source_id="qms",
    title="MasterControl",
    schema="mastercontrol",
    base_path="/mastercontrol/mc/api",
    auth=Auth("oauth_cc"),
    paging=Paging(
        "page", page_param="pageNumber", size_param="pageSize", items_key="results", next_key="nextPage", total_key="totalCount"
    ),
    resources=(
        Resource(
            "controlled-documents",
            "/v2/controlled-documents",
            "DOCUMENT_NUMBER",
            filters=("DOCUMENT_TYPE", "ASSET_CLASS", "REUSE_CLASS", "STATUS"),
        ),
        Resource(
            "certificates",
            "/v2/certificates",
            "RECORD_ID",
            filters=("ASSET_ID", "CERT_NUMBER", "CERT_TYPE", "ASSET_CLASS", "TEST_RESULT", "STATUS"),
        ),
        Resource("test-criteria", "/v2/test-criteria", "TEST_ID", filters=("ASSET_CLASS", "DOCUMENT_NUMBER")),
    ),
    seed=seed,
)
