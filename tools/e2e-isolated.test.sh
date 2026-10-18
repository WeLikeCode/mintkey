#!/usr/bin/env bash
# Tests for the guards in tools/e2e-isolated.sh. Uses a stub `docker` first on PATH that only records its
# arguments, so no real docker (and no real compose project) is ever touched.
#   tools/e2e-isolated.test.sh        (also: make test-e2e-tools)
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPT="$ROOT/tools/e2e-isolated.sh"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
mkdir -p "$TMP/bin" "$TMP/state"
cat > "$TMP/bin/docker" <<'STUB'
#!/usr/bin/env bash
echo "$*" >> "$DOCKER_LOG"
if [[ " $* " == *" config "* ]]; then
  echo '{"name":"mintkey-e2e","services":{},"volumes":{},"networks":{}}'
fi
exit 0
STUB
chmod +x "$TMP/bin/docker"
export DOCKER_LOG="$TMP/docker.log"
fails=0

run() { : > "$DOCKER_LOG"; PATH="$TMP/bin:$PATH" E2E_PROJECT="${PROJ-mintkey-e2e}" E2E_STATE_DIR="$TMP/state" "$SCRIPT" "$@" 2>&1; }

expect_refused() {
  local out rc
  out="$(run compose "$@")"; rc=$?
  if [ "$rc" -ne 2 ] || [ -s "$DOCKER_LOG" ] || ! grep -q "refusing" <<<"$out"; then
    echo "FAIL: compose $* was not refused cleanly (rc=$rc, docker calls: $(wc -l < "$DOCKER_LOG"))"; echo "$out"; fails=$((fails+1))
  else
    echo "ok: compose $* refused, docker not called"
  fi
}

for args in \
  "-p mintkey ps" "-pmintkey ps" "-p=mintkey ps" "--project-name mintkey-test ps" "--project-name=mintkey-test ps" \
  "-f other.yml ps" "-fother.yml ps" "--file other.yml ps" "--file=other.yml ps" \
  "--env-file x ps" "--env-file=x ps" "--project-directory /tmp ps" "--project-directory=/tmp ps" \
  "ps -p mintkey" "--profile x -p mintkey ps" "down -v --project-name=mintkey"; do
  # shellcheck disable=SC2086
  expect_refused $args
done

# project names that are the live / test-namespace stacks are refused before anything runs
for p in mintkey mintkey-test; do
  out="$(PROJ=$p run check)"; rc=$?
  if [ "$rc" -ne 2 ] || [ -s "$DOCKER_LOG" ]; then echo "FAIL: project $p accepted (rc=$rc)"; fails=$((fails+1)); else echo "ok: E2E_PROJECT=$p refused"; fi
done
out="$(PROJ= run check)"; rc=$?
if [ "$rc" -ne 2 ]; then echo "FAIL: empty E2E_PROJECT accepted"; fails=$((fails+1)); else echo "ok: empty E2E_PROJECT refused"; fi

# positive control: an allowed passthrough reaches docker, scoped to the isolated project
out="$(run compose ps -a)"; rc=$?
if [ "$rc" -ne 0 ] || ! grep -q -- "-p mintkey-e2e .* ps -a" "$DOCKER_LOG"; then
  echo "FAIL: 'compose ps -a' did not reach docker as -p mintkey-e2e (rc=$rc)"; cat "$DOCKER_LOG"; echo "$out"; fails=$((fails+1))
else
  echo "ok: 'compose ps -a' runs as -p mintkey-e2e"
fi

[ "$fails" -eq 0 ] && echo "all e2e-isolated guard tests passed" || { echo "$fails guard test(s) failed"; exit 1; }
