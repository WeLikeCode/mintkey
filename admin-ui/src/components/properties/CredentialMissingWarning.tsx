/**
 * CredentialMissingWarning — show-page virtual property component (UX-FB-B).
 *
 * Renders a red callout when a service requires credentials but none are
 * configured (current_key_version === 0 and auth_scheme !== 'none').
 *
 * Receives `record` from AdminJS show pipeline via the _credential_warning
 * virtual property declared in services.ts.
 *
 * Conditions for rendering (must ALL be true):
 *   - record.params.auth_scheme !== 'none'   (service requires credentials)
 *   - record.params.current_key_version < 1  (no active credential configured)
 *
 * Source: UX-FB-B; admin-ui-ux-uplift.
 */

import React from "react";
import { Box, Text } from "@adminjs/design-system";

// ── types ─────────────────────────────────────────────────────────────────────

interface RecordInterface {
  params?: Record<string, unknown>;
}

interface CredentialMissingWarningProps {
  record?: RecordInterface;
}

// ── component ─────────────────────────────────────────────────────────────────

const CredentialMissingWarning = (
  props: CredentialMissingWarningProps
): React.ReactElement | null => {
  const { record } = props;
  const params = record?.params ?? {};

  const authScheme = (params.auth_scheme as string) ?? "";
  const currentKeyVersion = Number(params.current_key_version ?? 0);

  // Do not render when service does not need credentials or one is configured
  if (authScheme === "none" || currentKeyVersion >= 1) {
    return null;
  }

  return (
    <Box
      data-testid="credential-missing-warning"
      style={{
        background: "#fff4f4",
        borderLeft: "4px solid #e85c5c",
        borderRadius: 4,
        padding: "16px 20px",
        marginBottom: 16,
      }}
    >
      <Text
        style={{
          fontWeight: 700,
          color: "#b91c1c",
          marginBottom: 6,
          fontSize: 14,
        }}
      >
        No credential is configured for this service.
      </Text>
      <Text style={{ color: "#7f1d1d", fontSize: 13 }}>
        Agents that hold a permission grant on this service will receive 502
        from the egress proxy until you add a credential. Click &ldquo;Set
        Credential&rdquo; (top of this page) to configure one.
      </Text>
    </Box>
  );
};

export default CredentialMissingWarning;
