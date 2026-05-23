# Integration Tests Timeout — Closing Report

**Session:** `2026-05-17-integration-tests-timeout`
**Status:** CLOSED
**Closed by:** IMPLEMENTER INTEGRATION-FIX

---

## Summary

The CI `Integration Tests` job's "Start stack" step was timing out at 120 s because
`docker compose up -d` triggers inline builds for 10 services (seed-job, vault-adapter,
admin-api, admin-ui, mcp-server, broker, kong-syncer, proxy-plugin, mock-backend, jaeger-auth)
before any container can enter `running` state. On cold CI cache that build phase alone exceeds
3-10 minutes. The fix splits the step into two: `Build stack images` (`docker compose build`,
no timeout — covered by the GitHub Actions job-level timeout) followed by `Start stack`
(`docker compose up -d` with a 180 s wait-loop that now only times the startup phase). A
`Capture container logs` + `Upload container logs` step pair was also added (runs only on
failure) to aid future debugging. YAML validated cleanly.

---

## Verification commands and exit codes

```
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml')); print('YAML OK')"
exit code: 0 (output: YAML OK)
```

Structural checks:
- `test-integration` job contains `Build stack images` step before `Start stack`: confirmed.
- wait-loop timeout is 180 s (was 120 s): confirmed.
- `Capture container logs` and `Upload container logs` steps present with `if: failure()`: confirmed.

---

## Chunks completed

| Chunk | Commit | Reviewer verdict | Rounds |
|---|---|---|---|
| C-1: scaffold + intake | see git log | PASS | 1 |
| C-2: split docker compose build/start + extend wait timeout | see git log | PASS | 1 |
| C-3: close session | see git log | PASS | 1 |

---

## DoD checklist — final state

- [x] `test-integration` job has separate `Build stack images` step before `Start stack` — verified via grep + YAML parse
- [x] wait-loop timeout extended from 120 s to 180 s — verified by reading ci.yml:227
- [x] YAML validates — `python3 -c "import yaml; yaml.safe_load(...)"` exits 0
- [x] No Co-Authored-By trailer in any new commit
- [x] No --no-verify used

---

## Residual risks / deferred items

- The `upload-artifact@v4` action used in the log-capture step may need a pinned SHA in
  environments that enforce strict action pinning (like the rest of this workflow). Deferred
  as a P3 — does not affect correctness and can be pinned in a follow-up.
- Option C (pre-built registry images) would reduce CI build time further but requires
  significant infrastructure change. Deferred as out of scope.

---

## Escalation resolutions

None.

---

## Lessons learned / notes for next session

- Always separate `docker compose build` from `docker compose up -d` in CI workflows that have
  services with `build:` directives. The build phase is long and unpredictable; mixing it with
  the health-check wait-loop causes false timeouts.
- The 10 build-directive services in docker-compose.yml are the primary reason CI cold-cache
  runs take so long. If CI build times remain problematic, investigate layer caching with
  `actions/cache` for Docker build layers or migration to pre-built registry images.
