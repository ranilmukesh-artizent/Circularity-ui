# Full-stack POC

The plan is [`docs/PLAN_FULLSTACK_POC.md`](../docs/PLAN_FULLSTACK_POC.md). The static demo (`fixtures/demo/index.html`) is unchanged and still the reference.

| App | What it is | Local URL |
|---|---|---|
| `web/` | React app (Vite, TypeScript) | http://localhost:5173 |
| `api/` | `di-api` (FastAPI) and `di-worker` (`python -m di.worker`), one Python package `di` | http://localhost:8000/docs |
| `source-sim/` | Mock source systems on Postgres: SAP S/4HANA, SAP Ariba, generic vendor mocks | http://localhost:8100/docs |

## Run

Needs Docker (Docker Desktop or Rancher Desktop) running.

```sh
docker compose up --build          # postgres, source-sim, api (runs migrations), worker, web
```

Open http://localhost:5173. The status page shows the API, the `di` database migration and source-sim; all three should read **OK**.

Postgres listens on `localhost:5432` (user and password `circ`), with two databases, `di` and `sources`. To change the defaults, copy `.env.example` to `.env`.

### On Windows with WSL (no Docker Desktop)

One-time setup, from PowerShell:

```powershell
wsl --install -d Ubuntu-24.04 --no-launch
wsl -d Ubuntu-24.04 -u root -- bash -lc "apt-get update && apt-get install -y docker.io docker-compose-v2 && systemctl enable --now docker"
# keep WSL from adding the Windows PATH (a Windows Docker credential helper on it breaks image pulls)
wsl -d Ubuntu-24.04 -u root -- bash -lc "printf '[boot]\nsystemd=true\n\n[interop]\nappendWindowsPath=false\n' > /etc/wsl.conf"
wsl --terminate Ubuntu-24.04
```

Each time:

```powershell
wsl -d Ubuntu-24.04 -u root -- bash -lc "cd /mnt/c/<path-to>/Circularity-ui && docker compose up -d --build"
```

WSL stops the Ubuntu VM, and the stack with it, shortly after the last WSL window closes. Keep a WSL terminal open while you use the app (`wsl -d Ubuntu-24.04`). The services have `restart: unless-stopped`, so they come back when Docker starts again.

## Mock source systems (source-sim)

Twenty mocked enterprise systems answer at http://localhost:8100, each below its own path:
- `/sap/opu/odata/sap` for S/4HANA
- `/ariba/api` for Ariba
- `/salesforce/services/data/v59.0` for Salesforce
- `/maximo/api` for Maximo
- and so on for the others; `GET /_sim/systems` lists them all

Each module's docstring gives its demo credentials (`apps/source-sim/sim/s4`, `sim/ariba`, `sim/vendors/*`). For the generic specs (`sim/generic/specs/*`), the credentials follow `sim/generic/spec.py`:
- API key: `<id>-demo-key`
- Basic: `di-connector` / `<id>-demo`
- OAuth: `di-connector` / `<id>-demo-secret`

Controlling the simulation:

```sh
curl localhost:8100/_sim/clock                                                   # simulated time (starts 7 Oct 2026 09:00 UTC)
curl -X POST localhost:8100/_sim/clock/advance -H 'content-type: application/json' -d '{"days": 3}'
curl -X POST localhost:8100/_sim/faults -H 'content-type: application/json' -d '{"system": "erp", "kind": "unavailable", "minutes": 30}'
curl -X POST localhost:8100/_sim/faults/demo                                     # the demo's starting fault (Ritchie Bros. token expired)
curl -X POST localhost:8100/_sim/webhooks -H 'content-type: application/json' -d '{"url": "http://source-sim:8100/_sim/sink"}'
curl localhost:8100/_sim/sink                                                    # events received by the demo sink
curl -X POST localhost:8100/_sim/reset                                           # every system back to the seed, clock reset
```

The source-sim tests use the same database as the running service, so run `/_sim/reset` after a test run.

## Test

```sh
docker compose run --rm api pytest
docker compose run --rm source-sim pytest
cd apps/web && npm install && npm run build
```

## Add a migration

```sh
docker compose run --rm api alembic revision --autogenerate -m "what changed"
```

## Reset everything

```sh
docker compose down -v             # also deletes the database volume
```
