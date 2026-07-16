# Agent Budgets — Contract Additions (Draft)

> **Status**: Draft for architect review. These additions are applied to the canonical contracts in tasks T-BUD-1.2 through T-BUD-1.5 once the architect accepts P-011/ADR-0029.

---

## 1. OpenAPI — `Constraints` schema extension

Add to `docs/architecture/contracts/rest/openapi.yaml` under `components/schemas/Constraints/properties`:

```yaml
    budget:
      type: object
      additionalProperties: false
      description: |
        Call-count ceiling per period. When exhausted, the proxy returns
        429 budget_exceeded without calling upstream.
        Source: P-011, FR-1, ADR-0029.
      properties:
        ceiling:
          type: integer
          minimum: 1
          description: Maximum calls allowed within a single period.
        period:
          type: string
          enum: [hourly, daily, weekly, monthly]
          description: |
            Reset cadence. Periods are aligned to UTC boundaries:
            hourly=top of hour, daily=midnight, weekly=Monday 00:00,
            monthly=1st 00:00.
        alert_thresholds:
          type: array
          items:
            type: integer
            minimum: 1
            maximum: 100
          default: [50, 80, 100]
          description: |
            Percentage thresholds that trigger budget.threshold_reached
            audit events.
      required: [ceiling, period]
```

---

## 2. OpenAPI — New schemas

Add to `components/schemas`:

```yaml
    BudgetStatus:
      type: object
      additionalProperties: false
      description: Current budget status for a permission grant.
      properties:
        ceiling:
          type: integer
          minimum: 1
        period:
          type: string
          enum: [hourly, daily, weekly, monthly]
        used:
          type: integer
          minimum: 0
        remaining:
          type: integer
          minimum: 0
        period_start:
          type: string
          format: date-time
        period_end:
          type: string
          format: date-time
        alert_thresholds:
          type: array
          items:
            type: integer
      required:
        - ceiling
        - period
        - used
        - remaining
        - period_start
        - period_end
        - alert_thresholds

    BudgetExceededError:
      type: object
      additionalProperties: false
      description: |
        Returned by the proxy when the agent's call budget is exhausted.
        HTTP 429.
      properties:
        error:
          type: string
          enum: [budget_exceeded]
        detail:
          type: string
        permission_id:
          type: string
          pattern: "^perm_[0-9A-HJKMNP-TV-Z]{26}$"
        budget:
          type: object
          additionalProperties: false
          properties:
            ceiling:
              type: integer
            used:
              type: integer
            period:
              type: string
              enum: [hourly, daily, weekly, monthly]
            period_end:
              type: string
              format: date-time
          required: [ceiling, used, period, period_end]
        retry_after:
          type: string
          format: date-time
          description: ISO 8601 timestamp when the budget resets.
      required: [error, detail, permission_id, budget, retry_after]
```

---

## 3. OpenAPI — New endpoints

Add under `paths`:

