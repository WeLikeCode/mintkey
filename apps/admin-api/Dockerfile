# Admin API — Python 3.14 + FastAPI (ADR-0005, ADR-0012)
# Build context must be repo root so packages/python/mintkey-models/ is accessible.
# Pinned 2026-10-17; re-pin every quarter.
# uv's documented pattern: the uv binary copied onto python:3.14-slim-bookworm, because the
# ghcr.io/astral-sh/uv:python3.12-bookworm-slim image still shipped Debian 12.13 (2026-10: perl-base, krb5,
# pcre2 HIGH/CRITICAL fixed only in later point releases). Both FROM lines are digest-pinned for Dependabot.
FROM ghcr.io/astral-sh/uv:0.13.1@sha256:4a1f3666816dafadd20ceb71eac9a7d56d7ef30279f7d64048519ab901ada336 AS uv
FROM python:3.14-slim-bookworm@sha256:48b13b003dda20b16f9442b8475aa05fe21bf6579a8c881db92ffb4d8fd20f83
COPY --from=uv /uv /uvx /usr/local/bin/
# The base image's pip vendors msgpack 1.1.2 / urllib3 2.7.0 / setuptools 70.3.0 (Trivy HIGH). Dependencies are
# installed by uv, so pip is not needed at runtime.
RUN rm -rf /usr/local/lib/python3.14/site-packages/pip /usr/local/lib/python3.14/site-packages/pip-*.dist-info /usr/local/bin/pip /usr/local/bin/pip3 /usr/local/bin/pip3.14

WORKDIR /app

# Copy lock + manifest first for layer cache
COPY apps/admin-api/pyproject.toml apps/admin-api/uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

# Copy source
COPY apps/admin-api/src/ src/
# Copy shared mintkey_models package directly into PYTHONPATH so no editable install needed.
COPY packages/python/mintkey-models/mintkey_models/ src/mintkey_models/

# Install the project itself (without re-resolving) — picks up admin_api package
RUN uv sync --frozen --no-dev

ENV PYTHONPATH=/app/src
ENV PORT=8080
ENV PATH="/app/.venv/bin:$PATH"

# Run as non-root (UID 65532 matches distroless nonroot convention for consistency)
RUN useradd -u 65532 -M -s /sbin/nologin nonroot && chown -R 65532:65532 /app
USER 65532:65532

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python3 -c "import urllib.request,sys; urllib.request.urlopen('http://localhost:8080/v1/health'); sys.exit(0)" || exit 1

CMD ["uvicorn", "admin_api.main:app", "--host", "0.0.0.0", "--port", "8080"]
