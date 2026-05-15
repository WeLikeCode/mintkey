/**
 * ConfirmAction — generic confirmation page for destructive record-type actions.
 *
 * AdminJS 7.x requires a `component:` on every custom action. This component
 * serves revokeAgent, rotateCredential, and any other "click to confirm" action.
 *
 * Flow:
 *   GET  → handler returns { record } (no API side-effect) → this component renders
 *   POST → user clicks Confirm → ApiClient.recordAction({ method: "post" })
 *          → handler executes → component shows notice / navigates away
 *
 * Props (beyond the standard AdminJS record/resource/action triple):
 *   description?: string — optional explanatory copy rendered below the record
 *     label and above the action buttons. Intended for per-action guidance, e.g.:
 *       "Revocation is permanent — to restore access, create a new agent."
 *     Defaults to empty string; when empty nothing extra is rendered (no regression
 *     for existing callers).
 *
 * Source: Phase 1b of action-grid completion; ADMIN_UI_ACTION_MATRIX.md.
 *         UX-CLARITY chunk F — description prop added.
 */

import React, { useState } from "react";
import { Box, H3, Text, Button } from "@adminjs/design-system";
import { ApiClient } from "adminjs";

/** Props passed to ConfirmAction by AdminJS plus our optional extension. */
interface ConfirmActionProps {
  record: { id: string | number; params: Record<string, unknown> };
  resource: { id: string };
  action: { name: string; label: string };
  /**
   * Optional explanatory copy shown in the dialog body, below the record label
   * and above the confirm/cancel buttons. When omitted (or empty) nothing extra
   * is rendered so existing callers are unaffected.
   */
  description?: string;
  [key: string]: unknown;
}

const ConfirmAction = (props: Record<string, unknown>): React.ReactElement => {
  const { record, resource, action, description = "" } = props as ConfirmActionProps;

  const [loading, setLoading] = useState(false);
  const [notice, setNotice] = useState<{ type: "success" | "error"; message: string } | null>(null);

  const handleConfirm = async () => {
    setLoading(true);
    setNotice(null);
    try {
      const api = new ApiClient();
      const response = await api.recordAction({
        resourceId: resource.id,
        recordId: String(record.id),
        actionName: action.name,
        method: "post",
        data: {},
      });
      const result = response.data as {
        redirectUrl?: string;
        notice?: { message: string; type: string };
      };
      if (result?.redirectUrl) {
        window.location.href = result.redirectUrl;
        return;
      }
      const msg = result?.notice?.message ?? "Done";
      const type = result?.notice?.type === "error" ? "error" : "success";
      setNotice({ type, message: msg });
      if (type === "success") {
        setTimeout(() => {
          window.location.href = `/admin/resources/${resource.id}`;
        }, 1500);
      }
    } catch {
      setNotice({ type: "error", message: "Request failed — please try again" });
    } finally {
      setLoading(false);
    }
  };

  const recordLabel =
    (record?.params?.name as string | undefined) ??
    (record?.params?.slug as string | undefined) ??
    String(record?.id ?? "—");

  const cancelHref = `/admin/resources/${resource.id}/records/${record.id}/show`;

  return (
    <Box variant="white" p="xxl" data-testid="confirm-action-page">
      <H3 mb="lg">{action.label}</H3>
      <Text mb="default">
        Record: <strong>{recordLabel}</strong>
      </Text>
      {description && (
        <Text mb="lg" data-testid="confirm-action-description">
          {description}
        </Text>
      )}
      {notice && (
        <Box
          mb="lg"
          p="lg"
          style={{
            background: notice.type === "success" ? "#d4edda" : "#f8d7da",
            border: `1px solid ${notice.type === "success" ? "#c3e6cb" : "#f5c6cb"}`,
            borderRadius: 4,
          }}
          data-testid="action-notice"
        >
          <Text>{notice.message}</Text>
        </Box>
      )}
      {(!notice || notice.type !== "success") && (
        <Box flex mt="xl" style={{ gap: 12 }}>
          <Button
            variant="danger"
            disabled={loading}
            onClick={handleConfirm}
            data-testid="confirm-action-button"
          >
            {loading ? "Processing…" : `Confirm ${action.label}`}
          </Button>
          <Button
            as="a"
            href={cancelHref}
            variant="light"
            data-testid="cancel-action-button"
          >
            Cancel
          </Button>
        </Box>
      )}
    </Box>
  );
};

export default ConfirmAction;
