/**
 * AgentSecretNewForm — create a new agent secret (Chunk C6, D11).
 *
 * Features:
 *   1. Reads ?agent_id= from URL query params and pre-fills + locks the
 *      agent_id field (mirrors CredentialNewForm reading ?service_id=).
 *   2. Inputs: name (required), value (password/masked, required),
 *      content_type (optional, defaults to text/plain).
 *   3. On submit calls the agent-secrets resource `new` action handler
 *      (which calls apiWrite with the signed-request path).
 *   4. On success: REVEAL-ONCE panel shows the value the operator TYPED
 *      (from component state — NOT from the response, which has no value).
 *      A Copy button copies it. Dismissed by navigating away.
 *
 * Security rules (ADR-0014.4 / S-SEC-1):
 *   - value lives only in component state; never logged, never in Redux
 *   - reveal-once panel is shown exactly once per submit; navigating away
 *     discards it
 *   - clipboard.writeText only on explicit user action (no auto-copy)
 *
 * Source: Chunk C6; D11; D13; ADR-0019; ADR-0014.4.
 */

import React, { useState, useEffect } from "react";
import {
  Box,
  H3,
  Text,
  Button,
  Label,
  Input,
} from "@adminjs/design-system";
import { ApiClient } from "adminjs";
import { useSearchParams, useNavigate } from "react-router-dom";

// ── types ────────────────────────────────────────────────────────────────────

// Props injected by AdminJS for resource-type actions
// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Props = Record<string, any>;

// ── helpers ──────────────────────────────────────────────────────────────────

const inputStyle: React.CSSProperties = {
  width: "100%",
  padding: "8px 12px",
  border: "1px solid #dee2e6",
  borderRadius: 4,
  fontSize: 14,
  lineHeight: "1.5",
  boxSizing: "border-box",
};

interface FieldProps {
  id: string;
  label: string;
  required?: boolean;
  children: React.ReactNode;
}

const FieldRow = ({ id, label, required, children }: FieldProps): React.ReactElement => (
  <Box mb="default" data-testid={`field-${id}`}>
    <Label htmlFor={id} required={required}>{label}</Label>
    {children}
  </Box>
);

// ── CopyButton ───────────────────────────────────────────────────────────────

interface CopyButtonProps {
  value: string;
  testId?: string;
  label?: string;
}

const CopyButton = ({ value, testId, label = "Copy" }: CopyButtonProps): React.ReactElement => {
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
      variant={copied ? "success" : "primary"}
      size="sm"
      onClick={handleCopy}
      data-testid={testId ?? "copy-btn"}
      style={{ whiteSpace: "nowrap", flexShrink: 0 }}
    >
      {copied ? "Copied!" : label}
    </Button>
  );
};

// ── AgentSecretNewForm ───────────────────────────────────────────────────────

