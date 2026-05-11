# MCP Server — Python 3.12 + FastAPI (ADR-0009, ADR-0012)
# Build context must be repo root so mintkey-models/ is accessible.
FROM python:3.12-slim

WORKDIR /app

COPY mcp-server/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY mcp-server/src/ src/
COPY mintkey-models/mintkey_models/ src/mintkey_models/

ENV PYTHONPATH=/app/src
ENV PORT=8082

EXPOSE 8082

CMD ["uvicorn", "mcp_server.main:app", "--host", "0.0.0.0", "--port", "8082"]
