# Mock Backend — Python 3.12 + FastAPI
# Build context is mock-backend/ directory.
# Pinned 2026-05-18; re-pin every quarter.
FROM python:3.14-slim-bookworm@sha256:86f975aca15cf04a40b399eebede9aea7c82eae084d1f1a0a6ef6bcaae871a30

WORKDIR /app

COPY src/ src/
COPY pyproject.toml .
COPY requirements-hashes.txt .

# Install pinned deps with hash verification, then install the local package.
# --require-hashes cannot apply to a local editable ('.') path, so we install
# third-party deps first (hashes verified) and then install the package itself.
RUN pip install --no-cache-dir --require-hashes -r requirements-hashes.txt \
 && pip install --no-cache-dir --no-deps .

# Run as non-root (UID 65532 matches distroless nonroot convention for consistency)
RUN useradd -u 65532 -M -s /sbin/nologin nonroot && chown -R 65532:65532 /app
USER 65532:65532

ENV PYTHONPATH=/app/src

EXPOSE 8999

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python3 -c "import urllib.request,sys; urllib.request.urlopen('http://localhost:8999/health'); sys.exit(0)" || exit 1

CMD ["uvicorn", "mock_backend.rest.main:app", "--host", "0.0.0.0", "--port", "8999"]
