# Requirements Document

## Introduction

A pre-baked Grafana dashboard that gives operators real-time visibility into proxied request traffic — broken down by service and by agent identity. The dashboard answers "how many requests per second is each agent making to each service?" and "who is using what?" It leverages the existing OTel span attributes (`mintkey.actor_id`, `mintkey.service_id`, `mintkey.outcome`) already emitted by the Egress Proxy plugin, deriving Prometheus metrics via the OTel Collector's `spanmetrics` connector so no proxy code changes are required for the agent dimension.

## Glossary

- **Dashboard**: A Grafana JSON dashboard definition provisioned automatically via the Grafana provisioning mechanism in Docker Compose.
- **Request_Monitoring_Dashboard**: The specific Grafana dashboard created by this feature, focused on proxied request traffic.
- **Proxy_Metrics**: Prometheus-format metrics emitted by the Egress Proxy plugin or derived from its spans.
- **Agent**: An AI agent identified by its `mintkey.actor_id` (prefixed ULID `agent_…`) in JWT claims and span attributes.
- **Service**: A registered backend service identified by `mintkey.service_id` (prefixed ULID `svc_…`).
- **Spanmetrics_Connector**: The OTel Collector component that derives Prometheus metrics (counters, histograms) from span attributes without modifying the emitting service.
- **Operator**: A human user of the Mintkey admin console who views the dashboard.

## Requirements

### Requirement 1: Request Rate Panel

**User Story:** As an operator, I want to see the request rate (requests per second) for each service on the dashboard, so that I can understand current traffic patterns at a glance.

#### Acceptance Criteria

1. THE Request_Monitoring_Dashboard SHALL display a Grafana Time Series panel showing requests per second, with one series per distinct `mintkey_service_id` label value.
2. WHEN an operator selects a time range, THE Request_Monitoring_Dashboard SHALL compute and display the per-second rate using the PromQL `rate()` function over the selected range, with Grafana's automatic step interval determining point resolution.
3. THE Request_Monitoring_Dashboard SHALL derive request rate from the `calls_total` counter metric produced by the Spanmetrics_Connector from `mintkey.proxy.handle_request` spans, grouped by the `mintkey_service_id` dimension.

### Requirement 2: Request Count Panel

**User Story:** As an operator, I want to see total request counts over a configurable time period per service, so that I can understand usage volumes.

#### Acceptance Criteria

1. THE Request_Monitoring_Dashboard SHALL display a stat panel showing total request count per service for the selected time range, derived from the Spanmetrics_Connector counter metric with the `mintkey.service_id` dimension.
2. WHEN an operator changes the Grafana time picker, THE Request_Monitoring_Dashboard SHALL update the count to reflect the new period.
3. THE Request_Monitoring_Dashboard SHALL support Grafana's standard time range controls (last 5m, 15m, 1h, 6h, 24h, 7d, custom).
4. WHEN an operator selects a value in the agent or service template variable dropdowns, THE Request_Monitoring_Dashboard SHALL filter the request count panel to reflect only matching traffic.
5. IF no requests are recorded for a service within the selected time range, THEN THE Request_Monitoring_Dashboard SHALL display a count of 0 for that service rather than omitting it from the panel.

### Requirement 3: Agent Filter

**User Story:** As an operator, I want to filter the dashboard by agent identity, so that I can understand which specific agent is generating traffic.

#### Acceptance Criteria

1. THE Request_Monitoring_Dashboard SHALL provide a template variable dropdown populated with all distinct `mintkey.actor_id` label values observed in the Spanmetrics-derived metrics, including the `unknown` placeholder value produced by the Spanmetrics_Connector for unauthenticated requests.
2. THE Request_Monitoring_Dashboard SHALL default the agent filter selection to "All" so that on initial load all agent traffic is displayed.
3. WHEN an operator selects a specific agent from the dropdown, THE Request_Monitoring_Dashboard SHALL filter all panels to show only requests where `mintkey.actor_id` matches the selected value.
4. WHEN the "All" option is selected, THE Request_Monitoring_Dashboard SHALL show aggregate traffic across all agents without filtering by `mintkey.actor_id`.
5. THE Request_Monitoring_Dashboard SHALL derive the agent dimension from the `mintkey.actor_id` span attribute via the Spanmetrics_Connector.

### Requirement 4: Agent-to-Service Usage Matrix

**User Story:** As an operator, I want to see which agents are calling which services, so that I can understand "who is using what."

#### Acceptance Criteria

1. THE Request_Monitoring_Dashboard SHALL display a table panel showing request counts broken down by agent and service pairs, with columns: `mintkey.actor_id` (agent), `mintkey.service_id` (service), and request count.
2. WHEN an operator views the table, THE Request_Monitoring_Dashboard SHALL show one row per agent-service combination that has at least one request in the selected time range, omitting combinations with zero requests.
3. THE Request_Monitoring_Dashboard SHALL sort the table by request count descending by default.
4. THE Request_Monitoring_Dashboard SHALL derive the table data from the Spanmetrics_Connector counter metric using the `mintkey.actor_id` and `mintkey.service_id` dimensions.
5. WHEN the dashboard agent filter or service filter template variables are set to a specific value, THE Request_Monitoring_Dashboard SHALL filter the table rows to match the selected agent, service, or both.

