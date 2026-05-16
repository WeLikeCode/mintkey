# Admin API — Python 3.12 + FastAPI (ADR-0005, ADR-0012)
# Build context must be repo root so mintkey-models/ is accessible.
FROM python:3.12-slim

WORKDIR /app

# Install admin-api deps
COPY admin-api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY admin-api/src/ src/
# Copy shared mintkey_models package directly into PYTHONPATH so no editable install needed.
COPY mintkey-models/mintkey_models/ src/mintkey_models/

ENV PYTHONPATH=/app/src
ENV PORT=8080

# Run as non-root (UID 65532 matches distroless nonroot convention for consistency)
RUN useradd -u 65532 -M -s /sbin/nologin nonroot && chown -R 65532:65532 /app
USER 65532:65532

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python3 -c "import urllib.request,sys; urllib.request.urlopen('http://localhost:8080/v1/health'); sys.exit(0)" || exit 1

CMD ["uvicorn", "admin_api.main:app", "--host", "0.0.0.0", "--port", "8080"]
