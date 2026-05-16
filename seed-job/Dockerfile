# Seed job — Python 3.12, one-shot (ADR-0005)
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .
COPY realm-mintkey.json .

# Run as non-root (UID 65532 matches distroless nonroot convention for consistency).
# NOTE: /run/secrets/mintkey/bootstrap-secrets is a Docker named volume mounted
# at runtime. On fresh installs Docker creates the volume directory owned by the
# first writer (UID 65532). On existing installs the volume is root-owned from the
# prior root seed-job run; see DEPLOYMENT.md for the HEALTHCHECK deferral note.
RUN useradd -u 65532 -M -s /sbin/nologin nonroot && chown -R 65532:65532 /app
USER 65532:65532

# No HEALTHCHECK — this is a one-shot init container. See DEPLOYMENT.md.

CMD ["python", "main.py"]
