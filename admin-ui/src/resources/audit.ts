/**
 * AdminJS Audit Log resource — T-1.7.4.
 *
 * READ-ONLY: list audit events with filters.
 * No write operations (audit log is append-only by DB policy).
 *
 * Source: T-1.7.4; Req 8 AC1–AC5; ADR-0013; ADR-0014.7.
 */

import type { ResourceWithOptions } from "adminjs";

export const AuditResource: ResourceWithOptions = {
  resource: "audit_events",
  options: {
    navigation: { name: "Audit Log", icon: "ClipboardList" },
    listProperties: ["id", "event_type", "actor_id", "actor_type", "target_id", "target_type", "at"],
    showProperties: ["id", "event_type", "actor_id", "actor_type", "target_id", "target_type", "payload", "hash", "prev_hash", "request_id", "trace_id", "at"],
    filterProperties: ["event_type", "actor_id", "actor_type", "target_id", "target_type"],
    properties: {
      payload: {
        type: "mixed",
        isArray: false,
      },
      hash: {
        type: "string",
      },
      prev_hash: {
        type: "string",
      },
    },
    // All write actions disabled — audit log is append-only
    actions: {
      new: { isVisible: false },
      edit: { isVisible: false },
      delete: { isVisible: false },
      bulkDelete: { isVisible: false },
    },
    sort: {
      direction: "desc",
      sortBy: "at",
    },
  },
};
