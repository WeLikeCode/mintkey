# Mock Backend — Python 3.12 + FastAPI
# Build context is mock-backend/ directory.
# Pinned 2026-05-18; re-pin every quarter.
FROM python:3.12-slim-bookworm@sha256:d193c6f51a7dbd10395d6328de3a7edb0516fb0608ca138036576f574c3e07d2

WORKDIR /app

COPY src/ src/
COPY pyproject.toml .

RUN pip install --no-cache-dir -e .

# Run as non-root (UID 65532 matches distroless nonroot convention for consistency)
RUN useradd -u 65532 -M -s /sbin/nologin nonroot && chown -R 65532:65532 /app
USER 65532:65532

ENV PYTHONPATH=/app/src

EXPOSE 8999

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python3 -c "import urllib.request,sys; urllib.request.urlopen('http://localhost:8999/health'); sys.exit(0)" || exit 1

CMD ["uvicorn", "mock_backend.rest.main:app", "--host", "0.0.0.0", "--port", "8999"]
