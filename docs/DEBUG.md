# Debugging Mintkey

Mintkey is a layered system: request failures can originate in the egress proxy, the broker, the vault adapter, the admin API, or the underlying infrastructure. The correct approach is to start at the symptom, identify which layer owns it, then drill into that layer's logs and observability.

The canonical troubleshooting table for the developer quick-start scenario is [`docs/guides/github-quickstart.md` §8 — Failure modes](guides/github-quickstart.md#8-failure-modes). Read that table first. This document is the **systemic layer** that sits above it: it explains the full diagnostic sequence, covers all eight long-running services, and connects symptoms to the observability pipeline.

---

## Contents

1. [Stack-health check (Layer 1)](#layer-1-stack-health)
2. [Triage flowchart](#2-triage-flowchart)
3. [Readiness probe (Layer 2)](#layer-2-readiness-probe)
4. [Per-service diagnostics (Layer 3)](#layer-3-per-service-diagnostics)
5. [Observability (Layer 4)](#layer-4-observability)
6. [Red-team verification (Layer 5)](#layer-5-red-team-checks)
7. [Contract-drift detection (Layer 6)](#layer-6-contract-drift)
8. [Worked debug session — 401 from proxy](#9-worked-debug-session--401-from-proxy)
9. [When to escalate](#10-when-to-escalate)

---

## Layer 1: Stack health

Before any service-level debugging, confirm the whole stack is up.

```bash
docker compose ps
```

Every long-running service should show `Up (healthy)`. The two one-shot jobs (`liquibase`, `seed-job`) should show `Exited (0)`. Any other state is the first thing to investigate.

Quick-scan the unhealthy service's recent logs:

```bash
docker compose logs <service-name> --tail 100
```

The canonical service list with port assignments lives in [`PORTS.md`](../PORTS.md). There are **15 long-running containers + 2 one-shot jobs** = 17 services total (per `docker compose up -d` and `PROGRESS.md` §1.1).

> **Startup order matters.** `liquibase` must exit 0 before `seed-job` runs; `seed-job` must exit 0 before `admin-api` starts. A stuck `liquibase` blocks the entire control plane. Check with `docker compose logs liquibase`.

---

## 2. Triage flowchart

```mermaid
flowchart TD
    A([Symptom observed]) --> B{docker compose ps\nall healthy?}
    B -- No --> C[Check failing service logs\ndocker compose logs &lt;svc&gt; --tail 100]
    C --> D{One-shot jobs\nexited 0?}
    D -- No --> E[liquibase or seed-job failed\nCheck DB connectivity and\nchangelog conflicts]
    D -- Yes --> F[Service startup failure\nSee Layer 3 per-service table]
    B -- Yes --> G{HTTP symptom\n4xx or 5xx?}
    G -- 401 --> H[JWT expired or wrong service_id\nSee Layer 3: proxy-plugin and broker]
    G -- 403 --> I[Missing grant or permission_denied\nmintkey:code = permission_denied\nor permission_not_found\nSee Layer 3: mcp-server and admin-api]
    G -- 404 --> J[Route not synced or wrong service_id\nSee Layer 3: kong-syncer]
    G -- 429 --> K[Rate limit exceeded\nmintkey:code = rate_limited\nSee Layer 3: broker]
    G -- 502 --> L[Vault lookup failed or\ncredential row missing\nmintkey:code = vault_unavailable\nSee Layer 3: vault-adapter]
    G -- 503 --> M[Dependency not ready\ncurl localhost:8080/v1/ready\nSee Layer 2]
    G -- Other --> N[Check mintkey:trace_id\nin response body\nFind trace in Jaeger\nhttp://localhost:16686]
    H & I & J & K & L & M --> O{Still stuck?}
    N --> O
    O -- Yes --> P[Layer 4: Observability\nJaeger trace + Grafana]
    P --> Q{Contract or\nsecurity concern?}
    Q -- Contract --> R[Layer 6: make test-arch]
    Q -- Security --> S[Layer 5: red-team greps]
    Q -- Unresolved --> T[Escalate → docs/REPORTING.md]
```

---

## Layer 2: Readiness probe

The admin-api readiness endpoint reports which dependency is blocking it:

```bash
curl -s http://localhost:8080/v1/ready | jq .
```

A `503` body names the failing dependency (`db`, `liquibase`, `vault_adapter`, `change_channel`). This is the fastest way to distinguish infrastructure failure from application failure. The readiness behavior is specified in `.kiro/specs/mintkey-mvp/requirements.md` Req 1 AC 8.

---

## Layer 3: Per-service diagnostics

Each entry gives: container name (derived from `name: mintkey` in `docker-compose.yml` + service key), the two most common failure modes, the exact log invocation, and the relevant `mintkey:code` values where applicable.

---

### admin-api

| | |
|---|---|
| **Container** | `mintkey-admin-api-1` |
| **Stack** | Python / FastAPI |
| **Port** | `8080` |

**Top-2 failure modes:**

1. **Auth failure on write operations** — AdminJS UI writes go through an `AdminUiSignedRequest` JWT (Ed25519, signed by the admin-ui service key). A stale or missing key produces `mintkey:code: unauthenticated` or `mintkey:code: permission_denied`. See [`ADR-0019`](architecture/01-architecture/adr/0019-admin-ui-bff-and-write-auth.md) for the signing contract.
2. **DB / migration not ready** — if `liquibase` did not complete, `admin-api` refuses to start. The readiness probe (`/v1/ready`) returns `503` with `"db"` in the body.

```bash
docker compose logs mintkey-admin-api-1 --tail 100
docker compose logs mintkey-admin-api-1 | grep "mintkey:code"
```

Relevant codes: `mintkey:code: unauthenticated`, `mintkey:code: permission_denied`, `mintkey:code: validation_failed`, `mintkey:code: duplicate_resource`.

---

### mcp-server

| | |
|---|---|
| **Container** | `mintkey-mcp-server-1` |
| **Stack** | Python / FastAPI |
| **Port** | `8082` |

**Top-2 failure modes:**

1. **Missing agent grant** — the agent's API key exists but no grant covers the `call` action on the target service. Response: `mintkey:code: permission_denied` with `reason_code: permission_not_found`. This is the most common first-run failure; create the grant in the Admin UI → Agent → Permissions tab.
2. **Broker unreachable** — mcp-server proxies token requests to the broker. If `broker` is down, token issuance returns `5xx`. Check `docker compose ps mintkey-broker-1`.

```bash
docker compose logs mintkey-mcp-server-1 --tail 100
docker compose logs mintkey-mcp-server-1 | grep "mintkey:code"
```

Relevant codes: `mintkey:code: permission_denied`, `mintkey:code: unauthenticated`, `mintkey:code: rate_limited`.

---

### broker

| | |
|---|---|
| **Container** | `mintkey-broker-1` |
| **Stack** | Go |
| **Port** | `8083` |

**Top-2 failure modes:**

1. **`MINTKEY_BROKER_SERVICE_TOKEN` mismatch** — the broker validates the service token presented by the proxy-plugin and the mcp-server against `MINTKEY_BROKER_SERVICE_TOKEN` in its environment. A mismatch produces `403`. Verify all three services carry the same token value (see `docker-compose.yml`).
2. **JWT signing key not loaded** — the broker signs short-lived JWTs (60 s TTL, Ed25519). If the key material is absent at startup, every token-issuance request fails immediately. Check early startup lines for key-load errors.

```bash
docker compose logs mintkey-broker-1 --tail 100
docker compose logs mintkey-broker-1 | grep "mintkey:code"
```

Relevant codes: `mintkey:code: unauthenticated`, `mintkey:code: permission_denied`, `mintkey:code: token_expired`, `mintkey:code: token_revoked`.

---

### vault-adapter

| | |
|---|---|
| **Container** | `mintkey-vault-adapter-1` |
| **Stack** | Go |
| **Ports** | `8084` (gRPC), `8087` (HTTP) |

**Top-2 failure modes:**

1. **KEK not available** — the vault adapter encrypts credentials at rest using the Key Encryption Key (`MINTKEY_VAULT_KEK` env var in dev, or `MINTKEY_VAULT_KEK_FILE` in production). If the key is missing or malformed, the adapter refuses to start. All downstream services that depend on credential fetch will fail with `502`.
2. **SQLite write lock** — the vault backend (`vault.sqlite`) is single-writer (see [`OQ-003`](architecture/01-architecture/open-questions.md#oq-003--vault-adapter-horizontal-scaling-) for the Phase 2 scaling question). Concurrent init attempts can produce lock errors.

```bash
docker compose logs mintkey-vault-adapter-1 --tail 100
docker compose logs mintkey-vault-adapter-1 | grep "mintkey:code"
```

Relevant codes: `mintkey:code: vault_unavailable`, `mintkey:code: credential_not_found`, `mintkey:code: api_key_resolution_unavailable`.

---

### proxy-plugin

| | |
|---|---|
| **Container** | `mintkey-proxy-plugin-1` |
| **Stack** | Go (HTTP reverse proxy, port 8086; Kong routes through it) |
| **Port** | `8086` (plugin HTTP); agent traffic enters via Kong at `8000` |

**Top-2 failure modes:**

1. **JWT expired (60 s TTL)** — the short-lived token issued by the broker expires quickly. The proxy-plugin rejects it with `401`. Re-issue via `POST /v1/tools/request_token`. See [`docs/guides/github-quickstart.md` §8](guides/github-quickstart.md#8-failure-modes) rows 1 and 6.
2. **Credential row missing / vault lookup failed** — if the credential was not saved in the admin UI, the proxy-plugin cannot inject it and returns `502`. Verify the credential exists and vault-adapter is healthy. Relevant code: `mintkey:code: api_key_resolution_unavailable`.

```bash
docker compose logs mintkey-proxy-plugin-1 --tail 100
docker compose logs mintkey-proxy-plugin-1 | grep "mintkey:code"
```

Relevant codes: `mintkey:code: unauthenticated`, `mintkey:code: token_expired`, `mintkey:code: api_key_resolution_unavailable`, `mintkey:code: forbidden_destination`, `mintkey:code: api_key_invalid`, `mintkey:code: api_key_expired`, `mintkey:code: api_key_revoked`, `mintkey:code: api_key_wrong_service`, `mintkey:code: api_key_action_not_allowed`, `mintkey:code: api_key_constraint_failed`, `mintkey:code: api_key_policy_violation`.

---

### kong-syncer

| | |
|---|---|
| **Container** | `mintkey-kong-syncer-1` |
| **Stack** | Go |
| **Port** | `8085` |

**Top-2 failure modes:**

1. **Routes not yet published after service create** — kong-syncer listens for `mintkey:service` PostgreSQL NOTIFY events and publishes Kong declarative-config routes within ~300 ms. If a service was just created and Kong returns `404`, wait 30 s for the initial reconcile, then verify: `docker compose logs mintkey-kong-syncer-1 | grep routes_published`.
2. **Wire-ID encoding mismatch** — if the `svc_` ULID from admin-api does not round-trip correctly through the Kong-syncer Go wire-ID encoder, routes will not match. The reference test is `services/kong-syncer/internal/wireids/encode_test.go`.

```bash
docker compose logs mintkey-kong-syncer-1 --tail 100
docker compose logs mintkey-kong-syncer-1 | grep routes_published
```

No `mintkey:code` values are emitted directly by kong-syncer (it is not on the request path); Kong `404` errors are the symptom. Verify route publication in the logs above.

---

### admin-ui

| | |
|---|---|
| **Container** | `mintkey-admin-ui-1` |
| **Stack** | TypeScript / Node.js (AdminJS) |
| **Port** | `8081` |

**Top-2 failure modes:**

1. **Session cookie not relayed / CSRF failure** — all AdminJS writes are forwarded to admin-api with an `AdminUiSignedRequest` JWT (see [`ADR-0019`](architecture/01-architecture/adr/0019-admin-ui-bff-and-write-auth.md)). A session that doesn't carry a valid signed JWT produces `unauthenticated` in admin-api. Check that `ADMIN_UI_PRIVATE_KEY_PATH` correctly resolves to the bootstrap private key.
2. **Resource adapter 404** — AdminJS's resource adapters call admin-api REST endpoints. If an endpoint is missing or mis-routed (e.g., after a contract change), the UI renders a blank form or throws. Check the admin-api logs for `404` responses from the adapter's perspective.

```bash
docker compose logs mintkey-admin-ui-1 --tail 100
docker compose logs mintkey-admin-ui-1 | grep "error\|Error"
```

AdminJS errors surface in the browser console and in the server log. The admin-api log will carry any `mintkey:code` value from the rejected request.

---

### kong

| | |
|---|---|
| **Container** | `mintkey-kong-1` |
| **Stack** | Kong 3.6 (DB-less) |
| **Ports** | `8000` (proxy), `8001` (admin) |

**Top-2 failure modes:**

1. **`404 no Route matched`** — kong-syncer has not yet published the route, or the `svc_` ID in the URL does not match a registered route. Wait for initial reconcile (~30 s after stack start) and check `docker compose logs mintkey-kong-syncer-1 | grep routes_published`.
2. **Plugin crash / unhealthy** — Kong reports `kong health || exit 1` in its health-check. If the proxy-plugin HTTP backend at `localhost:8086` is unreachable, Kong will return `502` for all proxied requests.

```bash
docker compose logs mintkey-kong-1 --tail 100
docker compose logs mintkey-kong-1 | grep "error\|ERR"
```

---

## Layer 4: Observability

### Jaeger (distributed traces)

Open [http://localhost:16686](http://localhost:16686). From the **Service** dropdown select `admin-api` or `mcp-server`. Every RFC 7807 error response carries a `mintkey:trace_id` extension member — find the trace by that ID in the Jaeger UI.

The `mintkey:trace_id` is defined in [`openapi.yaml`](architecture/contracts/rest/openapi.yaml) `info.description` lines 40–53 as the OTel trace ID of the failing request, formatted as a 32-hex-char W3C `traceparent` trace-id segment.

```bash
# Example: extract trace_id from a 4xx response body
curl -s http://localhost:8080/v1/tenants/bad-id/services | jq '."mintkey:trace_id"'
```

### Grafana (metrics dashboards)

Open [http://localhost:3003](http://localhost:3003) (admin / admin by default; see [`docs/guides/github-quickstart.md` §9](guides/github-quickstart.md#9-observability--verify-its-working) for the reset procedure). Dashboards show per-service request rates, error rates, and latency percentiles.

Prometheus is accessible only within the Docker network; query it through Grafana, not directly.

---

## Layer 5: Red-team checks

When debugging a potential security or data-isolation issue, run these verification commands (from `CLAUDE.md` "Verification commands"):

**Plaintext credential in logs:**

```bash
# Replace <fingerprint> with first 8 chars of the actual credential value
grep -rn "<fingerprint>" $(docker compose logs 2>&1)
```

Zero matches required. Any match is a `S-SEC-1` violation — file immediately via [`docs/REPORTING.md`](REPORTING.md) with label `security` (or privately via [`SECURITY.md`](../SECURITY.md) if the credential is real).

**Audit chain integrity:**

```bash
curl -s -X POST http://localhost:8080/v1/admin/audit/verify-chain \
  -H "X-Platform-Admin: true" \
  -H "Content-Type: application/json" \
  -d '{"tenant_id": "<tnt_id>"}' | jq .
```

Per `QUICKSTART.md` §9.

**RLS coverage:**

```bash
# Ensure every domain table has a tenant_isolation RLS policy
psql postgresql://mintkey_app:mintkey_app_password@localhost:5432/mintkey \
  -c "SELECT tablename, policyname, qual FROM pg_policies WHERE policyname = 'tenant_isolation';"
```

Per `CLAUDE.md` lines 210–213: every domain table must have a policy whose `qual` references `current_setting('app.current_tenant')`.

---

## Layer 6: Contract drift

If per-service debugging hasn't found the root cause, the running code may have drifted from the canonical contracts. Run:

```bash
make test-arch
```

This executes:
- **OpenAPI parity check** — asserts every route and schema in `docs/architecture/contracts/rest/openapi.yaml` matches what the running service implements.
- **SQLAlchemy mirror diff** — asserts the ORM models mirror the Liquibase-managed schema (per [`ADR-0015`](architecture/01-architecture/adr/0015-liquibase-schema-source-of-truth.md)).

Contract-drift failures are a **unique failure class**. They indicate the implementation diverged from the canonical spec. The fix is always to align the code to the spec — never to update the spec to match the code. The contracts are the source of truth.

If `make test-arch` fails in a way that looks like the spec is wrong (not the code), that is an architectural open question. Add it to [`docs/architecture/01-architecture/open-questions.md`](architecture/01-architecture/open-questions.md) as `OQ-NNN` (per `CLAUDE.md` Principle 2).

---

## 9. Worked debug session — 401 from proxy

**Scenario:** an agent calls the GitHub service through the egress proxy and receives `401`.

The failure-mode matrix in [`docs/guides/github-quickstart.md` §8](guides/github-quickstart.md#8-failure-modes) lists four root causes for `401 from proxy`. Work through them in this order:

**Step 1 — Is the JWT expired?**

The broker issues short-lived tokens with a 60-second TTL ([`ADR-0006`](architecture/01-architecture/adr/0006-token-format-and-binding.md)). Re-issue the token via `POST /v1/tools/request_token` and retry immediately. If the `401` disappears, this was the cause.

```bash
docker compose logs mintkey-proxy-plugin-1 --tail 50
# Look for: "token expired" or mintkey:code: token_expired
```

**Step 2 — Is the `service_id` in the URL correct?**

The proxy URL form is `http://localhost:8000/v1/call/<service_id>/...`. An incorrect `service_id` produces `401` (the proxy cannot look up the credential row). Verify the canonical ID:

```bash
curl -s http://localhost:8082/v1/tools/list_services \
  -H "Authorization: Bearer $AGENT_KEY" | jq '.[].id'
```

Compare against the ID in the failing request URL. See [`docs/guides/github-quickstart.md` §8](guides/github-quickstart.md#8-failure-modes) row "404 `service_not_found`" for the equivalent lookup step.

**Step 3 — Is the grant missing?**

A missing agent → service → `call` grant produces `403` (not `401`), but if the proxy-plugin checks the grant before the JWT, you may see `403` with `mintkey:code: permission_denied` and `reason_code: permission_not_found`. Consult the matrix in [`docs/guides/github-quickstart.md` §8](guides/github-quickstart.md#8-failure-modes) row **403**.

```bash
docker compose logs mintkey-admin-api-1 --tail 50
# Look for: token.denied in audit_events
```

**Step 4 — Is the credential row missing?**

If the credential was not saved in the Admin UI, the vault adapter returns `credential_not_found`, which surfaces at the proxy as `502` (not `401`). But if the credential row is present but the vault adapter is down, the proxy-plugin may degrade to `401` depending on its error-handling path.

```bash
docker compose logs mintkey-vault-adapter-1 --tail 50
# Look for: vault_unavailable or KEK errors
docker compose logs mintkey-proxy-plugin-1 --tail 50
# Correlate by mintkey:trace_id
```

**Correlate via trace:** extract `mintkey:trace_id` from the error response body and open [http://localhost:16686](http://localhost:16686) — search by that trace ID to see the full call chain across proxy-plugin, broker, and vault-adapter in one view.

**If none of Steps 1–4 resolves the issue**, the failure mode is not in the canonical table. This is itself a bug. File it via [`docs/REPORTING.md`](REPORTING.md).

---

## 10. When to escalate

Escalate to [`docs/REPORTING.md`](REPORTING.md) when:

- Your debugging identifies a reproducible failure not covered by [`docs/guides/github-quickstart.md` §8](guides/github-quickstart.md#8-failure-modes).
- A `mintkey:code` value appears in logs that is **not listed in [`docs/architecture/contracts/rest/openapi.yaml`](architecture/contracts/rest/openapi.yaml) `x-mintkey-error-codes`**. An unlisted code is itself a contract violation — file it as a bug.
- `make test-arch` fails in a way that appears to be a spec defect rather than a code defect.
- A red-team check in Layer 5 finds a plaintext credential in a log, audit payload, or span attribute — this is a security report and goes to [`SECURITY.md`](../SECURITY.md) directly, not Issues.

The full list of canonical `mintkey:code` values is the `x-mintkey-error-codes` block at the bottom of [`docs/architecture/contracts/rest/openapi.yaml`](architecture/contracts/rest/openapi.yaml).

---

## 11. Stack not running

**Symptom:** `make smoke`, direct API calls, or the demo script fail immediately with
`Connection refused` on ports 8080–8082 or `8000`.

**Diagnostic commands:**

1. Check whether Docker itself is running:
   ```bash
   docker info
   ```
   If this fails with `Cannot connect to the Docker daemon`, Docker Desktop (or the
   Docker daemon) is not started.

2. Check which containers are up:
   ```bash
   docker compose ps
   ```
   If the output is empty or every service shows `Exit`, the stack is not running.

3. Check for port conflicts:
   ```bash
   lsof -i :8080 -i :8081 -i :8082 -i :8000 2>/dev/null | head -20
   ```

**Resolution steps:**

1. Start Docker Desktop (or `sudo systemctl start docker` on Linux) and wait for it to
   report healthy.
2. Start the Mintkey stack:
   ```bash
   make demo
   ```
   `make demo` includes a 180-second health-check loop — it will print the admin URL
   and bootstrap password once all services are healthy.
3. If port conflicts exist, stop the conflicting process or change the ports in
   `docker-compose.yml` (and update `PORTS.md` accordingly).
4. If the stack is partially up (some containers healthy, some not), check the
   unhealthy service logs:
   ```bash
   docker compose logs <service-name> --tail 100
   ```

---

## 12. Bootstrap password / KEK mismatch

**Symptom:** admin-ui login returns `401`; admin-api logs contain `InvalidToken`,
`Fernet`, or `decryption error`; seed-job logs show a key-derivation or decryption
failure.

**Diagnostic commands:**

1. Compare the `MINTKEY_BOOTSTRAP_KEK` value used by each service:
   ```bash
   docker compose exec admin-api  env | grep KEK
   docker compose exec admin-ui   env | grep KEK
   docker compose exec seed-job   env | grep KEK 2>/dev/null || true
   ```
   All three must match exactly (same base64url string, same length).

2. Check for decryption errors in logs:
   ```bash
   docker compose logs mintkey-admin-api-1 | grep -i "kek\|fernet\|decrypt\|InvalidToken"
   docker compose logs mintkey-seed-job-1  | grep -i "kek\|fernet\|decrypt\|InvalidToken"
   ```

3. Verify the `.env` file KEK value:
   ```bash
   grep MINTKEY_BOOTSTRAP_KEK .env 2>/dev/null | head -1 | cut -c1-50
   ```

**Resolution steps:**

1. Ensure every service in `docker-compose.yml` and `.env` references the **same**
   `MINTKEY_BOOTSTRAP_KEK` value. A common cause of drift is editing `.env` after the
   stack has been started, so only some containers pick up the new value.
2. After correcting the KEK, restart all services to re-sync:
   ```bash
   docker compose down && docker compose up -d
   ```
   **IMPORTANT:** run `bash scripts/dev-backup.sh` before `docker compose down` if you
   have hand-curated state you want to preserve.
3. If the bootstrap password itself is corrupted, regenerate it via Option B in
   `docs/AUTH.md`:
   ```bash
   bash scripts/dev-backup.sh   # back up first
   docker compose down
   rm data/bootstrap-secrets/.admin_password_synced
   docker compose up -d
   ```
4. See [`docs/operations/backup-before-reset.md`](../docs/operations/backup-before-reset.md)
   for the full backup/restore guide.

---

## 13. oauth2-proxy / Jaeger auth issues

**Symptom:** Opening `http://localhost:16686` (Jaeger UI) redirects to a Keycloak
login page, then back to Jaeger, then to login again (redirect loop); or `403 Forbidden`
appears after a seemingly successful login.

**Diagnostic commands:**

1. Check the jaeger-auth (oauth2-proxy) container logs for errors:
   ```bash
   docker compose logs mintkey-jaeger-auth-1 --tail 100
   ```
   Look for `cookie_secret`, `invalid session`, `CSRF token mismatch`, or Keycloak
   connectivity errors.

2. Verify the cookie secret length (must be 16, 24, or 32 bytes after base64 decode):
   ```bash
   docker compose exec mintkey-jaeger-auth-1 env | grep OAUTH2_PROXY_COOKIE_SECRET
   ```

3. Check whether the Keycloak realm and OIDC client exist:
   ```bash
   docker compose logs mintkey-seed-job-1 | grep -i "jaeger\|oidc\|realm\|keycloak"
   ```

4. Confirm Keycloak is healthy:
   ```bash
   curl -sf http://localhost:8888/health/ready | jq .
   ```

**Resolution steps:**

1. If the cookie secret is missing or has wrong length, regenerate it via the seed-job.
   The seed-job writes a correctly-sized secret to `bootstrap_secrets` volume on first
   run. Restart the seed-job:
   ```bash
   docker compose restart mintkey-seed-job-1
   docker compose restart mintkey-jaeger-auth-1
   ```
2. If Keycloak has not seeded the Jaeger OIDC client yet, wait for the seed-job to
   complete (`docker compose logs mintkey-seed-job-1 | tail -20`) and then restart
   jaeger-auth.
3. If a redirect loop persists after the above, clear browser cookies for
   `localhost:16686` and try again — stale oauth2-proxy session cookies can cause loops.
4. See `docker-compose.yml` `jaeger-auth` service section for the full oauth2-proxy
   configuration and environment variables.

---

## 14. `make smoke` failures

**Symptom:** `make smoke` exits non-zero; test output shows assertion errors or
connection errors.

Common root causes and resolution per each:

**1. Stack not healthy yet**

`make smoke` runs immediately after `make demo` finishes, but some services may still be
initialising. Diagnostic:

```bash
docker compose ps
# Look for any service not showing "healthy"
docker compose logs mintkey-liquibase-1 --tail 30
docker compose logs mintkey-seed-job-1  --tail 30
```

Resolution: wait 30–60 seconds for one-shot jobs (`liquibase`, `seed-job`) to complete,
then re-run `make smoke`.

**2. Port conflicts on 8080–8082**

Another process holds one of the Mintkey ports. Diagnostic:

```bash
lsof -i :8080 -i :8081 -i :8082 -i :8000 2>/dev/null | grep LISTEN
```

Resolution: stop the conflicting process or reconfigure the port in `docker-compose.yml`
and `.env`.

**3. PostgreSQL connection failures**

admin-api returns `503` with `"db"` in the readiness body. Diagnostic:

```bash
curl -s http://localhost:8080/v1/ready | jq .
docker compose logs mintkey-postgres-1 --tail 50
```

Resolution: if postgres is not healthy, `docker compose restart mintkey-postgres-1`.
If liquibase failed, check its logs for migration errors:
```bash
docker compose logs mintkey-liquibase-1 | grep -i "error\|FAILED"
```

**4. Stale state from a previous run**

A previous test run left agents, services, or audit rows that conflict with the smoke
test's assumptions. Resolution:

```bash
bash scripts/dev-backup.sh      # back up first
docker compose down
docker compose up -d
make smoke
```

---

## 15. Backup before reset

**Symptom:** You are about to run `docker compose down -v` (or any other volume-
destructive operation) and want to preserve your hand-curated agents, services,
permission grants, and audit rows.

**Resolution — ALWAYS run the backup script first:**

```bash
bash scripts/dev-backup.sh
```

This dumps PostgreSQL data, snapshots vault and KEK volumes, and copies `.env` with
secret values redacted. Output is written to `.mintkey-backups/<ISO-timestamp>/`
(gitignored).

For the full backup/restore guide, including the restore command, KEK considerations,
and cron automation, see:

```
docs/operations/backup-before-reset.md
```

Key rules:
- **Never** run `docker compose down -v` without a backup.
- **Never** change `MINTKEY_VAULT_KEK` or `MINTKEY_BOOTSTRAP_KEK` without first backing
  up — a KEK change makes previous encrypted backups unrestorable without the old key.
- Use `bash scripts/dev-restore.sh .mintkey-backups/<timestamp> --dry-run` to preview a
  restore before applying it.

---

## 16. MCP config mismatch

**Symptom:** An MCP client (e.g., Claude Code, a custom agent) receives `401
Unauthorized` on every call to the Mintkey MCP server, or reports that the `mintkey`
tools are not found / the tool schema version is unsupported.

**Diagnostic commands:**

1. Check the MCP server URL and key configured in your MCP client:
   ```bash
   claude mcp get mintkey
   ```
   This prints the URL and any configured headers.

2. Check the live MCP server URL:
   ```bash
   curl -s http://localhost:8082/v1/health | jq .
   ```
   The MCP server should respond with `{"status": "ok"}`. If it's not reachable,
   the stack is not running (see §11).

3. Verify the tool schema version reported by the server:
   ```bash
   curl -s http://localhost:8082/v1/tools | jq '.schema_version // "unknown"'
   ```
   Compare against the version in `docs/architecture/contracts/mcp/tools.yaml`.

4. Check MCP server logs for auth failures:
   ```bash
   docker compose logs mintkey-mcp-server-1 --tail 50 | grep -i "401\|auth\|key\|invalid"
   ```

**Resolution steps:**

1. If the URL is wrong, remove and re-add the Mintkey MCP server in your client:
   ```bash
   claude mcp remove mintkey
   claude mcp add --transport http mintkey http://localhost:8082/mcp \
     --header "Authorization: Bearer mk_agent_YOUR_AGENT_KEY_HERE"
   ```
   Replace `mk_agent_YOUR_AGENT_KEY_HERE` with the actual agent key from admin UI.

2. If the agent key has been rotated (e.g., via admin UI → Agents → Rotate Key), update
   the MCP client config with the new key using `claude mcp remove` + `claude mcp add`.

3. If the tool schema version is mismatched, pull the latest repo and restart the stack:
   ```bash
   git pull
   docker compose pull
   docker compose up -d
   ```

4. Verify the corrected config resolves the issue:
   ```bash
   curl -s http://localhost:8082/v1/tools/list_services \
     -H "Authorization: Bearer mk_agent_YOUR_AGENT_KEY_HERE" | jq '.[].name'
   ```
   A `200` response listing services confirms the key and URL are correct.
