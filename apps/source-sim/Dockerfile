FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
# Locked, hash-checked installs (requirements*.in -> *.lock, docs/agents/dos-and-donts.md "Dependencies").
# Compose runs tests in this image, so it carries the dev lock too.
COPY requirements.lock requirements-dev.lock ./
RUN pip install --no-cache-dir --require-hashes --no-deps -r requirements.lock -r requirements-dev.lock
COPY . .
EXPOSE 8100
CMD ["uvicorn", "sim.main:app", "--host", "0.0.0.0", "--port", "8100"]
