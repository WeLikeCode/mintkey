/**
 * AgentKeyRotatedNotice — hard-cutover key rotation form + show-once result screen (UX-FB-AK-2).
 *
 * Form view (before submit):
 *   - Hard-cutover warning callout (yellow)
 *   - expires_in dropdown: Never / 30 days / 90 days / 180 days / 365 days
 *   - Rotate Key (red) + Cancel (link) buttons
 *
 * Show-once result (after successful rotation):
 *   - "Previous key invalidated" warning banner (red)
 *   - New API key (monospace) + Copy API Key button
 *   - Agent ID + Copy ID button
 *   - API Key Version display
 *   - New expiry (uses formatRelativeExpiry)
 *   - "This key will not be shown again" warning
 *   - Go to agent button
 *
 * Security rules (ADR-0014.4 / S-SEC-1):
 *   - clipboard.writeText only — DO NOT auto-copy on mount
 *   - API key lives only in local state; never written to Redux or localStorage
 *   - never console.log(apiKey)
 */

import React, { useState, useEffect } from "react";
import {
  Box,
  H3,
  Text,
  Button,
  Label,
} from "@adminjs/design-system";
import { ApiClient } from "adminjs";
import { useNavigate } from "react-router-dom";
import { formatRelativeExpiry } from "../../lib/key-expiry.js";

// ── types ────────────────────────────────────────────────────────────────────

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Props = Record<string, any>;

const EXPIRES_IN_OPTIONS: { label: string; value: string | null }[] = [
  { label: "Never", value: null },
  { label: "30 days", value: "30d" },
  { label: "90 days", value: "90d" },
  { label: "180 days", value: "180d" },
  { label: "365 days", value: "365d" },
];

// ── CopyButton ───────────────────────────────────────────────────────────────

interface CopyButtonProps {
  value: string;
  testId?: string;
  label?: string;
  variant?: "primary" | "light" | "success";
}

const CopyButton = ({ value, testId, label = "Copy", variant = "light" }: CopyButtonProps): React.ReactElement => {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    if (!value) return;
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      setTimeout(() => setCopied(false), 3000);
    } catch {
      try {
        const el = document.createElement("textarea");
        el.value = value;
        document.body.appendChild(el);
        el.select();
        document.execCommand("copy");
        document.body.removeChild(el);
        setCopied(true);
        setTimeout(() => setCopied(false), 3000);
      } catch {
        // Silently fail — operator must manually select + copy
      }
    }
  };

  return (
    <Button
      variant={copied ? "success" : variant}
      size="sm"
      onClick={handleCopy}
      data-testid={testId ?? "copy-btn"}
      style={{ whiteSpace: "nowrap", flexShrink: 0 }}
    >
      {copied ? "Copied!" : label}
    </Button>
  );
};

// ── AgentKeyRotatedNotice (main component) ────────────────────────────────────

