#!/bin/bash
# Re-encrypt every stored source credential with the current DI_SECRET_KEY (the first key of the comma-separated
# list), after a key rotation: set DI_SECRET_KEY="NEW,OLD", restart api and worker, run this, then keep only NEW.
#   bash scripts/dev/reencrypt-secrets.sh
# Prints counts only (never a key or a secret); exits 1 if a credential opens with none of the keys.
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
docker compose exec -T -e PYTHONPATH=/app api python scripts/reencrypt_secrets.py  # /app on the path, for `di`