```yaml
  /v1/tenants/{tenant_id}/agents/{agent_id}/permissions/{permission_id}/budget:
    parameters:
      - $ref: "#/components/parameters/TenantId"
      - $ref: "#/components/parameters/AgentId"
      - in: path
        name: permission_id
        required: true
        schema:
          type: string
          pattern: "^perm_[0-9A-HJKMNP-TV-Z]{26}$"
        description: Permission grant identifier.
    get:
      tags: [Budgets]
      operationId: getBudgetStatus
      summary: Get current budget status for a permission grant.
      description: |
        Returns the budget counter state for the current period. 404 if
        the grant has no budget constraint configured. FR-9.
      responses:
        "200":
          description: Current budget status.
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/BudgetStatus"
              example:
                ceiling: 1000
                period: "daily"
                used: 847
                remaining: 153
                period_start: "2026-06-27T00:00:00Z"
                period_end: "2026-06-28T00:00:00Z"
                alert_thresholds: [50, 80, 100]
        "401":
          $ref: "#/components/responses/Unauthorized"
        "403":
          $ref: "#/components/responses/Forbidden"
        "404":
          $ref: "#/components/responses/NotFound"

  /v1/tenants/{tenant_id}/agents/{agent_id}/permissions/{permission_id}/budget/reset:
    parameters:
      - $ref: "#/components/parameters/TenantId"
      - $ref: "#/components/parameters/AgentId"
      - in: path
        name: permission_id
        required: true
        schema:
          type: string
          pattern: "^perm_[0-9A-HJKMNP-TV-Z]{26}$"
        description: Permission grant identifier.
    post:
      tags: [Budgets]
      operationId: resetBudget
      summary: Reset the budget counter for a permission grant.
      description: |
        Resets the counter to zero for the current period. Creates a new
        counter row. Emits budget.reset audit event. Fires change-channel
        notification so the proxy picks up the reset within ≤ 5 s. FR-5.
      responses:
        "200":
          description: Budget reset. Returns new status.
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/BudgetStatus"
              example:
                ceiling: 1000
                period: "daily"
                used: 0
                remaining: 1000
                period_start: "2026-06-27T00:00:00Z"
                period_end: "2026-06-28T00:00:00Z"
                alert_thresholds: [50, 80, 100]
        "401":
          $ref: "#/components/responses/Unauthorized"
        "403":
          $ref: "#/components/responses/Forbidden"
        "404":
          $ref: "#/components/responses/NotFound"
```

---

## 4. OpenAPI — `AuditEventType` enum additions

Add to the `AuditEventType` enum:

```yaml
        - budget.threshold_reached
        - budget.exceeded
        - budget.config_updated
        - budget.reset
```

---

## 5. OpenAPI — `TargetType` enum addition

Add to the `TargetType` enum (for audit events targeting the budget/permission entity):

```yaml
        - budget
```

---

## 6. Audit Event Schema — New event definitions

Add to `docs/architecture/contracts/events/audit-event.schema.json` under `$defs`:

```json
"ev_budget_threshold_reached": {
  "type": "object",
  "description": "Budget consumption crossed a configured alert threshold.",
  "allOf": [{"$ref": "#/$defs/envelope"}],
  "properties": {
    "event_type": {"const": "budget.threshold_reached"},
    "target_type": {"const": "budget"},
    "payload": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "permission_id": {"$ref": "#/$defs/permission_id"},
        "used": {"type": "integer"},
        "ceiling": {"type": "integer"},
        "threshold_pct": {"type": "integer", "minimum": 1, "maximum": 100},
        "period_start": {"$ref": "#/$defs/timestamp_utc"},
        "period_end": {"$ref": "#/$defs/timestamp_utc"}
      },
      "required": ["permission_id", "used", "ceiling", "threshold_pct", "period_start", "period_end"]
    }
  },
  "required": ["event_type", "target_type", "payload"]
},

"ev_budget_exceeded": {
  "type": "object",
  "description": "A proxied request was denied because the budget ceiling was reached.",
  "allOf": [{"$ref": "#/$defs/envelope"}],
  "properties": {
    "event_type": {"const": "budget.exceeded"},
    "target_type": {"const": "budget"},
    "payload": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "permission_id": {"$ref": "#/$defs/permission_id"},
        "used": {"type": "integer"},
        "ceiling": {"type": "integer"},
        "period_end": {"$ref": "#/$defs/timestamp_utc"},
        "denied_jti": {"$ref": "#/$defs/ulid"}
      },
      "required": ["permission_id", "used", "ceiling", "period_end", "denied_jti"]
    }
  },
  "required": ["event_type", "target_type", "payload"]
},

"ev_budget_config_updated": {
  "type": "object",
  "description": "An operator changed the budget configuration on a permission grant.",
  "allOf": [{"$ref": "#/$defs/envelope"}],
  "properties": {
    "event_type": {"const": "budget.config_updated"},
    "target_type": {"const": "budget"},
    "payload": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "permission_id": {"$ref": "#/$defs/permission_id"},
        "old_ceiling": {"type": ["integer", "null"]},
        "new_ceiling": {"type": "integer"},
        "old_period": {"type": ["string", "null"]},
        "new_period": {"type": "string", "enum": ["hourly", "daily", "weekly", "monthly"]}
      },
      "required": ["permission_id", "new_ceiling", "new_period"]
    }
  },
  "required": ["event_type", "target_type", "payload"]
},

"ev_budget_reset": {
  "type": "object",
  "description": "An operator manually reset the budget counter mid-period.",
  "allOf": [{"$ref": "#/$defs/envelope"}],
  "properties": {
    "event_type": {"const": "budget.reset"},
    "target_type": {"const": "budget"},
    "payload": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "permission_id": {"$ref": "#/$defs/permission_id"},
        "previous_used": {"type": "integer"},
        "previous_ceiling": {"type": "integer"},
        "new_period_start": {"$ref": "#/$defs/timestamp_utc"}
      },
      "required": ["permission_id", "previous_used", "previous_ceiling", "new_period_start"]
    }
  },
  "required": ["event_type", "target_type", "payload"]
}
```

