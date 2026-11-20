# source-sim, the mocked enterprise systems. Two targets:
#   dev      what docker-compose.yml builds: runtime and dev locks, the source is bind-mounted over /app, uvicorn --reload,
#            and the source-sim tests run in it.
#   runtime  no dev tools, no tests, a non-root user; the golden files (the seed) are mounted read-only at /fixtures
#            (docker-compose.prod.yml), as in dev.
# The base image is pinned by digest (python 3.12.16-slim, Debian trixie, built 2026-11-05). Both targets build with the
# classic builder too (no BuildKit-only syntax): `docker build --target runtime -t circ-sim apps/source-sim`.
FROM python:3.12.16-slim-trixie@sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
# Locked, hash-checked installs (requirements*.in -> *.lock, docs/agents/dos-and-donts.md "Dependencies").
COPY requirements.lock ./
RUN pip install --no-cache-dir --require-hashes --no-deps -r requirements.lock

FROM base AS dev
# Compose runs the tests in this image, so it carries the dev lock too.
COPY requirements-dev.lock ./
RUN pip install --no-cache-dir --require-hashes --no-deps -r requirements-dev.lock
COPY . .
EXPOSE 8100
CMD ["uvicorn", "sim.main:app", "--host", "0.0.0.0", "--port", "8100"]

FROM base AS runtime
RUN useradd --system --uid 10001 --gid 0 --no-create-home --shell /usr/sbin/nologin app
COPY pyproject.toml ./
COPY sim ./sim
USER 10001
# 8100 HTTP, 2222 the SFTP drop (Sims Lifecycle Services)
EXPOSE 8100 2222
CMD ["uvicorn", "sim.main:app", "--host", "0.0.0.0", "--port", "8100"]
