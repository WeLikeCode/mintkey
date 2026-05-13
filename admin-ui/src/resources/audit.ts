/**
 * AdminJS Audit Log resource — T-1.7.4.
 *
 * READ-ONLY: list audit events with filters. No write operations (the audit log
 * is append-only by DB policy).
 *
 * The list envelope is reconciled with what admin-api actually returns from
 * `GET /v1/tenants/{tid}/audit`: `{ "items": [...], "next_cursor": ... }`, and
 * each item is `{ id, event_type, tenant_id, payload, created_at }`
 * (admin-api/src/admin_api/api/audit.py `_row_to_dict`).
 *
 * The OpenAPI `AuditEvent` schema additionally specifies `actor_id`,
 * `actor_type`, `target_id`, `target_type`, `request_id`, `trace_id`,
 * `prev_hash`, `hash` (ADMIN_UI_SPEC.md §2.8 wants the actor/target columns and
 * the hash-chain linkage). admin-api does not emit those fields on the audit
 * list yet — but we declare them here so the show view can reference them
 * without AdminJS emitting `[AdminJS]: There is no property of the name`
 * warnings, and so the columns light up automatically once admin-api populates
 * them (no further UI change needed).
 *
 * Source: T-1.7.4; Req 8 AC1–AC5; ADR-0013; ADR-0014.7; OpenAPI AuditEvent.
 */

import type { ResourceWithOptions } from "adminjs";
import { RestResource } from "../lib/rest-resource.js";
import { Components } from "../components/index.js";

const _auditResource = new RestResource({
  id: "audit_events", name: "Audit Events",
  listPath: "/v1/tenants/{tenantId}/audit",
  listKey: "events",
  idField: "id",
  filterKeys: ["q", "event_type", "actor_id", "target_id", "from_ts", "to_ts"],
  properties: [
    { path: "id", type: "string", isId: true },
    { path: "event_type", type: "string" },
    { path: "tenant_id", type: "string" },
    { path: "actor_id", type: "string" },
    { path: "actor_type", type: "string" },
    { path: "target_id", type: "string" },
    { path: "target_type", type: "string" },
    { path: "request_id", type: "string" },
    { path: "trace_id", type: "string" },
    { path: "payload", type: "mixed" },
    { path: "prev_hash", type: "string" },
    { path: "hash", type: "string" },
    { path: "created_at", type: "datetime" },
    // alias also referenced by the OpenAPI schema; admin-api returns `created_at`.
    { path: "at", type: "datetime" },
    // Virtual filter-only properties (not returned by API, only used for filtering)
    { path: "q", type: "string" },
    { path: "from_ts", type: "string" },
    { path: "to_ts", type: "string" },
  ],
});

export const AuditResource: ResourceWithOptions & { adminResource: typeof _auditResource } = {
  resource: _auditResource.resource,
  adminResource: _auditResource,
  options: {
    navigation: { name: "Audit Log", icon: "ClipboardList" },
    listProperties: ["created_at", "event_type", "actor_type", "actor_id", "target_type", "target_id", "tenant_id"],
    showProperties: ["id", "created_at", "event_type", "actor_type", "actor_id", "target_type", "target_id", "payload", "prev_hash", "hash", "request_id", "trace_id", "tenant_id"],
    filterProperties: ["q", "event_type", "actor_id", "target_id", "from_ts", "to_ts", "actor_type", "target_type"],
    properties: {
      payload: {
        type: "mixed",
        isArray: false,
        components: { show: Components.JsonValue },
      },
      q: {
        isVisible: { list: false, show: false, edit: false, filter: true },
        label: "Search (event type)",
        description: "Case-insensitive substring match on event_type.",
      },
      from_ts: {
        isVisible: { list: false, show: false, edit: false, filter: true },
        label: "From (ISO 8601)",
        description: "Inclusive lower bound on event time. Example: 2024-01-01T00:00:00Z",
      },
      to_ts: {
        isVisible: { list: false, show: false, edit: false, filter: true },
        label: "To (ISO 8601)",
        description: "Exclusive upper bound on event time. Example: 2024-12-31T23:59:59Z",
      },
    },
    // All write actions disabled — audit log is append-only
    actions: {
      list: {
        component: Components.AuditIntro,
      },
      new: { isVisible: false },
      edit: { isVisible: false },
      delete: { isVisible: false },
      bulkDelete: { isVisible: false },
    },
    sort: {
      direction: "desc",
      sortBy: "created_at",
    },
  },
};
