"""Sims Lifecycle Services (rcy): the partner's signed CSV drop (the demo's SOURCES.rcy, "SFTP drop · signed manifest").
Read only, imported in full every time (delta=False: a drop is a complete set of files).

The SFTP folder is served as a file listing (Basic auth stands in for the SFTP login): every file carries its SHA-256,
an HMAC-SHA256 signature and its text; `manifest.json` lists each CSV with its hash. Before a file is used:
    - the manifest's own hash and signature must match;
    - the file must be in the manifest, and its content must hash to the manifest's SHA-256 (and the listing's), and
      carry a valid signature.
A file that fails is one failed record (the run is partial, nothing from that file is used); the others import.

Facts (rcy has authority over vendor certification)
    vendor.<VENDOR_ID>   certification (certified / lapsed / …), cert_ref, cert_standard, cert_valid_to, name,
                         material_rates {material: usd_per_t, inr_per_kg, basis, label}, rebates, fees,
                         yields {asset class: {material: kg per unit}}, custody_certificates
The demo's mapping: VND_CERT ISO14001-VA → vendor.certification certified (Certificate table); RATE_TNE "Cu 7.8k" →
Cu $7,800 / t (Unit + currency; ₹650/kg at 83.5 INR/USD = $7,784/t).
"""

import csv
import hashlib
import hmac
import io
import json
from decimal import Decimal

from di.canonical.store import Fact
from di.connectors.base import Record, Resource
from di.connectors.generic import INR_PER_USD, GenericAdapter, keep

SIGNING_KEY = b"rcy-demo-signing-key"  # the partner's signing key (demo value)
CERT_TABLE = {"APPROVED": "certified", "LAPSED": "lapsed", "SUSPENDED": "suspended", "PENDING": "pending"}


class IntegrityError(Exception):
    pass


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def signature(text: str) -> str:
    return hmac.new(SIGNING_KEY, text.encode(), hashlib.sha256).hexdigest()


def problems(f: dict, manifest: dict | None, manifest_error: str | None) -> str | None:
    """Why a file cannot be trusted, or None."""
    if manifest_error:
        return manifest_error
    entry = next((e for e in manifest["files"] if e["fileName"] == f["fileName"]), None)
    if entry is None:
        return f"{f['fileName']} is not in the manifest"
    actual = sha256(f.get("content") or "")
    if actual != entry["sha256"]:
        return f"{f['fileName']}: SHA-256 {actual[:12]}… does not match the manifest ({entry['sha256'][:12]}…)"
    if f.get("sha256") and f["sha256"] != actual:
        return f"{f['fileName']}: SHA-256 does not match the listing"
    if not hmac.compare_digest(signature(f.get("content") or ""), f.get("signature") or ""):
        return f"{f['fileName']}: signature does not verify"
    return None


def rate_label(code: str, usd_per_t: int) -> str:
    """Cu, 7784 → 'Cu $7,800 / t' (to the nearest hundred, as the partner quotes)."""
    return f"{code} ${round(usd_per_t, -2):,} / t"


