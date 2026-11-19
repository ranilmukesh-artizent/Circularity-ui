"""Sims Lifecycle Services (the demo's SOURCES.rcy): no partner API, only a signed CSV drop that DI imports by hand
("IMPORT partner-rates.csv"; auth "SFTP drop · signed manifest").

The SFTP folder is served as a read-only file listing at the registry's base path:
    GET /sims/outbound               the files, each with size, SHA-256 and HMAC-SHA256 signature
    GET /sims/outbound/{fileName}    one file, its CSV text in `content`
`manifest.json` lists every CSV with its hash; its own signature covers the manifest text. Signatures use the demo
signing key "rcy-demo-signing-key". Basic auth stands in for the SFTP login.

MAPPINGS.rcy: VND_CERT ISO14001-VA (Approved vendor A, ISO 14001, valid to Mar 2027) and RATE_TNE "Cu 7.8k"
(the demo's ₹650/kg copper partner rate at 83.5 INR/USD = $7,784/t).
"""

import csv
import hashlib
import hmac
import io
import json
from datetime import timedelta

from sim.generic.spec import Auth, Paging, Resource, Spec
from sim.seed import Seed

SIGNING_KEY = b"rcy-demo-signing-key"
INR_PER_USD = 83.5
# vendor id, name, certificate code, standard, valid to, status
VENDORS = [
    ("SIMS-MAA", "Sims Lifecycle Services · Chennai (Gummidipoondi)", "ISO14001-VA", "ISO 14001", "2027-03-31", "APPROVED"),
    ("VND-B", "Approved vendor B", "R2V3-VB", "R2v3", "2027-06-30", "APPROVED"),
    ("VND-U", "Uncertified vendor", "ISO14001-VU", "ISO 14001", "2026-08-12", "LAPSED"),
]
# material, INR per kg (copper from the demo; the rest assumed), basis
RATES = [
    ("Cu", "Copper", 650.0, "rebate"),
    ("Fe", "Steel and other ferrous metals", 27.0, "rebate"),
    ("Al", "Aluminium", 140.0, "rebate"),
    ("PCB", "Printed circuit boards", 210.0, "rebate"),
    ("LiB", "Li-ion cells (hazardous route)", -75.0, "fee"),
]
# class -> recovered kg per unit (copper and steel for motors from the demo's RT-1027 harvest; others assumed)
YIELDS = {
    "motor": {"Cu": 11.4, "Fe": 96.0, "Al": 4.0},
    "pump": {"Fe": 38.0, "Al": 6.0, "Cu": 0.6},
    "control": {"PCB": 1.2, "Cu": 0.4, "Al": 0.9},
    "drill": {"Cu": 0.2, "Fe": 0.6, "LiB": 0.6},
    "batch": {"Cu": 0.2, "Fe": 0.5, "LiB": 0.4},
    "it": {"PCB": 0.3, "Al": 0.8, "LiB": 0.25},
}


def _csv(header: list[str], rows: list[list]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(header)
    w.writerows(rows)
    return buf.getvalue()


def _rate_tne(code: str, inr_per_kg: float) -> str:
    return f"{code} {inr_per_kg * 1000 / INR_PER_USD / 1000:.1f}k"


def seed(s: Seed) -> dict[str, list[dict]]:
    as_of = s.world.as_of
    dropped = (as_of - timedelta(days=2)).isoformat()  # the demo: last import 2 days ago
    approved = VENDORS[0][2]
    files = {
        "partner-rates.csv": _csv(
            [
                "VENDOR_ID",
                "VND_CERT",
                "MATERIAL",
                "MATERIAL_NAME",
                "RATE_INR_KG",
                "RATE_USD_TNE",
                "RATE_TNE",
                "BASIS",
                "VALID_FROM",
            ],
            [
                [VENDORS[0][0], approved, c, n, f"{r:.2f}", round(r * 1000 / INR_PER_USD), _rate_tne(c, r), b, "2026-10-01"]
                for c, n, r, b in RATES
            ],
        ),
        "vendor-approvals.csv": _csv(
            ["VENDOR_ID", "VENDOR_NAME", "VND_CERT", "CERT_STANDARD", "VALID_TO", "STATUS"], [list(v) for v in VENDORS]
        ),
        "material-yields.csv": _csv(
            ["ASSET_CLASS", "MATERIAL", "KG_PER_UNIT", "VND_CERT"],
            [[cls, m, kg, approved] for cls, ys in YIELDS.items() for m, kg in ys.items()],
        ),
        "custody-certificates.csv": _csv(
            ["CERT_ID", "DECISION_ID", "ASSET_ID", "ASSET_CLASS", "QTY", "ROUTE", "PROCESSED_ON", "VND_CERT"],
            [
                [f"COC-{d.id}", d.id, d.asset_id, d.cls, d.q, d.route, d.date.date().isoformat(), approved]
                for d in s.decisions
                if d.route in ("material", "exit") and d.status == "reconciled"
            ],
        ),
    }

    def sign(text: str) -> tuple[str, str]:
        b = text.encode()
        return hashlib.sha256(b).hexdigest(), hmac.new(SIGNING_KEY, b, hashlib.sha256).hexdigest()

    docs = []
    for name, text in files.items():
        sha, sig = sign(text)
        docs.append(
            {
                "fileName": name,
                "contentType": "text/csv",
                "size": len(text.encode()),
                "rows": text.count("\n") - 1,
                "sha256": sha,
                "signature": sig,
                "signatureAlgorithm": "HMAC-SHA256",
                "modifiedAt": dropped,
                "content": text,
            }
        )
    manifest = json.dumps(
        {
            "partner": "Sims Lifecycle Services",
            "generatedAt": dropped,
            "files": [{k: d[k] for k in ("fileName", "size", "rows", "sha256")} for d in docs],
        },
        indent=1,
    )
    sha, sig = sign(manifest)
    docs.append(
        {
            "fileName": "manifest.json",
            "contentType": "application/json",
            "size": len(manifest.encode()),
            "rows": None,
            "sha256": sha,
            "signature": sig,
            "signatureAlgorithm": "HMAC-SHA256",
            "modifiedAt": dropped,
            "content": manifest,
        }
    )
    return {"files": docs}


SPEC = Spec(
    source_id="rcy",
    title="Sims Lifecycle Services",
    schema="sims",
    base_path="/sims/outbound",
    auth=Auth("basic"),
    paging=Paging("offset", items_key="files", next_key="nextOffset", total_key="total"),
    resources=(Resource("files", "", "fileName", filters=("contentType",)),),
    seed=seed,
)
