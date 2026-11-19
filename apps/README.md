# Full-stack POC

The plan is [`docs/PLAN_FULLSTACK_POC.md`](../docs/PLAN_FULLSTACK_POC.md). The static demo (`index.html` at the repository root) is unchanged and still the reference.

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
