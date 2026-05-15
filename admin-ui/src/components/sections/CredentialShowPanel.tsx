/**
 * CredentialShowPanel — show-page intro panel for the Credentials resource (OPS-Y).
 *
 * Rendered as a property.components.show override on a virtual `_credentialShowPanel`
 * property placed at the top of the Credentials show page (AdminJS 7.x pattern).
 *
 * Surfaces to the operator:
 *   1. Contextual header clarifying what this credential is and how it works.
 *   2. A direct link to the bound Service's show page.
 *   3. A "View audit history" deep-link to the audit_events list filtered by target_id.
 *   4. A backlog note that last-used timestamp is not yet tracked (TODO-last-used).
 *
 * Filter key verified in audit.ts filterKeys: ["q", "event_type", "actor_id",
 * "actor_type", "target_id", "target_type", "from_ts", "to_ts"].
 * Audit deep-link uses `filters.target_id` (AdminJS URL query encoding).
 *
 * Source: OPS-Y spec; ADMIN_UI_SPEC.md §2.4; UX-CLARITY Pain 6.
 */

import React from "react";
import { Box, Text } from "@adminjs/design-system";
// eslint-disable-next-line @typescript-eslint/ban-ts-comment
// @ts-ignore — adminjs re-exports ValueGroup from @adminjs/design-system
import { ValueGroup } from "@adminjs/design-system";

// ── types ────────────────────────────────────────────────────────────────────

interface Props {
  record?: {
    id?: string | number;
    params?: Record<string, unknown>;
  };
  property?: { path?: string; label?: string };
}

// ── component ─────────────────────────────────────────────────────────────────

const CredentialShowPanel: React.FC<Props> = ({ record, property }) => {
  const label = property?.label ?? "About this credential";

  const serviceId = (record?.params?.id ?? record?.id ?? "") as string;
  const serviceName = (record?.params?.name ?? record?.params?.slug ?? serviceId) as string;

  const serviceShowUrl = serviceId
    ? `/admin/resources/services/records/${serviceId}/show`
    : `/admin/resources/services`;

  // AdminJS encodes filter params as filters.<key> in the query string.
  // audit_events filterKeys include "target_id" (verified in audit.ts).
  const auditUrl = serviceId
    ? `/admin/resources/audit_events?filters.target_id=${encodeURIComponent(serviceId)}`
    : `/admin/resources/audit_events`;

  return (
    <ValueGroup label={label}>
      <Box data-testid="credential-show-panel" mb="xl">
        {/* ── Header paragraph ─────────────────────────────────────── */}
        <Text
          data-testid="credential-show-panel-intro"
          style={{ fontSize: 13, lineHeight: 1.6, color: "#495057", marginBottom: 16 }}
        >
          This page shows the credential bound to service{" "}
          <strong>{serviceName || serviceId}</strong>. Credentials are
          envelope-encrypted in the Vault Adapter; plaintext is never displayed.
          Agents never see the value — it&apos;s fetched at request time by the Egress Proxy and injected into the outbound call. To rotate, use the action above.
        </Text>

        {/* ── Service link ──────────────────────────────────────────── */}
        <Box mb="default" data-testid="credential-show-panel-service-row">
          <Text style={{ fontSize: 13, color: "#6c757d", marginBottom: 4 }}>
            <strong>Service:</strong>{" "}
            <a
              href={serviceShowUrl}
              data-testid="credential-show-panel-service-link"
              style={{ color: "#3795BE", textDecoration: "underline" }}
            >
              {serviceName || serviceId}
            </a>
          </Text>
        </Box>

        {/* ── Audit history link ────────────────────────────────────── */}
        <Box mb="default" data-testid="credential-show-panel-audit-row">
          <Text style={{ fontSize: 13 }}>
            <a
              href={auditUrl}
              data-testid="credential-show-panel-audit-link"
              style={{ color: "#3795BE", textDecoration: "underline" }}
            >
              View audit history
            </a>{" "}
            <span style={{ color: "#6c757d" }}>
              — filtered to events where target_id = {serviceId || "(this service)"}
            </span>
          </Text>
        </Box>

        {/* ── Backlog note ──────────────────────────────────────────── */}
        <Box
          data-testid="credential-show-panel-backlog-note"
          p="default"
          style={{
            background: "#f8f9fa",
            border: "1px solid #dee2e6",
            borderRadius: 4,
          }}
        >
          <Text style={{ fontSize: 12, color: "#6c757d", fontStyle: "italic" }}>
            Last-used timestamp not yet tracked — see backlog item TODO-last-used.
          </Text>
        </Box>
      </Box>
    </ValueGroup>
  );
};

export default CredentialShowPanel;
