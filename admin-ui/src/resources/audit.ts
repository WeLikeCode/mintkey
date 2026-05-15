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
  filterKeys: ["q", "event_type", "actor_id", "actor_type", "target_id", "target_type", "from_ts", "to_ts"],
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
    { path: "from_ts", type: "datetime" },
    { path: "to_ts", type: "datetime" },
  ],
});

export const AuditResource: ResourceWithOptions & { adminResource: typeof _auditResource } = {
  resource: _auditResource.resource,
  adminResource: _auditResource,
  options: {
    navigation: { name: "Audit Log", icon: "ClipboardList" },
    listProperties: ["created_at", "event_type", "actor_type", "actor_id", "target_type", "target_id", "tenant_id"],
    showProperties: ["id", "created_at", "event_type", "actor_type", "actor_id", "target_type", "target_id", "payload", "prev_hash", "hash", "request_id", "trace_id", "tenant_id"],
    filterProperties: ["q", "event_type", "actor_id", "actor_type", "target_id", "target_type", "from_ts", "to_ts"],
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
      event_type: {
        isVisible: { list: true, show: true, edit: false, filter: true },
        label: "Event Type",
        description: "Exact match on the event type. Select from known types or leave blank to show all.",
        availableValues: [
          { value: "agent.created", label: "agent.created" },
          { value: "agent.revoked", label: "agent.revoked" },
          { value: "agent.deleted", label: "agent.deleted" },
          { value: "agent.permission.granted", label: "agent.permission.granted" },
          { value: "agent.permission.revoked", label: "agent.permission.revoked" },
          { value: "api_key.created", label: "api_key.created" },
          { value: "api_key.revoked", label: "api_key.revoked" },
          { value: "api_key.rotated", label: "api_key.rotated" },
          { value: "audit.chain.tamper_acknowledged", label: "audit.chain.tamper_acknowledged" },
          { value: "credential.registered", label: "credential.registered" },
          { value: "credential.rotated", label: "credential.rotated" },
          { value: "credential.revoked", label: "credential.revoked" },
          { value: "platform_admin.access", label: "platform_admin.access" },
          { value: "proxy.aud_mismatch_rejected", label: "proxy.aud_mismatch_rejected" },
          { value: "proxy.error", label: "proxy.error" },
          { value: "proxy.hit", label: "proxy.hit" },
          { value: "service.registered", label: "service.registered" },
          { value: "service.updated", label: "service.updated" },
          { value: "service.deleted", label: "service.deleted" },
          { value: "settings.updated", label: "settings.updated" },
          { value: "tenant.created", label: "tenant.created" },
          { value: "tenant.updated", label: "tenant.updated" },
          { value: "tenant.deleted", label: "tenant.deleted" },
          { value: "token.denied", label: "token.denied" },
          { value: "token.issued", label: "token.issued" },
        ],
      },
      actor_type: {
        isVisible: { list: true, show: true, edit: false, filter: true },
        label: "Actor Type",
        description: "Filter by the type of principal that performed the action.",
        availableValues: [
          { value: "agent", label: "agent" },
          { value: "operator", label: "operator" },
          { value: "platform_admin", label: "platform_admin" },
          { value: "proxy", label: "proxy" },
        ],
      },
      target_type: {
        isVisible: { list: true, show: true, edit: false, filter: true },
        label: "Target Type",
        description: "Filter by the type of resource that was acted upon.",
        availableValues: [
          { value: "admin_settings", label: "admin_settings" },
          { value: "agent", label: "agent" },
          { value: "api_key", label: "api_key" },
          { value: "audit_event", label: "audit_event" },
          { value: "credential", label: "credential" },
          { value: "permission", label: "permission" },
          { value: "proxy_request", label: "proxy_request" },
          { value: "service", label: "service" },
          { value: "tenant", label: "tenant" },
        ],
      },
      from_ts: {
        isVisible: { list: false, show: false, edit: false, filter: true },
        type: "datetime",
        label: "From",
        description: "Inclusive lower bound on event time. AdminJS sends a range shape that is split into from_ts and to_ts query params.",
      },
      to_ts: {
        isVisible: { list: false, show: false, edit: false, filter: true },
        type: "datetime",
        label: "To",
        description: "Exclusive upper bound on event time.",
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
