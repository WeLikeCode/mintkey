/**
 * AgentSecretUpdateForm — rotate an agent secret value (Chunk C6b).
 *
 * Features:
 *   1. Displays the secret name read-only for context.
 *   2. Input: new value (password/masked, required) + optional content_type.
 *   3. On submit calls the agent-secrets resource `editValue` action handler
 *      (which calls apiWrite PUT with the signed-request path).
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
 * Source: Chunk C6b; D11; ADR-0019; ADR-0014.4.
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

// ── types ────────────────────────────────────────────────────────────────────

interface AgentSecretUpdateFormProps {
  record: {
    id: string | number;
    params: Record<string, unknown>;
    errors?: Record<string, unknown>;
  };
  resource: { id: string };
  action: { name: string; label: string };
  [key: string]: unknown;
}

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

// ── AgentSecretUpdateForm ────────────────────────────────────────────────────

const AgentSecretUpdateForm = (props: Record<string, unknown>): React.ReactElement => {
  const { record, resource, action } = props as AgentSecretUpdateFormProps;

  const secretName = (record?.params?.name as string | undefined) ?? "";
  const secretId = String(record?.id ?? "");

  // ── form fields ───────────────────────────────────────────────────────────
  const [value, setValue] = useState("");
  const [contentType, setContentType] = useState(
    (record?.params?.content_type as string | undefined) ?? ""
  );

  // ── submission state ──────────────────────────────────────────────────────
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // ── reveal-once state ─────────────────────────────────────────────────────
  // revealValue holds the VALUE THE OPERATOR TYPED — never from the API response.
  // Set exactly once on successful submit; cleared on unmount.
  const [revealed, setRevealed] = useState(false);
  const [revealValue, setRevealValue] = useState("");

  // ── submit ────────────────────────────────────────────────────────────────
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!value) {
      setError("New secret value is required.");
      return;
    }

    setSubmitting(true);
    setError(null);

    // Capture the typed value BEFORE any async call — for the reveal-once panel.
    // The API response NEVER contains the value; we show what the operator typed.
    const typedValue = value;

    const api = new ApiClient();
    try {
      const data: Record<string, string> = { value: typedValue };
      if (contentType.trim()) {
        data.content_type = contentType.trim();
      }

      const resp = await api.recordAction({
        resourceId: resource.id,
        recordId: String(secretId),
        actionName: action.name,
        method: "post",
        data,
      });

      const result = resp.data as {
        notice?: { message: string; type: string };
      };

      if (result?.notice?.type === "error") {
        setError(result.notice.message || "Failed to update secret.");
        return;
      }

      // Success: show reveal-once panel with the VALUE THE OPERATOR TYPED.
      // Clear the form value input so it is not visible in form fields.
      setValue("");
      setRevealValue(typedValue);
      setRevealed(true);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Request failed.");
    } finally {
      setSubmitting(false);
    }
  };

  // ── reveal-once panel ─────────────────────────────────────────────────────
  if (revealed) {
    return (
      <Box variant="white" p="xxl" data-testid="agent-secret-update-reveal-panel">
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
            The new secret value will not be shown again — copy it now.
            It cannot be retrieved after you leave this page.
          </Text>
        </Box>

        <H3 mb="xl">Secret Value Rotated</H3>

        {/* Secret name row */}
        <Box mb="lg">
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
            data-testid="secret-name-reveal"
          >
            {secretName}
          </Box>
        </Box>

        {/* New secret value reveal-once row */}
        <Box mb="xl" data-testid="secret-value-row">
          <Label style={{ display: "block", marginBottom: 4 }}>
            New Secret Value <span style={{ color: "#856404", fontSize: 12 }}>(shown once)</span>
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
            href={`/admin/resources/${resource.id}/records/${secretId}/show`}
            variant="primary"
            data-testid="secret-back-btn"
          >
            Back to Secret
          </Button>
          <Button
            as="a"
            href={`/admin/resources/${resource.id}`}
            variant="light"
            data-testid="secret-list-btn"
          >
            All Secrets
          </Button>
        </Box>
      </Box>
    );
  }

  // ── rotate form ───────────────────────────────────────────────────────────
  return (
    <Box variant="white" p="xxl" data-testid="agent-secret-update-form">
      <H3 mb="default">Rotate Secret Value</H3>

      <Text mb="xl" style={{ color: "#6c757d" }}>
        Replace the encrypted value for this secret. The new value is shown once
        after rotation — copy it before leaving.
      </Text>

      {/* Secret name — read-only context */}
      <Box
        mb="xl"
        p="lg"
        style={{
          background: "#f8f9fa",
          border: "1px solid #dee2e6",
          borderRadius: 4,
        }}
      >
        <Label style={{ display: "block", marginBottom: 4 }}>Secret Name</Label>
        <Text
          style={{ fontFamily: "monospace", fontSize: 14, color: "#495057", wordBreak: "break-all" }}
          data-testid="secret-name-display"
        >
          {secretName}
        </Text>
      </Box>

      <form onSubmit={handleSubmit} noValidate>
        {/* New value — password input (masked) */}
        <FieldRow id="value" label="New Secret Value" required>
          <Input
            id="value"
            type="password"
            value={value}
            onChange={(e: React.ChangeEvent<HTMLInputElement>) => setValue(e.target.value)}
            placeholder="Enter the new secret value"
            style={inputStyle}
            data-testid="field-input-value"
          />
          <Text style={{ fontSize: 12, color: "#6c757d", marginTop: 4 }}>
            Masked for security. Shown once after rotation — copy it then.
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
            data-testid="update-error"
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
            data-testid="secret-update-submit"
          >
            {submitting ? "Rotating…" : "Rotate Secret"}
          </Button>
          <Button
            as="a"
            href={`/admin/resources/${resource.id}/records/${secretId}/show`}
            variant="light"
            data-testid="secret-update-cancel"
          >
            Cancel
          </Button>
        </Box>
      </form>
    </Box>
  );
};

export default AgentSecretUpdateForm;
