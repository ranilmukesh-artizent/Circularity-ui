"""The title mock's seed: 100 titles, synthetic, computed from the VIN's number (no randomness), and the scheduled
release of VIN ...003's lien. `titles()` is pure: the documents as the API serves them, in VIN order.
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import insert, text, update
from sqlalchemy.engine import Connection

from sim.core import clock, events, scheduler
from sim.seed import Seed
from sim.vendors.title_lien.models import TITLE, metadata

SOURCE = "uc_title"
HANDLER = "title_lien.release"
AS_OF = datetime(2026, 10, 7, 9, 0, tzinfo=UTC)
COUNT = 100
RELEASE_AFTER = timedelta(days=2)
LIENS = {3: 8200, 70: 6400}  # vin number -> amount of its one open lien
RELEASING = 3  # the lien that the lender releases (scheduled); VIN ...070's never does
BRANDS = {21: ("flood", "state title"), 22: ("rebuilt", "national title database"), 23: ("salvage", "state title")}


def vin(n: int) -> str:
    return f"SYNUC{n:012d}"


def _title(n: int) -> dict:
    brand, brand_source = BRANDS.get(n, (None, None))
    liens = []
    if n in LIENS:
        liens = [
            {
                "lienId": f"LN-{n:04d}",
                "holderRef": f"H-{n % 7 + 1:03d}",
                "amount": LIENS[n],
                "released": False,
                "releaseRef": None,
                "releasedAt": None,
            }
        ]
    return {
        "vin": vin(n),
        "titleStatus": "lien" if liens else "clear",
        "brand": brand,
        "brandSource": brand_source,
        "liens": liens,
        "checkedAt": AS_OF.isoformat(),
    }


def titles() -> list[dict]:
    return [_title(n) for n in range(1, COUNT + 1)]


def schedule_release(conn: Connection) -> None:
    scheduler.schedule(conn, AS_OF + RELEASE_AFTER, HANDLER, {"vin": vin(RELEASING)}, source=SOURCE)


@scheduler.handler(HANDLER)
def release(conn: Connection, payload: dict) -> None:
    """The lender releases the open lien: stamp it, clear the title, tell subscribers."""
    v = payload["vin"]
    now = clock.now(conn)
    doc = conn.execute(text("SELECT doc FROM title_lien.title WHERE vin = :v FOR UPDATE"), {"v": v}).scalar_one()
    ref = f"LR-{v[-6:]}"
    liens = [
        x | {"released": True, "releaseRef": ref, "releasedAt": now.isoformat()} if not x["released"] else x for x in doc["liens"]
    ]
    doc = doc | {"liens": liens, "titleStatus": "clear", "checkedAt": now.isoformat()}
    conn.execute(update(TITLE).where(TITLE.c.vin == v).values(doc=doc, updated_at=now))
    lien_id = next(x["lienId"] for x in liens if x["releaseRef"] == ref)
    events.emit(conn, SOURCE, "title.lien.released", v, {"vin": v, "lienId": lien_id, "releaseRef": ref}, now)


def load(conn: Connection, _s: Seed) -> dict[str, int]:
    rows = [{"vin": d["vin"], "doc": d, "updated_at": AS_OF - timedelta(minutes=COUNT - n)} for n, d in enumerate(titles(), 1)]
    conn.execute(insert(TITLE), rows)
    schedule_release(conn)
    return {"title": len(rows)}


def create(conn: Connection) -> None:
    conn.execute(text("CREATE SCHEMA IF NOT EXISTS title_lien"))
    metadata.create_all(conn)


def reset(conn: Connection, s: Seed) -> dict[str, int]:
    metadata.drop_all(conn)
    create(conn)
    return load(conn, s)


def ensure(conn: Connection, s: Seed) -> None:
    create(conn)
    if conn.execute(text("SELECT count(*) FROM title_lien.title")).scalar_one() == 0:
        load(conn, s)
        return
    still_open = conn.execute(
        text("SELECT doc ->> 'titleStatus' = 'lien' FROM title_lien.title WHERE vin = :v"), {"v": vin(RELEASING)}
    ).scalar()
    pending = conn.execute(
        text("SELECT count(*) FROM sim.scheduled WHERE handler = :h AND NOT done"), {"h": HANDLER}
    ).scalar_one()
    if still_open and not pending:  # scheduled work was cleared by a full reset of another kind
        schedule_release(conn)