const AgentKeyRotatedNotice = (props: Props): React.ReactElement => {
  const navigate = useNavigate();

  // ── state ──────────────────────────────────────────────────────────────────
  const [expiresIn, setExpiresIn] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  // Rotation result (show-once)
  const [rotated, setRotated] = useState(false);
  const [rotatedAgentId, setRotatedAgentId] = useState("");
  const [rotatedApiKey, setRotatedApiKey] = useState("");
  const [rotatedVersion, setRotatedVersion] = useState<number | null>(null);
  const [rotatedExpiresAt, setRotatedExpiresAt] = useState<string | null>(null);

  // ── resolve agent ID ───────────────────────────────────────────────────────
  const record = props.record as { params?: Record<string, unknown>; id?: string } | undefined;
  const agentId =
    (record?.params?.["rotated_agent_id"] as string | undefined) ||
    (record?.params?.["id"] as string | undefined) ||
    (record?.id as string | undefined) ||
    (props.params?.recordId as string | undefined) ||
    "";

  const resource = props.resource as { id?: string } | undefined;

  // ── on mount: check if rotation result already in params (server-side POST return) ──
  useEffect(() => {
    const params = record?.params ?? {};
    const rotKey = params["rotated_api_key"] as string | undefined;
    const rotId = params["rotated_agent_id"] as string | undefined;

    if (rotKey && rotId) {
      setRotatedAgentId(rotId);
      setRotatedApiKey(rotKey);
      setRotatedVersion((params["rotated_api_key_version"] as number | undefined) ?? null);
      setRotatedExpiresAt((params["rotated_api_key_expires_at"] as string | undefined) ?? null);
      setRotated(true);
    }
    setLoading(false);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ── submit handler (rotate key) ────────────────────────────────────────────
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!agentId) {
      setFormError("Agent ID not found. Please reload the page.");
      return;
    }

    setSubmitting(true);
    setFormError(null);

    const api = new ApiClient();
    try {
      const payload: Record<string, unknown> = {};
      if (expiresIn !== null) {
        payload.expires_in = expiresIn;
      }
      // Send null or empty string to indicate "no expiry"
      if (expiresIn === null) {
        payload.expires_in = null;
      }

      const resp = await api.recordAction({
        resourceId: resource?.id ?? "agents",
        recordId: agentId,
        actionName: "rotateAgentKey",
        method: "post",
        data: payload,
      });

      const result = resp.data as {
        record?: { params?: Record<string, unknown> };
        notice?: { message: string; type: string };
      };

      if (result?.notice?.type === "error") {
        setFormError(result.notice.message || "Key rotation failed.");
        return;
      }

      const params = result?.record?.params ?? {};
      const rotKey = params["rotated_api_key"] as string | undefined;
      const rotId = params["rotated_agent_id"] as string | undefined;

      if (rotKey && rotId) {
        setRotatedAgentId(rotId);
        setRotatedApiKey(rotKey);
        setRotatedVersion((params["rotated_api_key_version"] as number | undefined) ?? null);
        setRotatedExpiresAt((params["rotated_api_key_expires_at"] as string | undefined) ?? null);
        setRotated(true);
        return;
      }

      setFormError("Rotation succeeded but the new key was not returned. Check the agent show page.");
    } catch (err: unknown) {
      setFormError(err instanceof Error ? err.message : "Request failed.");
    } finally {
      setSubmitting(false);
    }
  };

  // ── loading ────────────────────────────────────────────────────────────────
  if (loading) {
    return (
      <Box variant="white" p="xxl" data-testid="agent-key-rotated-notice-loading">
        <Text>Loading…</Text>
      </Box>
    );
  }

  // ── show-once result screen ────────────────────────────────────────────────
  if (rotated && rotatedAgentId) {
    const showUrl = `/admin/resources/agents/records/${rotatedAgentId}/show`;
    const expiryFmt = formatRelativeExpiry(rotatedExpiresAt);

    return (
      <Box variant="white" p="xxl" data-testid="agent-key-rotated-notice">
        {/* Invalidation warning */}
        <Box
          mb="xl"
          p="lg"
          style={{
            background: "#f8d7da",
            border: "1px solid #f5c6cb",
            borderRadius: 4,
          }}
          data-testid="agent-key-invalidated-warning"
        >
          <Text style={{ fontWeight: 600, color: "#721c24" }}>
            The previous API key has been invalidated. Update your agent runtime now — the old key will no longer authenticate.
          </Text>
        </Box>

        <H3 mb="xl">Agent API Key Rotated</H3>

        {/* Show-once warning */}
        <Box
          mb="xl"
          p="lg"
          style={{
            background: "#fff3cd",
            border: "1px solid #ffc107",
            borderRadius: 4,
          }}
          data-testid="agent-key-show-once-warning"
        >
          <Text style={{ fontWeight: 600, color: "#856404" }}>
            This key will not be shown again. Copy it now — it cannot be retrieved after you leave this page.
          </Text>
        </Box>

        {/* API Key row */}
        <Box mb="lg" data-testid="rotated-api-key-row">
          <Label style={{ display: "block", marginBottom: 4 }}>
            New API Key <span style={{ color: "#856404", fontSize: 12 }}>(shown once)</span>
          </Label>
          <Box style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <Box
              p="default"
              style={{
                background: "#f8f9fa",
                border: "2px solid #ffc107",
                borderRadius: 4,
                fontFamily: "monospace",
                fontSize: 13,
                wordBreak: "break-all",
                flex: 1,
                minWidth: 0,
              }}
              data-testid="rotated-api-key-value"
            >
              {rotatedApiKey}
            </Box>
            <CopyButton
              value={rotatedApiKey}
              testId="rotated-api-key-copy-btn"
              label="Copy API Key"
              variant="primary"
            />
          </Box>
        </Box>

        {/* Agent ID row */}
        <Box mb="lg" data-testid="rotated-agent-id-row">
          <Label style={{ display: "block", marginBottom: 4 }}>Agent ID</Label>
          <Box style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <Box
              p="default"
              style={{
                background: "#f8f9fa",
                border: "1px solid #dee2e6",
                borderRadius: 4,
                fontFamily: "monospace",
                fontSize: 13,
                wordBreak: "break-all",
                flex: 1,
                minWidth: 0,
              }}
              data-testid="rotated-agent-id-value"
            >
              {rotatedAgentId}
            </Box>
            <CopyButton
              value={rotatedAgentId}
              testId="rotated-agent-id-copy-btn"
              label="Copy ID"
            />
          </Box>
        </Box>

        {/* Version row */}
        {rotatedVersion !== null && (
          <Box mb="lg" data-testid="rotated-version-row">
            <Label style={{ display: "block", marginBottom: 4 }}>API Key Version</Label>
            <Text data-testid="rotated-version-value" style={{ fontFamily: "monospace" }}>
              Version {rotatedVersion}
            </Text>
          </Box>
        )}

        {/* Expiry row */}
        <Box mb="xl" data-testid="rotated-expiry-row">
          <Label style={{ display: "block", marginBottom: 4 }}>Expires</Label>
          <Text
            data-testid="rotated-expiry-value"
            style={{
              color: expiryFmt.tone === "expired" ? "#dc3545" : expiryFmt.tone === "warn" ? "#ffc107" : expiryFmt.tone === "never" ? "#6c757d" : "#28a745",
              fontWeight: 600,
            }}
          >
            {expiryFmt.label}{expiryFmt.absolute ? ` (${expiryFmt.absolute})` : ""}
          </Text>
        </Box>

        {/* CTA */}
        <Box flex style={{ gap: 12 }}>
          <Button
            as="a"
            href={showUrl}
            variant="primary"
            data-testid="rotated-go-to-agent-btn"
          >
            Go to agent
          </Button>
          <Button
            as="a"
            href="/admin/resources/agents"
            variant="light"
            data-testid="rotated-agents-list-btn"
          >
            Back to agents list
          </Button>
        </Box>
      </Box>
    );
  }

  // ── Rotation form (before submit) ──────────────────────────────────────────
  const cancelUrl = agentId
    ? `/admin/resources/agents/records/${agentId}/show`
    : `/admin/resources/${resource?.id ?? "agents"}`;

  return (
    <Box variant="white" p="xxl" data-testid="agent-key-rotate-form">
      <H3 mb="default">Rotate Agent API Key</H3>

      {/* Hard-cutover warning */}
      <Box
        mb="lg"
        p="lg"
        style={{
          background: "#fff3cd",
          border: "2px solid #ffc107",
          borderRadius: 4,
        }}
        data-testid="agent-key-rotate-cutover-warning"
      >
        <Text style={{ fontWeight: 700, color: "#856404" }}>
          Hard cutover: the current API key is invalidated the instant you click Rotate. Have your agent runtime ready to receive the new key.
        </Text>
      </Box>

      <form onSubmit={handleSubmit} noValidate>
        {/* expires_in dropdown */}
        <Box mb="xl" data-testid="field-expires-in">
          <Label htmlFor="agent-rotate-expires-in">New Key Expiry</Label>
          <select
            id="agent-rotate-expires-in"
            value={expiresIn ?? ""}
            onChange={(e) => {
              const val = e.target.value;
              setExpiresIn(val === "" ? null : val);
            }}
            data-testid="field-select-expires-in"
            style={{
              width: "100%",
              padding: "8px 12px",
              border: "1px solid #dee2e6",
              borderRadius: 4,
              fontSize: 14,
              boxSizing: "border-box",
            }}
          >
            {EXPIRES_IN_OPTIONS.map((opt) => (
              <option key={opt.value ?? ""} value={opt.value ?? ""}>
                {opt.label}
              </option>
            ))}
          </select>
        </Box>

        {/* Error */}
        {formError && (
          <Box
            mb="lg"
            p="lg"
            style={{
              background: "#f8d7da",
              border: "1px solid #f5c6cb",
              borderRadius: 4,
            }}
            data-testid="rotate-error"
          >
            <Text style={{ color: "#721c24" }}>{formError}</Text>
          </Box>
        )}

        {/* Buttons */}
        <Box flex style={{ gap: 12 }}>
          <Button
            type="submit"
            variant="danger"
            disabled={submitting}
            data-testid="agent-rotate-key-submit"
          >
            {submitting ? "Rotating…" : "Rotate Key"}
          </Button>
          <Button
            as="a"
            href={cancelUrl}
            variant="light"
            data-testid="agent-rotate-key-cancel"
          >
            Cancel
          </Button>
        </Box>
      </form>
    </Box>
  );
};

export default AgentKeyRotatedNotice;
