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
 * Source: Phase 1b of action-grid completion; ADMIN_UI_ACTION_MATRIX.md.
 */

import React, { useState } from "react";
import { Box, H3, Text, Button } from "@adminjs/design-system";
import { ApiClient } from "adminjs";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const ConfirmAction = (props: Record<string, any>): React.ReactElement => {
  const { record, resource, action } = props as {
    record: { id: string | number; params: Record<string, unknown> };
    resource: { id: string };
    action: { name: string; label: string };
  };

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
