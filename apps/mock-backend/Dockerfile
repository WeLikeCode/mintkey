# Mock Backend — Python 3.12 + FastAPI
# Build context is mock-backend/ directory.
# Pinned 2026-10-17; re-pin every quarter.
FROM python:3.15-slim-bookworm@sha256:575f8bc12ec26542e0678bc6b60e385218248019d433157ec327264a78c3a853

WORKDIR /app

COPY src/ src/
COPY pyproject.toml .
COPY requirements-hashes.txt .

# Install pinned deps with hash verification, then install the local package.
# --require-hashes cannot apply to a local editable ('.') path, so we install
# third-party deps first (hashes verified) and then install the package itself.
# pip is not needed at run time: uninstall it with the build, so the image carries no pip-vendored packages
# (2026-10: pip 26.2.1, the latest, vendors msgpack 1.1.2, setuptools 70.3.0 and urllib3 2.7.0, all HIGH in Trivy).
RUN pip install --no-cache-dir --require-hashes -r requirements-hashes.txt \
 && pip install --no-cache-dir --no-deps . \
 && pip uninstall --yes pip

# Run as non-root (UID 65532 matches distroless nonroot convention for consistency)
RUN useradd -u 65532 -M -s /sbin/nologin nonroot && chown -R 65532:65532 /app
USER 65532:65532

ENV PYTHONPATH=/app/src

EXPOSE 8999

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python3 -c "import urllib.request,sys; urllib.request.urlopen('http://localhost:8999/health'); sys.exit(0)" || exit 1

CMD ["uvicorn", "mock_backend.rest.main:app", "--host", "0.0.0.0", "--port", "8999"]
