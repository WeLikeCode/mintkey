/**
 * AgentSecretGrantsPanel — manage sharing grants for an agent secret (Chunk C6c).
 *
 * Rendered by the `manageGrants` record action on agent-secrets.
 *
 * Features:
 *   1. Lists current grants (recipient_agent_id, created_by, created_at) from
 *      record.params._grants (populated by the handler GET branch).
 *   2. Create-grant form: operator enters a recipient_agent_id and submits;
 *      the handler POST branch calls apiWrite POST to the grants endpoint.
 *   3. Revoke button per grant row: handler POST branch with _action=revoke +
 *      grant_id calls apiWrite DELETE to the specific grant path.
 *
 * Security: no secret value is ever shown here — grants are pure metadata.
 *
 * Source: Chunk C6c; ADR-0019; ADR-0014.4.
 */

import React, { useState } from "react";
import {
  Box,
  H3,
  Text,
  Button,
  Label,
  Input,
} from "@adminjs/design-system";
import { ApiClient } from "adminjs";

// ── types ─────────────────────────────────────────────────────────────────────

interface Grant {
  id: string;
  secret_id: string;
  recipient_agent_id: string;
  created_by: string;
  created_at: string;
}

// Props injected by AdminJS for record-type actions
// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Props = Record<string, any>;

// ── styles ────────────────────────────────────────────────────────────────────

const inputStyle: React.CSSProperties = {
  width: "100%",
  padding: "8px 12px",
  border: "1px solid #dee2e6",
  borderRadius: 4,
  fontSize: 14,
  lineHeight: "1.5",
  boxSizing: "border-box",
};

// ── AgentSecretGrantsPanel ────────────────────────────────────────────────────

