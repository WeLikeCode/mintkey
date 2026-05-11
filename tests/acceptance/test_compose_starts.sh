#!/usr/bin/env bash
# T-1.0.10 acceptance test: all containers start and pass health checks within 120s.
# Source: Req 1 AC1, design §11.
set -euo pipefail

docker compose up -d --build

TIMEOUT=120
SERVICES=("admin-api:8080" "broker:8083" "vault-adapter:8084")

for svc_port in "${SERVICES[@]}"; do
  IFS=: read -r svc port <<< "$svc_port"
  echo "Waiting for $svc on port $port..."
  for i in $(seq 1 $TIMEOUT); do
    if curl -sf "http://localhost:$port/v1/health" > /dev/null 2>&1; then
      echo "$svc healthy"
      break
    fi
    sleep 1
    if [ "$i" -eq "$TIMEOUT" ]; then
      echo "FAIL: $svc not healthy after ${TIMEOUT}s"
      docker compose logs "$svc" | tail -20
      exit 1
    fi
  done
done

# Assert one-shot jobs exited 0
for job in liquibase seed-job; do
  STATUS=$(docker compose ps --status exited "$job" --format json | python3 -c "import sys,json; data=json.load(sys.stdin); print(data.get('ExitCode', 1))" 2>/dev/null || echo "1")
  if [ "$STATUS" != "0" ]; then
    echo "FAIL: $job did not exit 0 (exit code: $STATUS)"
    exit 1
  fi
done

echo "All containers healthy. T-1.0.10 PASS."
