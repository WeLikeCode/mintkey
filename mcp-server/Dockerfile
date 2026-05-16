# MCP Server — Python 3.12 + FastAPI (ADR-0009, ADR-0012)
# Build context must be repo root so mintkey-models/ is accessible.
FROM python:3.14-slim

WORKDIR /app

COPY mcp-server/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY mcp-server/src/ src/
COPY mintkey-models/mintkey_models/ src/mintkey_models/
# Skills directory — contains agent-bootstrap.md served by the bootstrap tool (R6)
COPY mcp-server/skills/ skills/

ENV PYTHONPATH=/app/src
ENV PORT=8082

# Run as non-root (UID 65532 matches distroless nonroot convention for consistency)
RUN useradd -u 65532 -M -s /sbin/nologin nonroot && chown -R 65532:65532 /app
USER 65532:65532

EXPOSE 8082

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python3 -c "import urllib.request,sys; urllib.request.urlopen('http://localhost:8082/health'); sys.exit(0)" || exit 1

CMD ["uvicorn", "mcp_server.main:app", "--host", "0.0.0.0", "--port", "8082"]