const AgentSecretNewForm = (props: Props): React.ReactElement => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();

  // ── agent_id — read from URL or allow manual entry ────────────────────────
  const [agentId, setAgentId] = useState("");
  const [agentIdLocked, setAgentIdLocked] = useState(false);

  // ── form fields ───────────────────────────────────────────────────────────
  const [name, setName] = useState("");
  const [value, setValue] = useState("");
  const [contentType, setContentType] = useState("");

  // ── submission state ──────────────────────────────────────────────────────
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // ── reveal-once state (D11) ───────────────────────────────────────────────
  // revealValue holds the VALUE THE OPERATOR TYPED — never from the API response.
  // Set exactly once on successful submit; cleared on unmount.
  const [revealed, setRevealed] = useState(false);
  const [revealValue, setRevealValue] = useState("");

  // ── on mount: read agent_id from URL ─────────────────────────────────────
  useEffect(() => {
    const urlAgentId = searchParams.get("agent_id");
    if (urlAgentId) {
      setAgentId(urlAgentId);
      setAgentIdLocked(true);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ── submit ────────────────────────────────────────────────────────────────
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!agentId.trim()) {
      setError("Agent ID is required.");
      return;
    }
    if (!name.trim()) {
      setError("Secret name is required.");
      return;
    }
    if (!value) {
      setError("Secret value is required.");
      return;
    }

    setSubmitting(true);
    setError(null);

    // Capture the typed value BEFORE any async call — for the reveal-once panel.
    // The API response NEVER contains the value; we show what the operator typed.
    const typedValue = value;

    const api = new ApiClient();
    try {
      const data: Record<string, string> = {
        agent_id: agentId.trim(),
        name: name.trim(),
        value: typedValue,
      };
      if (contentType.trim()) {
        data.content_type = contentType.trim();
      }

      const resp = await api.resourceAction({
        resourceId: "agent-secrets",
        actionName: "new",
        method: "post",
        data,
      });

      const result = resp.data as {
        notice?: { message: string; type: string };
        redirectUrl?: string;
      };

      if (result?.notice?.type === "error") {
        setError(result.notice.message || "Failed to create secret.");
        return;
      }

      // Success: show reveal-once panel with the VALUE THE OPERATOR TYPED.
      // Clear the form inputs so the value is not visible in the form fields.
      setValue("");
      setRevealValue(typedValue);
      setRevealed(true);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Request failed.");
    } finally {
      setSubmitting(false);
    }
  };

  // ── reveal-once panel (D11) ───────────────────────────────────────────────
  if (revealed) {
    return (
      <Box variant="white" p="xxl" data-testid="agent-secret-reveal-panel">
        {/* Warning banner */}
        <Box
          mb="xl"
          p="lg"
          style={{
            background: "#fff3cd",
            border: "1px solid #ffc107",
            borderRadius: 4,
          }}
          data-testid="secret-reveal-warning"
        >
          <Text style={{ fontWeight: 600, color: "#856404" }}>
            This secret value will not be shown again — copy it now.
            It cannot be retrieved after you leave this page.
          </Text>
        </Box>

        <H3 mb="xl">Secret Created</H3>

        {/* Secret name row */}
        <Box mb="lg" data-testid="secret-name-row">
          <Label style={{ display: "block", marginBottom: 4 }}>Secret Name</Label>
          <Box
            p="default"
            style={{
              background: "#f8f9fa",
              border: "1px solid #dee2e6",
              borderRadius: 4,
              fontFamily: "monospace",
              fontSize: 13,
            }}
            data-testid="secret-name-value"
          >
            {name}
          </Box>
        </Box>

        {/* Secret value reveal-once row */}
        <Box mb="xl" data-testid="secret-value-row">
          <Label style={{ display: "block", marginBottom: 4 }}>
            Secret Value <span style={{ color: "#856404", fontSize: 12 }}>(shown once)</span>
          </Label>
          <Box
            style={{ display: "flex", alignItems: "center", gap: 8 }}
          >
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
              data-testid="secret-reveal-value"
            >
              {revealValue}
            </Box>
            <CopyButton
              value={revealValue}
              testId="secret-reveal-copy-btn"
              label="Copy Value"
            />
          </Box>
          <Text style={{ fontSize: 12, color: "#856404", marginTop: 4 }}>
            Store this value securely. It will not be shown again.
          </Text>
        </Box>

        {/* Navigation */}
        <Box flex style={{ gap: 12 }}>
          <Button
            as="a"
            href={`/admin/resources/agent-secrets?filters.agent_id=${agentId}`}
            variant="primary"
            data-testid="secret-goto-list-btn"
          >
            View secrets for this agent
          </Button>
          <Button
            as="a"
            href="/admin/resources/agent-secrets"
            variant="light"
            data-testid="secret-list-btn"
          >
            All secrets
          </Button>
        </Box>
      </Box>
    );
  }

  // ── create form ───────────────────────────────────────────────────────────
  return (
    <Box variant="white" p="xxl" data-testid="agent-secret-new-form">
      <H3 mb="default">Create Agent Secret</H3>

      {/* Pre-fill banner */}
      {agentIdLocked && (
        <Box
          mb="lg"
          p="lg"
          style={{
            background: "#cce5ff",
            border: "1px solid #b8daff",
            borderRadius: 4,
          }}
          data-testid="secret-prefill-banner"
        >
          <Text style={{ color: "#004085" }}>
            Adding secret for agent: <strong>{agentId}</strong>
          </Text>
        </Box>
      )}

      <Text mb="xl" style={{ color: "#6c757d" }}>
        Store an encrypted secret for this agent. The value is encrypted at rest
        and shown to you exactly once after creation — copy it before leaving.
      </Text>

      <form onSubmit={handleSubmit} noValidate>
        {/* Agent ID */}
        <FieldRow id="agent_id" label="Agent ID" required>
          {agentIdLocked ? (
            <Box
              p="default"
              style={{
                background: "#e9ecef",
                border: "1px solid #dee2e6",
                borderRadius: 4,
                fontFamily: "monospace",
                fontSize: 14,
                color: "#495057",
                wordBreak: "break-all",
              }}
              data-testid="field-agent-id-locked"
            >
              {agentId}
              <input type="hidden" name="agent_id" value={agentId} />
            </Box>
          ) : (
            <Input
              id="agent_id"
              type="text"
              value={agentId}
              onChange={(e: React.ChangeEvent<HTMLInputElement>) => setAgentId(e.target.value)}
              placeholder="agent_…"
              style={inputStyle}
              data-testid="field-input-agent_id"
            />
          )}
        </FieldRow>

        {/* Name */}
        <FieldRow id="name" label="Secret Name" required>
          <Input
            id="name"
            type="text"
            value={name}
            onChange={(e: React.ChangeEvent<HTMLInputElement>) => setName(e.target.value)}
            placeholder="MY_SECRET_KEY"
            style={inputStyle}
            data-testid="field-input-name"
          />
        </FieldRow>

        {/* Value — password input (masked) */}
        <FieldRow id="value" label="Secret Value" required>
          <Input
            id="value"
            type="password"
            value={value}
            onChange={(e: React.ChangeEvent<HTMLInputElement>) => setValue(e.target.value)}
            placeholder="Enter the secret value"
            style={inputStyle}
            data-testid="field-input-value"
          />
          <Text style={{ fontSize: 12, color: "#6c757d", marginTop: 4 }}>
            Masked for security. Shown once after creation — copy it then.
          </Text>
        </FieldRow>

        {/* Content type (optional) */}
        <FieldRow id="content_type" label="Content Type (optional)">
          <Input
            id="content_type"
            type="text"
            value={contentType}
            onChange={(e: React.ChangeEvent<HTMLInputElement>) => setContentType(e.target.value)}
            placeholder="text/plain"
            style={inputStyle}
            data-testid="field-input-content_type"
          />
        </FieldRow>

        {/* Error display */}
        {error && (
          <Box
            mb="lg"
            p="lg"
            style={{
              background: "#f8d7da",
              border: "1px solid #f5c6cb",
              borderRadius: 4,
            }}
            data-testid="create-error"
          >
            <Text style={{ color: "#721c24" }}>{error}</Text>
          </Box>
        )}

        {/* Buttons */}
        <Box flex mt="xl" style={{ gap: 12 }}>
          <Button
            type="submit"
            variant="primary"
            disabled={submitting}
            data-testid="secret-new-submit"
          >
            {submitting ? "Creating…" : "Create Secret"}
          </Button>
          <Button
            as="a"
            href="/admin/resources/agent-secrets"
            variant="light"
            data-testid="secret-new-cancel"
          >
            Cancel
          </Button>
        </Box>
      </form>
    </Box>
  );
};

export default AgentSecretNewForm;
