# otel-collector spanmetrics config fix — Closing Report

**Session:** `2026-05-17-otel-collector-config`
**Status:** CLOSED
**Closed by:** IMPLEMENTER OTEL-CONFIG

---

## Summary

Removed the invalid `include:` top-level key from `connectors.spanmetrics` (not valid in otel-collector-contrib v0.104.0). Replaced the span-name filter with a dedicated `filter/spanmetrics_input` processor using OTTL (`name != "mintkey.proxy.handle_request"`), wired into a new `traces/spanmetrics_input` pipeline. The main traces pipeline now exports to Jaeger+debug only (no double-counting); the filtered pipeline feeds the spanmetrics connector exclusively. Config validated with `docker run … validate` — exit code 0.

---

## Verification commands and exit codes

```
docker run --rm \
  -v "/Users/alexandruiacobescu/gooseProjects/mintkey/otel-collector-config.yaml:/etc/otelcol-contrib/config.yaml" \
  otel/opentelemetry-collector-contrib:0.104.0 \
  validate --config=/etc/otelcol-contrib/config.yaml
exit code: 0
```

---

## Chunks completed

| Chunk | Commit | Reviewer verdict | Rounds |
|---|---|---|---|
| C-1: fix spanmetrics invalid include key | 4667e91 | PASS | 1 |

---

## DoD checklist — final state

- [x] `connectors.spanmetrics` block valid for v0.104 (no `include:` key) — verified via `docker validate`
- [x] spanmetrics connector preserved and wired correctly in pipelines
- [x] otel-collector image version unchanged (0.104.0)
- [x] No `Co-Authored-By` trailer in any new commit
- [x] No `--no-verify` used
- [x] Only `otel-collector-config.yaml` touched

---

## Residual risks / deferred items

None.

---

## Escalation resolutions

None.

---

## Lessons learned / notes for next session

`spanmetrics` connector v0.104+ uses OTTL-based filter processors for span selection — the older `include:/exclude:` config-level keys were valid only in older forms of the spanmetrics processor (before it became a connector). When upgrading collector versions, audit all connector configs against the new schema.
