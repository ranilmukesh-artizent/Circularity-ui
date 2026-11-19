"""The partner's drop: what Sims Lifecycle Services publishes to /outbound, built from the seed and kept on disk.

The drop directory is the SFTP server's chroot (env SIMS_SFTP_ROOT, default /tmp/sims-sftp; outside /app so the
dev server's reloader never sees it). Layout, as a partner drop:
    /outbound/partner-rates.csv            /outbound/partner-rates.csv.sig
    /outbound/vendor-approvals.csv         /outbound/vendor-approvals.csv.sig
    /outbound/material-yields.csv          /outbound/material-yields.csv.sig
    /outbound/custody-certificates.csv     /outbound/custody-certificates.csv.sig
    /outbound/manifest.json                /outbound/manifest.json.sig
A `.sig` file is the detached signature of its file: HMAC-SHA256 over the file's bytes with the demo signing key
"rcy-demo-signing-key", as lowercase hex and a newline. `manifest.json` lists every CSV with its size, row count and
SHA-256. File contents, names, values and signatures are the ones the generic mock served before (tuned to the demo).
Modification times are the drop time on the simulated clock: the seed drop is 2 days before the demo's as-of time
("last import 2 days ago").
"""

import csv
import hashlib
import hmac
import io
import json
import os
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sim.seed import Seed

SIGNING_KEY = b"rcy-demo-signing-key"
INR_PER_USD = 83.5
OUTBOUND = "outbound"
NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,120}$")
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


def root() -> Path:
    return Path(os.environ.get("SIMS_SFTP_ROOT", "/tmp/sims-sftp"))


def outbound() -> Path:
    return root() / OUTBOUND


def signature(data: bytes) -> str:
    return hmac.new(SIGNING_KEY, data, hashlib.sha256).hexdigest()


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _csv(header: list[str], rows: list[list]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(header)
    w.writerows(rows)
    return buf.getvalue()


def _rate_tne(code: str, inr_per_kg: float) -> str:
    return f"{code} {inr_per_kg * 1000 / INR_PER_USD / 1000:.1f}k"


def dropped_at(s: Seed) -> datetime:
    """When the seed drop was published: 2 days before the as-of time (the demo: last import 2 days ago)."""
    return s.world.as_of - timedelta(days=2)


def build(s: Seed, at: datetime | None = None) -> dict[str, bytes]:
    """Every file of a drop published at `at` (default: the seed's drop time): CSVs, manifest and signatures."""
    at = at or dropped_at(s)
    approved = VENDORS[0][2]
    csvs = {
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
    files = {name: text.encode() for name, text in csvs.items()}
    manifest = json.dumps(
        {
            "partner": "Sims Lifecycle Services",
            "generatedAt": at.isoformat(),
            "files": [{"fileName": n, "size": len(b), "rows": b.count(b"\n") - 1, "sha256": sha256(b)} for n, b in files.items()],
        },
        indent=1,
    ).encode()
    files["manifest.json"] = manifest
    for name in list(files):
        files[name + ".sig"] = (signature(files[name]) + "\n").encode()
    return files


def _write(path: Path, data: bytes, at: datetime) -> None:
    tmp = path.with_name(f".{path.name}.part")
    tmp.write_bytes(data)
    ts = at.timestamp()
    os.utime(tmp, (ts, ts))
    os.replace(tmp, path)  # atomic: a client mid-download never sees half a file


def publish(s: Seed, at: datetime | None = None) -> int:
    """Write a whole drop (replacing whatever is there). Returns the number of files."""
    at = at or dropped_at(s)
    files = build(s, at)
    out = outbound()
    out.mkdir(parents=True, exist_ok=True)
    for name, data in files.items():
        _write(out / name, data, at)
    for p in out.iterdir():  # anything else (a tampered extra file, leftovers) goes
        if p.name not in files:
            p.unlink(missing_ok=True)
    return len(files)


def exists() -> bool:
    return (outbound() / "manifest.json").is_file()


def put(name: str, data: bytes, at: datetime) -> None:
    """Replace one file as is, without signing it again (a corrupted or tampered file, for tests and demos)."""
    if not NAME.match(name):
        raise ValueError(f"bad file name {name!r}")
    outbound().mkdir(parents=True, exist_ok=True)
    _write(outbound() / name, data, at)


def read(name: str) -> bytes | None:
    if not NAME.match(name):
        return None
    p = outbound() / name
    return p.read_bytes() if p.is_file() else None


def listing() -> list[dict]:
    out = []
    if not outbound().is_dir():
        return out
    for p in sorted(outbound().iterdir()):
        if not p.is_file() or p.name.startswith("."):
            continue
        st = p.stat()
        data = p.read_bytes()
        out.append(
            {
                "fileName": p.name,
                "path": f"/{OUTBOUND}/{p.name}",
                "size": st.st_size,
                "modifiedAt": datetime.fromtimestamp(int(st.st_mtime), UTC).isoformat(),
                "sha256": sha256(data),
            }
        )
    return out
