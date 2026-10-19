#!/bin/sh
# The L4 test gate (gates.test in .l4/config.yaml): the test jobs of .github/workflows/ci.yml that the L4 job can run
# ("Python Unit Tests", "Acceptance Tests", "Go Unit Tests") and the admin-ui Vitest suite, in one run, one junit
# report per suite (every report is listed in gates.test.reports). Each Python project runs in its own uv
# environment, and --rootdir makes every test id relative to the repository root, which is how L4 finds a test's file.
# The Go modules run as ci.yml runs them (`go test ./... -short -timeout=120s`), through gotestsum for the report.
#
# Left out, because the L4 job cannot run them (the repository's own CI still does):
# - the tests that need a Docker daemon (testcontainers): the L4 gate sandbox hides the Docker socket.
# The ignores of the CI job "Acceptance Tests" (live stack, browser and render tests) are kept as they are.
R=$PWD
export MINTKEY_AUDIT_HMAC_KEY="${MINTKEY_AUDIT_HMAC_KEY:-0000000000000000000000000000000000000000000000000000000000000000}"
A="$R/tests/acceptance"
status=0

(cd apps/admin-api && uv run --frozen pytest -q -p no:cacheprovider --rootdir="$R" \
  --junitxml="$R/.l4-out/junit-admin-api.xml" \
  "$R/tests/unit/admin_api" "$A" \
  --ignore="$A/test_brokered_call.py" \
  --ignore="$A/test_rotation_propagation.py" \
  --ignore="$A/test_revocation_timing.py" \
  --ignore="$A/test_token_issuance_perf.py" \
  --ignore="$A/test_proxy_latency.py" \
  --ignore="$A/test_avail.py" \
  --ignore="$A/test_e2e_smoke.py" \
  --ignore="$A/test_e2e_trace.py" \
  --ignore="$A/test_mermaid_renders.py" \
  --ignore="$A/test_metrics.py" \
  --ignore="$A/test_grafana.py" \
  --ignore="$A/test_mock_backend_registered.py" \
  --ignore="$A/test_audit_append_only.py" \
  --ignore="$A/test_audit_chain.py") || status=1

(cd packages/python/mintkey-models && uv run --frozen pytest -q -p no:cacheprovider --rootdir="$R" \
  --junitxml="$R/.l4-out/junit-mintkey-models.xml" "$R/packages/python/mintkey-models/tests") || status=1

(cd apps/mcp-server && uv run --frozen pytest -q -p no:cacheprovider --rootdir="$R" \
  --junitxml="$R/.l4-out/junit-mcp-server.xml" "$R/apps/mcp-server/tests") || status=1

# the go.work modules, named as in gates.test.reports (a new module needs a line here and a report there)
for m in .:root apps/broker:broker apps/email-proxy:email-proxy apps/kong-syncer:kong-syncer \
  apps/proxy-plugin:proxy-plugin apps/ssh-proxy:ssh-proxy apps/vault-adapter:vault-adapter; do
  (cd "${m%%:*}" && "$R/.l4-out/bin/gotestsum" --format testname \
    --junitfile "$R/.l4-out/junit-go-${m##*:}.xml" -- ./... -short -timeout=120s) || status=1
done

# admin-ui's Vitest suite (ci.yml does not run it): both projects of vitest.workspace.ts, every file they include.
# --testTimeout=30000: the first dynamic import of an AdminJS resource takes seconds on a busy runner (Vitest's 5 s
# default timed out under load, and the tests after it in the file then saw no mock).
(cd apps/admin-ui && pnpm exec vitest run --reporter=default --reporter=junit --testTimeout=30000 \
    --outputFile.junit="$R/.l4-out/junit-admin-ui.xml") || status=1

exit $status
