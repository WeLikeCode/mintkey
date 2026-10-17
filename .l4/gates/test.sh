#!/bin/sh
# The L4 test gate (gates.test in .l4/config.yaml): the Python test jobs of .github/workflows/ci.yml ("Python Unit
# Tests" and "Acceptance Tests") in one run. Each project runs in its own uv environment, and --rootdir makes every
# test id relative to the repository root, which is how L4 finds a test's file.
#
# Left out, because the L4 job cannot run them (the repository's own CI still does):
# - the tests that need a Docker daemon (testcontainers): the L4 gate sandbox hides the Docker socket;
# - the tests that run the Go toolchain: the L4 job has no `go` on PATH.
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
  --ignore="$A/test_audit_chain.py" \
  --deselect=tests/acceptance/test_async_audit_emission.py::test_auditq_unit_tests_pass \
  --deselect=tests/acceptance/test_budget_enforcement.py::test_proxy_budget_check_returns_429_on_exhaustion \
  --deselect=tests/acceptance/test_budget_period_rollover.py::test_proxy_period_tests_pass \
  --deselect=tests/acceptance/test_cross_tenant_token.py::test_verifier_rejects_wrong_tenant) || status=1

(cd packages/python/mintkey-models && uv run --frozen pytest -q -p no:cacheprovider --rootdir="$R" \
  --junitxml="$R/.l4-out/junit-mintkey-models.xml" "$R/packages/python/mintkey-models/tests") || status=1

(cd apps/mcp-server && uv run --frozen pytest -q -p no:cacheprovider --rootdir="$R" \
  --junitxml="$R/.l4-out/junit-mcp-server.xml" "$R/apps/mcp-server/tests") || status=1

exit $status
