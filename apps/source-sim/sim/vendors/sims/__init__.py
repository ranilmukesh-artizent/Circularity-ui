"""Sims Lifecycle Services mock (the demo's SOURCES.rcy; docs/backend-steps.md, B5b): a partner SFTP drop.

The demo: "Partner SFTP", auth "SFTP drop · signed manifest", "Controlled CSV import", "No supported partner API.
Manual import supports evaluation, not live automation." MAPPINGS.rcy: VND_CERT ISO14001-VA → vendor.certification
certified (Certificate table); RATE_TNE "Cu 7.8k" → Cu $7,800 / t (₹650/kg at 83.5 INR/USD = $7,784/t).

Sims publishes no API documentation; a partner file drop has no public contract. Everything below is assumed, after
the common shape of a partner SFTP exchange:
- a real SFTP server (sftp.py, asyncssh) on port 2222, user di-connector / password rcy-demo, a fixed Ed25519 host
  key, chrooted to the drop, read only for Circularity (no writes, no shell);
- /outbound holds four CSV files (UTF-8, comma separated, header row, "\n" line ends), `manifest.json` (each CSV's
  size, row count and SHA-256) and a detached signature per file (`<file>.sig`: HMAC-SHA256 hex with the shared
  signing key "rcy-demo-signing-key"; a real partner would use PGP);
- the drop is complete each time (all files replaced together); file modification times are the publication time on
  the simulated clock (the seed drop: 2 days before the as-of time).
Drop contents and seed: drop.py. Admin view over HTTP (not the partner's interface; api.py):
    GET  /sims/admin/outbound           files with size, modification time and SHA-256, and the SFTP details
    GET  /sims/admin/outbound/{name}    one file's bytes
    PUT  /sims/admin/outbound/{name}    replace a file without signing it (a tampered file)
    POST /sims/admin/publish            publish the drop again, stamped with the simulated time
    POST /sims/admin/regenerate         rebuild the seed drop (also done by POST /_sim/reset?system=rcy)
"""

from sim.mock import Mock
from sim.vendors.sims import api, sftp

MOCK = Mock("rcy", api.router, api.ensure, api.reset, "Sims Lifecycle Services", startup=sftp.startup)