---

## 7. MCP Tools — `describe_service` output extension

Add to `docs/architecture/contracts/mcp/tools.yaml` in the `your_constraints` properties of `service_full` / `describe_service` output:

```yaml
      budget:
        type: ["object", "null"]
        additionalProperties: false
        description: |
          Call budget status for this agent on this service. Null when
          no budget is configured on the grant. FR-8.
        properties:
          ceiling:
            type: integer
            description: Maximum calls allowed in the current period.
          period:
            type: string
            enum: [hourly, daily, weekly, monthly]
          used:
            type: integer
            description: Calls consumed so far in the current period.
          remaining:
            type: integer
            description: Calls remaining (ceiling - used).
          period_end:
            type: string
            format: date-time
            description: When the current period ends (UTC).
          alert_thresholds:
            type: array
            items:
              type: integer
        required: [ceiling, period, used, remaining, period_end, alert_thresholds]
```

Update the `your_constraints.required` array to include `budget`.

Update the `describe_service` example:

```yaml
      your_constraints:
        rate_limit: 100
        time_window: 60
        request_path_prefix: null
        source_ip_allowlist: null
        budget:
          ceiling: 1000
          period: "daily"
          used: 847
          remaining: 153
          period_end: "2026-06-28T00:00:00Z"
          alert_thresholds: [50, 80, 100]
```

---

## 8. Change-event schema — budget events on `mintkey:agent` channel

The change-channel payload for budget events follows the existing format (ADR-0010):

```json
{
  "event_id": "change_01HX5J9F8V8H8V0CG3F2Y5J6Q1",
  "event_type": "budget.config_updated",
  "tenant_id": "tenant_01HX5J9F8V8H8V0CG3F2Y5J6M9",
  "actor_id": "operator_01HX5J9F8V8H8V0CG3F2Y5J6O1",
  "target_id": "perm_01HX5J9F8V8H8V0CG3F2Y5J6P1",
  "payload": {
    "ceiling": 2000,
    "period": "daily"
  },
  "at": "2026-06-27T14:23:45Z"
}
```

No changes needed to `docs/architecture/contracts/events/change-event.schema.json` — the schema already allows any `event_type` string. The proxy subscriber just needs to recognize the new event types.

---

## Summary of changes per file

| File | Change |
|---|---|
| `docs/architecture/contracts/rest/openapi.yaml` | Add `budget` to Constraints; add `BudgetStatus` + `BudgetExceededError` schemas; add 2 endpoints; extend `AuditEventType` + `TargetType` enums |
| `docs/architecture/contracts/events/audit-event.schema.json` | Add 4 event defs (`ev_budget_*`); add `"budget"` to `target_type` enum |
| `docs/architecture/contracts/mcp/tools.yaml` | Add `budget` to `your_constraints` in `service_full`/`describe_service` output |
| `docs/architecture/contracts/events/change-event.schema.json` | No change (schema is open to new event_type values) |
