# admin-ui Playwright e2e

Browser tests for the AdminJS operator UI (`tests/`), driven through the real Keycloak OIDC login
(`global-setup.ts`) against a real Mintkey stack. Nothing is mocked.

## Which stack does it hit?

Only the one you name. There are no `localhost:8081` / `localhost:8080` fallbacks any more
(`env.ts` is the single place that resolves them):

| variable | meaning |
|---|---|
| `PLAYWRIGHT_BASE_URL` | admin-ui origin of the stack under test, **required** |
| `ADMIN_API_URL` | admin-api origin of the same stack, required unless the admin-ui is the default `http://localhost:8081` |
| `PLAYWRIGHT_USER` / `PLAYWRIGHT_PASS` | the bootstrap operator; the password is Fernet-encrypted in `bootstrap-secrets/admin_password` |
| `PLAYWRIGHT_TENANT_ID` | the `t_default` tenant id of that stack |

`CI=true` or `E2E_ALLOW_DEFAULT_STACK=1` re-enable the 8081/8080 defaults (the GitHub workflow starts a
throw-away stack on exactly those ports). On a developer machine those ports are normally the live stack,
so do not set either there.

API-driven fixtures (`fixtures/test-data.ts`, several specs) reuse the OIDC session that `global-setup.ts`
stored in `state.json`; `/v1/auth/internal-login` answers 404 for the OIDC-provisioned bootstrap operator.
Specs create the data they assert on (services, agents, grants) and do not depend on rows that only exist
in a long-lived dev database.

## One command: Playwright + the stack-based Python tests, isolated

```sh
export E2E_PROJECT=mintkey-e2e        # required; `mintkey` and `mintkey-test` are refused
make e2e-isolated-up                  # build + start the project on its own ports/images/volumes
make e2e-isolated-test                # Playwright (chromium) + smoke + test-integration set + golden path + data-plane
make e2e-isolated-down                # down --volumes
```

Knobs: `E2E_BROWSERS="chromium firefox webkit"`, `E2E_SUITES="playwright smoke integration golden data-plane"`,
`E2E_PORT_*` (see `infra/compose/docker-compose.e2e.yml`; default is the +300 set: admin-ui 8381, admin-api 8380,
mcp 8382, kong 8300, keycloak 8643, ...). Install browsers once with
`pnpm exec playwright install chromium firefox webkit`.

What `tools/e2e-isolated.sh` guards against:

* the compose project is passed as `-p` and exported as `COMPOSE_PROJECT_NAME`, which outranks the `name: mintkey`
  in `docker-compose.yml`. The Python tests shell out to compose without `-p`
  (`test_e2e_smoke.py` teardown runs `docker compose exec postgres ... DELETE`, `test_data_plane_resilience.py`
  runs `docker compose pause vault-adapter`); without this they would act on the live project;
* before `up` the resolved config is checked: no `container_name`, every built image is `<project>-<service>`
  (never the shared `mintkey-<service>` tags), volumes and network are scoped to the project, no host port from
  the primary (8000-8092, 8443, 8999, 3003, 16686, 4317, 2222) or +100 test-namespace set, and the seed-job's host
  bind is not the checkout's `data/bootstrap-secrets` (it holds the live stack's admin password mirror);
* variables exported in your shell (`MINTKEY_*`, `COMPOSE_*`, `KC_*`, anything the compose files interpolate) are
  unset first: for docker compose an exported variable beats `--env-file`, so e.g. a stray
  `MINTKEY_KEYCLOAK_PUBLIC_URL` would repoint the isolated stack at the live one;
* each port is checked individually and must be free or published by this project;
* all test URLs are derived from the same port variables, so no test can fall back to a default port.

Do not use `make smoke`, `make test-golden` or `make test-data-plane*` for this: they look for "the stack" with
`docker compose ps` in the checkout and use the default ports.

Other tests in `tests/acceptance/` hard-code the live stack's container names (`mintkey-postgres-1`,
`mintkey-admin-api-1`); never run the whole directory with `MINTKEY_INTEGRATION_TEST=true`.

## Cleanup

Fixtures record what they create in `e2e/.cleanup.<E2E_PROJECT|default>.ndjson` (`fixtures/cleanup.ts`); `global-teardown.ts` deletes it
(LIFO) with the OIDC session saved in `state.json`. Entities that cannot be hard-deleted (e.g. a service with a
credential) are reported, not fatal.

The `compose` helper refuses `-p/--project-name`, `-f/--file`, `--env-file` and `--project-directory` anywhere in its
arguments (so use `logs --follow`, `run --publish`); guard tests: `make test-e2e-tools`.

Helpers: `tools/e2e-isolated.sh pw <playwright args>`, `py <pytest args>` and `compose <docker compose args>` run with the
isolated stack's environment / project.

## CI

`.github/workflows/playwright.yml`: PRs run chromium (30 min), the nightly schedule runs chromium, firefox and
webkit (60 min), and `workflow_dispatch` runs the same all-browsers matrix on demand (the schedule trigger cannot be exercised from a branch). Known webkit skips are listed in `COVERAGE.md`.