class SimsAdapter(GenericAdapter):
    source_id = "rcy"
    base_path = "/sims/outbound"
    auth_kind = "basic"
    items_key, next_key, next_param, size_param, page_size = "files", "nextOffset", "offset", "limit", 200

    def resources(self):
        return [Resource("files", self.read_files, delta=False)]

    def read_files(self, client, since):
        listing = self.read_all(client, "")
        url = client.url("")
        manifest, manifest_error = None, None
        mf = next((f for f in listing if f["fileName"] == "manifest.json"), None)
        if mf is None:
            manifest_error = "manifest.json is missing"
        elif sha256(mf.get("content") or "") != mf.get("sha256") or not hmac.compare_digest(
            signature(mf.get("content") or ""), mf.get("signature") or ""
        ):
            manifest_error = "manifest.json: hash or signature does not verify"
        else:
            manifest = json.loads(mf["content"])
        tables: dict[str, list[dict]] = {}
        for f in listing:
            name = f["fileName"]
            if name == "manifest.json" or not name.endswith(".csv"):
                continue
            err = problems(f, manifest, manifest_error)
            if err:
                yield Record(
                    name.removesuffix(".csv"), name, {"file": name, "integrity_error": err, "sha256": f.get("sha256")}, url
                )
                continue
            tables[name] = list(csv.DictReader(io.StringIO(f["content"])))
        approvals = tables.get("vendor-approvals.csv", [])
        vendor_of = {r["VND_CERT"]: r["VENDOR_ID"] for r in approvals}
        for r in approvals:
            yield Record("vendor-approvals", r["VENDOR_ID"], r, url)

        def by_vendor(rows: list[dict]) -> dict[str, list[dict]]:
            out: dict[str, list[dict]] = {}
            for r in rows:
                vid = r.get("VENDOR_ID") or vendor_of.get(r.get("VND_CERT") or "")
                if vid:
                    out.setdefault(vid, []).append(r)
            return out

        for name, resource in (
            ("partner-rates.csv", "partner-rates"),
            ("material-yields.csv", "material-yields"),
            ("custody-certificates.csv", "custody-certificates"),
        ):
            if name in tables:
                for vid, rows in sorted(by_vendor(tables[name]).items()):
                    yield Record(resource, vid, {"VENDOR_ID": vid, "rows": rows}, url)

    def map(self, record: Record) -> list[Fact]:
        p = record.payload
        if "integrity_error" in p:
            raise IntegrityError(p["integrity_error"])
        if record.resource == "vendor-approvals":
            return keep(self._approval(p))
        key = p["VENDOR_ID"]
        rows = p["rows"]
        if record.resource == "partner-rates":
            rates = {}
            for r in rows:
                inr = Decimal(r["RATE_INR_KG"])
                usd_t = int((inr * 1000 / INR_PER_USD).quantize(Decimal("1")))
                rates[r["MATERIAL"]] = {
                    "usd_per_t": usd_t,
                    "inr_per_kg": float(inr),
                    "basis": r.get("BASIS"),
                    "label": rate_label(r["MATERIAL"], usd_t),
                    "valid_from": r.get("VALID_FROM"),
                }
            return [
                Fact("vendor", key, "material_rates", rates, "RATE_TNE", [r["RATE_TNE"] for r in rows], "Unit + currency"),
                Fact(
                    "vendor",
                    key,
                    "rebates",
                    {m: v["usd_per_t"] for m, v in rates.items() if v["basis"] == "rebate"},
                    "RATE_INR_KG",
                    [f"{r['MATERIAL']} {r['RATE_INR_KG']}" for r in rows if r.get("BASIS") == "rebate"],
                    "INR/kg → USD/t at 83.5 INR/USD",
                ),
                Fact(
                    "vendor",
                    key,
                    "fees",
                    {m: -v["usd_per_t"] for m, v in rates.items() if v["basis"] == "fee"},
                    "RATE_INR_KG",
                    [f"{r['MATERIAL']} {r['RATE_INR_KG']}" for r in rows if r.get("BASIS") == "fee"],
                    "INR/kg → USD/t at 83.5 INR/USD (fee charged)",
                ),
            ]
        if record.resource == "material-yields":
            yields: dict[str, dict[str, float]] = {}
            for r in rows:
                yields.setdefault(r["ASSET_CLASS"], {})[r["MATERIAL"]] = float(r["KG_PER_UNIT"])
            return [
                Fact(
                    "vendor",
                    key,
                    "yields",
                    yields,
                    "KG_PER_UNIT",
                    [f"{r['ASSET_CLASS']} {r['MATERIAL']} {r['KG_PER_UNIT']}" for r in rows],
                    "kg per unit by asset class",
                )
            ]
        if record.resource == "custody-certificates":
            certs = [
                {
                    "ref": r["CERT_ID"],
                    "decision_id": r.get("DECISION_ID"),
                    "asset_id": r.get("ASSET_ID"),
                    "asset_class": r.get("ASSET_CLASS"),
                    "qty": int(r["QTY"]) if r.get("QTY") else None,
                    "route": r.get("ROUTE"),
                    "processed_on": r.get("PROCESSED_ON"),
                }
                for r in rows
            ]
            return [Fact("vendor", key, "custody_certificates", certs, "CERT_ID", [r["CERT_ID"] for r in rows], "Pass-through")]
        return []

    def _approval(self, r: dict) -> list[Fact]:
        key = r["VENDOR_ID"]
        status = r.get("STATUS") or ""
        return [
            Fact(
                "vendor",
                key,
                "certification",
                CERT_TABLE.get(status, status.lower() or None),
                "VND_CERT",
                r["VND_CERT"],
                "Certificate table",
            ),
            Fact("vendor", key, "cert_ref", r["VND_CERT"], "VND_CERT", r["VND_CERT"], "Pass-through"),
            Fact("vendor", key, "cert_status", status.lower() or None, "STATUS", status, "Status map"),
            Fact("vendor", key, "cert_standard", r.get("CERT_STANDARD"), "CERT_STANDARD", r.get("CERT_STANDARD"), "Pass-through"),
            Fact("vendor", key, "cert_valid_to", r.get("VALID_TO"), "VALID_TO", r.get("VALID_TO"), "ISO date"),
            Fact("vendor", key, "name", r.get("VENDOR_NAME"), "VENDOR_NAME", r.get("VENDOR_NAME"), "Pass-through"),
        ]


ADAPTER = SimsAdapter()
