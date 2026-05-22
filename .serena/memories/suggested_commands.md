# Suggested Commands for Mintkey Development

## Running the full stack
```bash
docker compose up -d                        # start all 15 services
docker compose up -d --build                # rebuild and start
docker compose logs -f admin-api            # tail specific service logs
docker compose down -v                      # ⚠ DESTRUCTIVE — removes ALL 7 named volumes (postgres_data, vault_data, vault_kek, bootstrap_secrets, grafana_data, broker_wal, proxy_wal). Run `bash scripts/dev-backup.sh` first. See docs/operations/backup-before-reset.md (EV-DESTRUCTIVE-008).
docker compose run --rm liquibase           # run DB migrations manually
```

## Smoke test (end-to-end validation)
```bash
python3 scripts/e2e_smoke.py                # full smoke test
python3 scripts/e2e_smoke.py --no-twilio    # skip live Twilio call
SKIP_TWILIO=1 python3 scripts/e2e_smoke.py  # same via env var
```

## Python (admin-api / mcp-server)
```bash
# From admin-api/ directory:
pip install -r requirements.txt
pytest tests/unit/admin_api/ -v             # unit tests
pytest tests/architecture/ -v               # architecture tests (RLS, audit)
ruff check admin-api/src/                   # lint
ruff format admin-api/src/                  # format
mypy --strict admin-api/src/admin_api/      # type check

# Run admin-api locally:
PYTHONPATH=admin-api/src:mintkey-models uvicorn admin_api.main:app --reload --port 8080
```

## Go services
```bash
# From repo root (go.work workspace):
go test ./services/vault-adapter/...        # test vault-adapter
go test ./services/broker/...               # test broker
go test ./...                               # test all Go modules

# Build specific service:
cd services/vault-adapter && go build ./cmd/vault-adapter
```

## Admin UI
```bash
cd admin-ui
pnpm install
pnpm dev                                    # start dev server
pnpm test                                   # run vitest
pnpm build                                  # production build
```

## Contract validation
```bash
# OpenAPI
python3 -c "import yaml,openapi_spec_validator as v; v.validate(yaml.safe_load(open('docs/architecture/contracts/rest/openapi.yaml')))"
npx @redocly/cli lint docs/architecture/contracts/rest/openapi.yaml

# JSON Schema
python3 -c "import json; from jsonschema import Draft202012Validator as V; [V.check_schema(json.load(open(p))) for p in ['docs/architecture/contracts/events/audit-event.schema.json','docs/architecture/contracts/events/change-event.schema.json']]"
```

## Database
```bash
# Query postgres directly (from host):
docker exec mintkey-postgres-1 psql -U mintkey_migrate -d mintkey -c "SELECT * FROM tenants;"

# Read bootstrap admin password:
docker run --rm -v mintkey_bootstrap_secrets:/secrets alpine cat /secrets/admin_password
```

## Plaintext leak red-team
```bash
docker compose logs | grep -E "canary-demo-api-key|TWILIO_TOKEN"   # must be empty
```
