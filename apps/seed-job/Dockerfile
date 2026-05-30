# Seed job — Python 3.12, one-shot (ADR-0005)
# Pinned 2026-05-18; re-pin every quarter.
FROM python:3.14-slim-bookworm@sha256:a9bee15510a364124aa24692899d269835683b883de42f7ebec8c293cf679ccb

WORKDIR /app

COPY requirements-hashes.txt .
RUN pip install --no-cache-dir --require-hashes -r requirements-hashes.txt

COPY main.py .
COPY realm-mintkey.json .

# seed-job runs as root intentionally (Option B, fix/seed-job-perms-2026-05-17).
#
# Rationale: this is a one-shot init container whose sole job is to WRITE secrets
# into the `bootstrap_secrets` Docker named volume. Named volumes are created
# root-owned by Docker; UID 65532 cannot write to them, causing PermissionError
# on '/run/secrets/mintkey/bootstrap-secrets/admin_password' et al.
#
# Running as root is the canonical pattern for init/seed containers (cf. Kubernetes
# init containers, Helm hooks). The chmod calls in main.py (0o640 / 0o644 / 0o600)
# still run and set per-file permissions so that downstream containers (admin-api
# UID 65532, Grafana UID 472, etc.) can READ the files after seed-job exits.
#
# Security posture: seed-job has no network exposure and no persistent process;
# it exits 0 immediately after writing. The blast radius of root inside this
# ephemeral container is bounded by the named volumes it mounts.
RUN useradd -u 65532 -M -s /sbin/nologin nonroot && chown -R 65532:65532 /app
# USER directive omitted — seed-job runs as root so it can write to the
# root-owned bootstrap_secrets named volume. See comment block above.

# No HEALTHCHECK — this is a one-shot init container. See DEPLOYMENT.md.

CMD ["python", "main.py"]
