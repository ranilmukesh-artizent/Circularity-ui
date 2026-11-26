# di-api and di-worker (one image, two commands). Two targets:
#   dev      what docker-compose.yml builds: runtime and dev locks, the source is bind-mounted over /app, uvicorn --reload,
#            and the api tests run in it (scripts/dev/api-test.sh).
#   runtime  no dev tools, no tests or scripts, a non-root user; the golden files are mounted read-only at /fixtures
#            (docker-compose.prod.yml), as in dev.
# The base image is pinned by digest (python 3.12.16-slim, Debian trixie, built 2026-11-05). Both targets build with the
# classic builder too (no BuildKit-only syntax): `docker build --target runtime -t circ-api backend`.
FROM python:3.12.16-slim-trixie@sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
# libgomp1: the OpenMP runtime lightgbm loads (plan 9 P9-6.9, the device price model)
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/*
# Locked, hash-checked installs (requirements*.in -> *.lock, docs/agents/dos-and-donts.md "Dependencies").
COPY requirements.lock ./
RUN pip install --no-cache-dir --require-hashes --no-deps -r requirements.lock

FROM base AS dev
# Compose runs the tests in this image, so it carries the dev lock too.
COPY requirements-dev.lock ./
RUN pip install --no-cache-dir --require-hashes --no-deps -r requirements-dev.lock
COPY . .
EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && uvicorn di.main:app --host 0.0.0.0 --port 8000"]

FROM base AS runtime
RUN useradd --system --uid 10001 --gid 0 --no-create-home --shell /usr/sbin/nologin app
COPY alembic.ini pyproject.toml ./
COPY migrations ./migrations
COPY di ./di
USER 10001
EXPOSE 8000
# the worker uses the same image: `python -m di.worker`
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn di.main:app --host 0.0.0.0 --port 8000"]
