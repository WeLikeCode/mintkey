# Onboarding — Data / ML engineer

**Time:** ~2 hours, Day 1
**Outcome:** you can stand up a new worker stub, run it against fixtures, emit traces.

| # | File | Time |
|---|---|---|
| 1 | [BOOTSTRAP.md](../../BOOTSTRAP.md) | 15 min |
| 2 | `.kiro/steering/data-lifecycle-and-idempotency.md` | 20 min |
| 3 | `.kiro/steering/object-storage-conventions.md` (if Q11 included Object store) | 15 min |
| 4 | `.kiro/steering/database-conventions.md` | 15 min |
| 5 | `workers/README.md` + skim one worker entrypoint | 20 min |
| 6 | `.kiro/steering/observability-and-operations.md` | 15 min |
| 7 | `fixtures/README.md` (sample data) | 10 min |
| 8 | `.kiro/steering/security-and-tenancy.md` (tenant context in worker) | 15 min |

## Before you write a worker

- Confirm the worker has a contract for its inputs (`contracts/asyncapi/` or `contracts/jsonschema/`).
- Confirm idempotency: replaying the same input must produce no duplicate side effects. The data-lifecycle doc enforces this.
- Confirm tenant isolation: workers MUST validate tenant context against session ownership before writing — don't trust the payload blindly.

## Common Day-1 failure modes

- Worker that produces duplicate rows on replay (idempotency violation).
- Worker that connects as DB superuser instead of the role with appropriate GRANT.
- Worker that omits OpenTelemetry instrumentation — observability conventions require it.
- Worker that hardcodes credentials in source — config conventions require env-var injection.

## Sign in

```bash
cp team/_template/onboarded.md team/{your-handle}/onboarded.md
```
