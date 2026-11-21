"""Re-encrypt every stored source credential with the current DI_SECRET_KEY (key rotation, plan 6 follow-up).

    docker compose exec -T -e PYTHONPATH=/app api python scripts/reencrypt_secrets.py
    bash scripts/dev/reencrypt-secrets.sh

To rotate: set DI_SECRET_KEY to "NEW,OLD" (comma-separated Fernet keys: the first encrypts, every one decrypts),
restart api and worker, run this script, then set DI_SECRET_KEY to "NEW" alone and restart again. Prints only counts
and the source ids and versions it could not read (no key in the list opens them); never a key or a secret. Exits 1
when a credential could not be read (the readable ones are re-encrypted and committed all the same).
"""

import sys

from di.connectors.secrets import reencrypt
from di.db import SessionLocal


def main() -> int:
    with SessionLocal() as s:
        out = reencrypt(s)
        s.commit()
    print(f"{out['reencrypted']} re-encrypted with the current key, {len(out['unreadable'])} unreadable")
    for r in out["unreadable"]:
        print(f"  unreadable: {r['source_id']} {r['kind']} v{r['version']}")
    return 1 if out["unreadable"] else 0


if __name__ == "__main__":
    sys.exit(main())
