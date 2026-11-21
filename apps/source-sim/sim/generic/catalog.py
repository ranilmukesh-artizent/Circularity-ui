"""Helpers for the catalogue systems' generic mocks (sim/generic/specs/catalog_*.py; plan 6, task A3).

The Connection Fabric's catalogue lists 15 systems a person can connect (Workday HCM, Jira, PostgreSQL, Amazon S3 ...).
Each has a generic mock here so that connecting one really reads records: synthetic, seeded deterministically from the
demo's world (its sites, tenants and returned assets), with resources and field names that read like that product's
API. None of them is a real connection to the vendor.

    h("workday", "W-001")            → a stable integer from the parts (md5)
    pick(LIST, "workday", "W-001")   → a stable element
    ago(s, "key", days=90)           → a stable timestamp before the world's as-of
    facts(s)                         → the returned assets' facts, in case order
"""

import hashlib
from datetime import datetime, timedelta
from typing import Any

from sim.seed import Seed
from sim.seed.model import CaseFacts

PEOPLE = (
    "Asha Menon", "Daniel Okafor", "Priya Natarajan", "Lena Fischer", "Marco Rossi", "Sofia Alvarez", "Kenji Watanabe",
    "Grace Mensah", "Omar Haddad", "Ingrid Larsen", "Ravi Shankar", "Chloe Martin", "Tomasz Nowak", "Aisha Bello",
    "Lucas Moreau", "Mei Lin", "Arjun Pillai", "Hannah Becker", "Diego Santos", "Fatima Zahra",
)  # fmt: skip
TEAMS = (
    ("Returns Operations", "CC-4100"), ("Integration Engineering", "CC-4200"), ("Reliability Engineering", "CC-4300"),
    ("Finance - Asset Recovery", "CC-5100"), ("Commercial - Remarketing", "CC-5200"), ("EHS and Compliance", "CC-6100"),
)  # fmt: skip


def h(*parts: Any) -> int:
    return int(hashlib.md5("|".join(str(p) for p in parts).encode()).hexdigest()[:8], 16)


def pick(items: tuple | list, *parts: Any) -> Any:
    return items[h(*parts) % len(items)]


def ago(s: Seed, *parts: Any, days: int = 90) -> datetime:
    return s.world.as_of - timedelta(minutes=h(*parts, "ago") % (days * 24 * 60))


def iso(d: datetime) -> str:
    return d.isoformat()


def facts(s: Seed) -> list[CaseFacts]:
    return [c.facts for c in s.cases.values()]


def email(name: str) -> str:
    return name.lower().replace(" ", ".") + "@northfield.example"