### Requirement 5: Service Filter

**User Story:** As an operator, I want to filter the dashboard by service, so that I can focus on traffic to a specific backend.

#### Acceptance Criteria

1. THE Request_Monitoring_Dashboard SHALL provide a template variable dropdown populated with service identifiers derived from the `mintkey.service_id` span attribute label in the Spanmetrics_Connector output, defaulting to "All".
2. WHEN an operator selects a service from the dropdown, THE Request_Monitoring_Dashboard SHALL filter all panels to show only requests where `mintkey.service_id` matches the selected value.
3. THE Request_Monitoring_Dashboard SHALL support an "All" option in the service filter that removes the service dimension filter and shows aggregate traffic across all services.
4. WHEN both the service filter and the agent filter are active with non-"All" selections, THE Request_Monitoring_Dashboard SHALL apply both filters as a logical AND, showing only requests matching both the selected agent and the selected service.

### Requirement 6: Outcome Breakdown

**User Story:** As an operator, I want to see request outcomes (success, denied, error) alongside rates, so that I can spot problems quickly.

#### Acceptance Criteria

1. THE Request_Monitoring_Dashboard SHALL display a panel showing request counts broken down by outcome (`success`, `client_error`, `server_error`, `denied`, `error`) for the selected time range, derived from the `mintkey.outcome` span attribute dimension via the Spanmetrics_Connector.
2. THE Request_Monitoring_Dashboard SHALL assign a distinct color override to each outcome category in the panel definition, grouping `success` as a non-alert color and `client_error`, `server_error`, `denied`, `error` as alert colors, so that error outcomes are visually distinguishable from successful ones without operator configuration.
3. WHEN an operator selects a time range via the Grafana time picker, THE Request_Monitoring_Dashboard SHALL update the outcome counts to reflect only requests within that period.

### Requirement 7: OTel Collector Spanmetrics Configuration

**User Story:** As a platform operator, I want the OTel Collector to derive request metrics from proxy spans automatically, so that the dashboard works without modifying the proxy plugin code.

#### Acceptance Criteria

1. THE Spanmetrics_Connector SHALL produce a histogram metric named `mintkey_proxy_duration` from `mintkey.proxy.handle_request` spans, with dimensions `mintkey_actor_id`, `mintkey_service_id`, `mintkey_outcome`, using explicit histogram bucket boundaries of `[5, 10, 25, 50, 75, 100, 250, 500, 750, 1000, 2500, 5000, 10000]` milliseconds.
2. THE Spanmetrics_Connector SHALL produce a counter metric named `mintkey_proxy_calls_total` representing total span count with the same dimensions (`mintkey_actor_id`, `mintkey_service_id`, `mintkey_outcome`).
3. THE Spanmetrics_Connector configuration SHALL be included in the OTel Collector config file `infra/observability/infra/observability/otel-collector-config.yaml` shipped with the repo, wired as a connector between the `traces` pipeline and the `metrics` pipeline so that spans flow through the connector and derived metrics are exported to Prometheus.
4. IF the OTel Collector receives `mintkey.proxy.handle_request` spans without `mintkey.actor_id` (e.g., unauthenticated denials), THEN THE Spanmetrics_Connector SHALL label those metrics with a placeholder dimension value `unknown`.
5. IF the OTel Collector receives `mintkey.proxy.handle_request` spans without `mintkey.service_id` or `mintkey.outcome`, THEN THE Spanmetrics_Connector SHALL label those metrics with a placeholder dimension value `unknown` for the missing attribute.
6. THE Spanmetrics_Connector SHALL filter spans by name, processing only spans named `mintkey.proxy.handle_request` and ignoring all other span names.

### Requirement 8: Dashboard Provisioning

**User Story:** As a platform operator, I want the dashboard to be automatically provisioned when I run `docker compose up`, so that it works out of the box with no manual setup.

#### Acceptance Criteria

1. THE Request_Monitoring_Dashboard SHALL be defined as a Grafana JSON file located at `infra/observability/infra/observability/grafana/provisioning/dashboards/request-monitoring.json` in the repository.
2. THE Request_Monitoring_Dashboard SHALL be provisioned via Grafana's file-based dashboard provisioning using the existing `infra/observability/infra/observability/grafana/provisioning/dashboards/provider.yaml` configuration in the Docker Compose setup.
3. WHEN an operator starts the stack with `docker compose up`, THE Request_Monitoring_Dashboard SHALL be available in Grafana under the "Mintkey" folder without manual import.
4. THE Request_Monitoring_Dashboard SHALL reference the Prometheus datasource by UID matching the provisioned datasource configuration.