const AgentSecretGrantsPanel = (props: Props): React.ReactElement => {
  const { record, resource, action } = props as {
    record: { id: string | number; params: Record<string, unknown> };
    resource: { id: string };
    action: { name: string };
  };

  // Grants list comes from record.params._grants (populated by the handler GET branch)
  const initialGrants = (record?.params?._grants as Grant[] | undefined) ?? [];

  const [grants, setGrants] = useState<Grant[]>(initialGrants);
  const [recipientAgentId, setRecipientAgentId] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [revoking, setRevoking] = useState<string | null>(null);
  const [notice, setNotice] = useState<{ type: "success" | "error"; message: string } | null>(null);

  const secretId = String(record?.id ?? "");
  const secretName =
    (record?.params?.name as string | undefined) ??
    (record?.params?.id as string | undefined) ??
    secretId;

  // ── create grant ────────────────────────────────────────────────────────────
  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!recipientAgentId.trim()) {
      setNotice({ type: "error", message: "Recipient agent ID is required." });
      return;
    }
    setSubmitting(true);
    setNotice(null);
    try {
      const api = new ApiClient();
      const resp = await api.recordAction({
        resourceId: resource.id,
        recordId: secretId,
        actionName: action.name,
        method: "post",
        data: {
          _action: "create",
          recipient_agent_id: recipientAgentId.trim(),
        },
      });
      const result = resp.data as {
        notice?: { message: string; type: string };
        record?: { params?: Record<string, unknown> };
      };
      if (result?.notice?.type === "error") {
        setNotice({ type: "error", message: result.notice.message || "Failed to create grant." });
        return;
      }
      setRecipientAgentId("");
      setNotice({ type: "success", message: "Grant created — the recipient agent can now read this secret." });
      // Refresh grants list from updated record params
      const updated = result?.record?.params?._grants as Grant[] | undefined;
      if (Array.isArray(updated)) {
        setGrants(updated);
      }
    } catch (err: unknown) {
      setNotice({ type: "error", message: err instanceof Error ? err.message : "Request failed." });
    } finally {
      setSubmitting(false);
    }
  };

  // ── revoke grant ────────────────────────────────────────────────────────────
  const handleRevoke = async (grantId: string) => {
    setRevoking(grantId);
    setNotice(null);
    try {
      const api = new ApiClient();
      const resp = await api.recordAction({
        resourceId: resource.id,
        recordId: secretId,
        actionName: action.name,
        method: "post",
        data: {
          _action: "revoke",
          grant_id: grantId,
        },
      });
      const result = resp.data as {
        notice?: { message: string; type: string };
        record?: { params?: Record<string, unknown> };
      };
      if (result?.notice?.type === "error") {
        setNotice({ type: "error", message: result.notice.message || "Failed to revoke grant." });
        return;
      }
      setNotice({ type: "success", message: "Grant revoked." });
      const updated = result?.record?.params?._grants as Grant[] | undefined;
      if (Array.isArray(updated)) {
        setGrants(updated);
      } else {
        setGrants((prev) => prev.filter((g) => g.id !== grantId));
      }
    } catch (err: unknown) {
      setNotice({ type: "error", message: err instanceof Error ? err.message : "Request failed." });
    } finally {
      setRevoking(null);
    }
  };

  // ── render ───────────────────────────────────────────────────────────────────
  return (
    <Box variant="white" p="xxl" data-testid="agent-secret-grants-panel">
      <H3 mb="default">Manage Sharing — {secretName}</H3>
      <Text mb="xl" style={{ color: "#6c757d" }}>
        Share this secret with other agents (read-only). Recipients can call
        <code> secret_get({secretName})</code> via MCP. No secret value is shown here.
      </Text>

      {/* Notice */}
      {notice && (
        <Box
          mb="lg"
          p="lg"
          style={{
            background: notice.type === "success" ? "#d4edda" : "#f8d7da",
            border: `1px solid ${notice.type === "success" ? "#c3e6cb" : "#f5c6cb"}`,
            borderRadius: 4,
          }}
          data-testid="grants-notice"
        >
          <Text style={{ color: notice.type === "success" ? "#155724" : "#721c24" }}>
            {notice.message}
          </Text>
        </Box>
      )}

      {/* Create-grant form */}
      <Box
        mb="xl"
        p="lg"
        style={{ background: "#f8f9fa", border: "1px solid #dee2e6", borderRadius: 4 }}
        data-testid="create-grant-section"
      >
        <Text mb="default" style={{ fontWeight: 600, color: "#495057" }}>
          Share with agent
        </Text>
        <form onSubmit={handleCreate} noValidate>
          <Box mb="default" data-testid="field-recipient_agent_id">
            <Label htmlFor="recipient_agent_id" required>Recipient Agent ID</Label>
            <Input
              id="recipient_agent_id"
              type="text"
              value={recipientAgentId}
              onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                setRecipientAgentId(e.target.value)
              }
              placeholder="agent_…"
              style={inputStyle}
              data-testid="field-input-recipient_agent_id"
            />
          </Box>
          <Button
            type="submit"
            variant="primary"
            disabled={submitting}
            data-testid="create-grant-submit"
          >
            {submitting ? "Sharing…" : "Share (grant read access)"}
          </Button>
        </form>
      </Box>

      {/* Grants list */}
      <Box data-testid="grants-list-section">
        <Text mb="default" style={{ fontWeight: 600, color: "#495057" }}>
          Current grants ({grants.length})
        </Text>
        {grants.length === 0 ? (
          <Text style={{ color: "#6c757d" }} data-testid="grants-empty">
            No grants yet. Use the form above to share this secret with another agent.
          </Text>
        ) : (
          <Box data-testid="grants-table">
            {grants.map((grant) => (
              <Box
                key={grant.id}
                mb="default"
                p="default"
                style={{
                  background: "#fff",
                  border: "1px solid #dee2e6",
                  borderRadius: 4,
                  display: "flex",
                  alignItems: "center",
                  gap: 12,
                }}
                data-testid={`grant-row-${grant.id}`}
              >
                <Box style={{ flex: 1, minWidth: 0 }}>
                  <Text style={{ fontFamily: "monospace", fontSize: 13, wordBreak: "break-all" }}>
                    <strong>Recipient:</strong> {grant.recipient_agent_id}
                  </Text>
                  <Text style={{ fontSize: 12, color: "#6c757d", marginTop: 2 }}>
                    Created by {grant.created_by} · {grant.created_at}
                  </Text>
                </Box>
                <Button
                  variant="danger"
                  size="sm"
                  disabled={revoking === grant.id}
                  onClick={() => handleRevoke(grant.id)}
                  data-testid={`revoke-grant-${grant.id}`}
                >
                  {revoking === grant.id ? "Revoking…" : "Revoke"}
                </Button>
              </Box>
            ))}
          </Box>
        )}
      </Box>

      {/* Back link */}
      <Box mt="xl">
        <Button
          as="a"
          href={`/admin/resources/${resource.id}/records/${secretId}/show`}
          variant="light"
          data-testid="grants-back-link"
        >
          Back to secret
        </Button>
      </Box>
    </Box>
  );
};

export default AgentSecretGrantsPanel;
