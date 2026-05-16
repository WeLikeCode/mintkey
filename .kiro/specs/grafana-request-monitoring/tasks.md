# Implementation Plan: Grafana Request Monitoring

## Overview

Add a pre-baked Grafana dashboard for proxied request traffic visibility by: (1) adding an explicit UID to the Prometheus datasource provisioning, (2) configuring the OTel Collector spanmetrics connector to derive metrics from proxy spans, (3) wiring the connector into traces/metrics pipelines, and (4) creating the dashboard JSON with 4 panels and 2 template variables.

## Tasks

- [x] 1. Add explicit UID to Prometheus datasource provisioning
  - [x] 1.1 Add `uid: prometheus` to the Prometheus datasource in `grafana/provisioning/datasources/prometheus.yaml`
    - Add the `uid: prometheus` field to the existing datasource entry so the dashboard can reference it by stable UID
    - _Requirements: 8.4_

- [x] 2. Configure OTel Collector spanmetrics connector
  - [x] 2.1 Add `connectors.spanmetrics` section to `otel-collector-config.yaml`
    - Add the `connectors:` top-level key with the `spanmetrics` configuration
    - Set `namespace: mintkey_proxy` to produce `mintkey_proxy_calls_total` and `mintkey_proxy_duration_milliseconds_*` metrics
    - Configure `dimensions` for `mintkey.actor_id`, `mintkey.service_id`, `mintkey.outcome` with `default: "unknown"`
    - Set `include` filter with `match_type: strict` and `span_names: ["mintkey.proxy.handle_request"]`
    - Configure explicit histogram buckets: `[5ms, 10ms, 25ms, 50ms, 75ms, 100ms, 250ms, 500ms, 750ms, 1000ms, 2500ms, 5000ms, 10000ms]`
    - Set `aggregation_temporality: AGGREGATION_TEMPORALITY_CUMULATIVE`, `metrics_flush_interval: 15s`, `metrics_expiration: 5m`
    - _Requirements: 7.1, 7.2, 7.4, 7.5, 7.6_

  - [x] 2.2 Wire spanmetrics into traces and metrics pipelines
    - Add `spanmetrics` to `service.pipelines.traces.exporters` list
    - Add `spanmetrics` to `service.pipelines.metrics.receivers` list
    - _Requirements: 7.3_

- [x] 3. Checkpoint - Validate OTel Collector config
  - Ensure the YAML is valid and parseable, ask the user if questions arise.

- [x] 4. Create Grafana dashboard JSON
  - [x] 4.1 Create `grafana/provisioning/dashboards/request-monitoring.json` with dashboard skeleton and template variables
    - Create the dashboard JSON file with `uid: "mintkey-request-monitoring"`, `title: "Request Monitoring"`, `schemaVersion: 39`
    - Define template variable `agent` querying `label_values(mintkey_proxy_calls_total, mintkey_actor_id)` with `includeAll: true`, default "All"
    - Define template variable `service` querying `label_values(mintkey_proxy_calls_total, mintkey_service_id)` with `includeAll: true`, default "All"
    - Both variables reference datasource `uid: "prometheus"`
    - Set `refresh: "30s"`, `time: { from: "now-1h", to: "now" }`, `tags: ["mintkey", "proxy"]`
    - _Requirements: 3.1, 3.2, 3.4, 5.1, 5.3, 8.1, 8.2, 8.3, 8.4_

  - [x] 4.2 Add Request Rate panel (Time Series)
    - Add a Time Series panel with PromQL: `rate(mintkey_proxy_calls_total{mintkey_actor_id=~"$agent", mintkey_service_id=~"$service"}[$__rate_interval])`
    - Legend: `{{mintkey_service_id}}`
    - One series per distinct `mintkey_service_id` value
    - _Requirements: 1.1, 1.2, 1.3_

  - [x] 4.3 Add Request Count panel (Stat)
    - Add a Stat panel with PromQL: `increase(mintkey_proxy_calls_total{mintkey_actor_id=~"$agent", mintkey_service_id=~"$service"}[$__range])`
    - Legend: `{{mintkey_service_id}}`
    - Set `"noValue": "0"` in field config so missing services show 0
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_

  - [x] 4.4 Add Outcome Breakdown panel (Time Series, stacked)
    - Add a stacked Time Series panel with PromQL: `sum by (mintkey_outcome) (rate(mintkey_proxy_calls_total{mintkey_actor_id=~"$agent", mintkey_service_id=~"$service"}[$__rate_interval]))`
    - Legend: `{{mintkey_outcome}}`
    - Add color overrides: `success` → green (#73BF69), `client_error` → yellow (#FADE2A), `server_error` → red (#F2495C), `denied` → orange (#FF9830), `error` → dark red (#C4162A)
    - _Requirements: 6.1, 6.2, 6.3_

  - [x] 4.5 Add Agent-Service Matrix panel (Table)
    - Add a Table panel with PromQL: `topk(50, sum by (mintkey_actor_id, mintkey_service_id) (increase(mintkey_proxy_calls_total{mintkey_actor_id=~"$agent", mintkey_service_id=~"$service"}[$__range])))`
    - Configure table transformations: rename `mintkey_actor_id` → "Agent", `mintkey_service_id` → "Service", `Value` → "Requests"
    - Sort by "Requests" descending by default
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_

- [x] 5. Checkpoint - Validate dashboard JSON
  - Ensure the JSON is valid and parseable, ask the user if questions arise.

- [x] 6. Validation tests
  - [x] 6.1 Write unit test validating OTel Collector config structure
    - Assert `spanmetrics` exists under `connectors` key
    - Assert `spanmetrics` appears in `service.pipelines.traces.exporters`
    - Assert `spanmetrics` appears in `service.pipelines.metrics.receivers`
    - Assert `include.span_names` contains exactly `["mintkey.proxy.handle_request"]`
    - _Requirements: 7.3, 7.6_

  - [x] 6.2 Write unit test validating dashboard JSON structure
    - Assert template variables `agent` and `service` exist with correct queries
    - Assert all 4 panels reference datasource `uid: "prometheus"`
    - Assert all panel queries reference both `$agent` and `$service` template variables
    - Assert outcome panel has color overrides for all 5 outcome values
    - Assert dashboard `uid` is `"mintkey-request-monitoring"`
    - _Requirements: 3.1, 5.1, 8.4_

- [x] 7. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- No proxy plugin code changes are required — the spanmetrics connector derives metrics from existing span attributes
- The OTel Collector image `otel/opentelemetry-collector-contrib:0.104.0` already includes the spanmetrics connector
- Prometheus already scrapes `otel-collector:8889`, so no Prometheus config changes are needed
- The existing `grafana/provisioning/dashboards/provider.yaml` auto-loads all JSON files from the provisioning directory

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "2.1"] },
    { "id": 1, "tasks": ["2.2", "4.1"] },
    { "id": 2, "tasks": ["4.2", "4.3", "4.4", "4.5"] },
    { "id": 3, "tasks": ["6.1", "6.2"] }
  ]
}
```
