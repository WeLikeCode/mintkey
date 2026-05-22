# MCP Server — Python 3.12 + FastAPI (ADR-0009, ADR-0012)
# Build context must be repo root so mintkey-models/ is accessible.
# Pinned 2026-05-18; re-pin every quarter.
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim@sha256:e5b65587bce7de595f299855d7385fe7fca39b8a74baa261ba1b7147afa78e58

WORKDIR /app

# Copy lock + manifest first for layer cache
COPY apps/mcp-server/pyproject.toml apps/mcp-server/uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

# Copy source
COPY apps/mcp-server/src/ src/
COPY mintkey-models/mintkey_models/ src/mintkey_models/
# Skills directory — contains agent-bootstrap.md served by the bootstrap tool (R6)
COPY apps/mcp-server/skills/ skills/

RUN uv sync --frozen --no-dev

ENV PYTHONPATH=/app/src
ENV PORT=8082
ENV PATH="/app/.venv/bin:$PATH"

# Run as non-root (UID 65532 matches distroless nonroot convention for consistency)
RUN useradd -u 65532 -M -s /sbin/nologin nonroot && chown -R 65532:65532 /app
USER 65532:65532

EXPOSE 8082

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python3 -c "import urllib.request,sys; urllib.request.urlopen('http://localhost:8082/health'); sys.exit(0)" || exit 1

CMD ["uvicorn", "mcp_server.main:app", "--host", "0.0.0.0", "--port", "8082"]
