# otel-collector spanmetrics config fix — Session Plan

**Session:** `2026-05-17-otel-collector-config`
**Driver:** IMPLEMENTER OTEL-CONFIG
**Status:** Complete

---

## Mission

`otel-collector` container crashes on startup with `* '' has invalid keys: include` because `connectors.spanmetrics.include` is not a valid top-level key in spanmetrics connector v0.104.x. The `include` filter block was removed and replaced with a `filter/spanmetrics_input` processor inserted before the spanmetrics connector in the traces pipeline.

---

## Hard rules (every chunk inherits)

- No `Co-Authored-By` trailer on any commit
- No `--no-verify`
- No `docker compose down -v`
- No edits to accepted ADRs
- No product-code changes outside the scope defined in this session
- Validate via tools: every "done" claim carries command output
- Surgical changes; one logical change per commit
- DO NOT downgrade otel-collector image version
- DO NOT remove the spanmetrics connector

---

## Issue intake

**Problem statement:** `otel-collector` fails to start due to `connectors.spanmetrics.include` not being a valid key in `otel/opentelemetry-collector-contrib:0.104.0`. Integration Tests CI cannot run because the collector never comes up healthy.

**User-visible symptom:** Container restart loop; CI fails on Integration Tests job. Error: `* '' has invalid keys: include`

**Expected behavior:** `otel-collector` starts and stays running; spanmetrics connector produces metrics for spans named `mintkey.proxy.handle_request`.

**Evidence:** `otel-collector-config.yaml` lines 64–68 — `include.match_type: strict / span_names: [mintkey.proxy.handle_request]` — not valid in spanmetrics v0.104.x schema.

**Scope:** `otel-collector-config.yaml` only.

**Out of scope:** All other files. Image version must stay at 0.104.0.

**Risk level:** CI / availability

**Verification target:** `docker compose up -d otel-collector && sleep 5 && docker compose ps otel-collector` shows state `running`. OR push to CI and Integration Tests pass.

**Owner decisions needed:** None — filter processor is the correct v0.104 equivalent.

---

## Fix applied

Removed `include:` block from `connectors.spanmetrics` (invalid key). Added `filter/spanmetrics_input` processor with OTTL span name match. Inserted processor into traces pipeline before `spanmetrics` connector.
