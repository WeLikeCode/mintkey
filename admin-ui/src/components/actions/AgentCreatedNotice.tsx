/**
 * AgentCreatedNotice — show-once agent API key screen (OPS-DDEE DD-2).
 *
 * Rendered as the `new` action component for the Agents resource after a
 * successful agent creation. Displays:
 *   1. Agent ID (with Copy button)
 *   2. API key in a monospace code block with a prominent Copy button
 *   3. Warning: "This API key will not be shown again — copy it now."
 *   4. "Go to agent" button → navigates to the agent show page
 *
 * Security rules (ADR-0014.4 / S-SEC-1):
 *   - clipboard.writeText only — DO NOT auto-copy on mount
 *   - API key lives only in local state; never written to Redux or localStorage
 *   - never console.log(apiKey)
 *
 * Data flow:
 *   The agents `new` handler embeds { agentId, apiKey } in record.params
 *   (keyed as "created_agent_id" and "created_api_key") so this component
 *   can read them after the POST resolves. Falls back to parsing the legacy
 *   notice message (bracket form "[<id>]") when the params approach isn't
 *   available.
 *
 * Visual pattern mirrors ApiKeyCreate ShowOnceModal + Dashboard McpConfigModal.
 *
 * Source: OPS-DDEE DD-2; ADR-0014.4; S-SEC-1.
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

// ── types ────────────────────────────────────────────────────────────────────

// Props injected by AdminJS for resource actions
// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Props = Record<string, any>;

// ── helpers ──────────────────────────────────────────────────────────────────

/**
 * Parse agent_id + api_key out of the legacy notice message format:
 *   "Agent created [<agent_id>]. API key (shown once): <key>"
 */
function parseNoticeMessage(msg: string): { agentId: string; apiKey: string } {
  const idMatch = msg.match(/\[([^\]]+)\]/);
  const keyMatch = msg.match(/API key \(shown once\)[^:]*:\s*(\S+)/i);
  return {
    agentId: idMatch ? idMatch[1] : "",
    apiKey: keyMatch ? keyMatch[1] : "",
  };
}

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
      // Fallback: execCommand (deprecated but supported in some browser contexts)
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
      variant={copied ? "success" : "light"}
      size="sm"
      onClick={handleCopy}
      data-testid={testId ?? "copy-btn"}
      style={{ whiteSpace: "nowrap", flexShrink: 0 }}
    >
      {copied ? "Copied!" : label}
    </Button>
  );
};

// ── AgentCreatedNotice (main component) ─────────────────────────────────────

const AgentCreatedNotice = (props: Props): React.ReactElement => {
  const navigate = useNavigate();

  // ── state ──────────────────────────────────────────────────────────────────
  const [agentId, setAgentId] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  // Form fields (for the create form before submission)
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [rateLimitRps, setRateLimitRps] = useState("");
  const [expiresIn, setExpiresIn] = useState<string | null>(null);

  // Whether creation has already happened (show-once screen)
  const [created, setCreated] = useState(false);

  // ── on mount: check if we already have record.params with the key ──────────
  useEffect(() => {
    const record = props.record as {
      params?: Record<string, unknown>;
    } | undefined;

    const createdId = record?.params?.["created_agent_id"] as string | undefined;
    const createdKey = record?.params?.["created_api_key"] as string | undefined;

    if (createdId && createdKey) {
      setAgentId(createdId);
      setApiKey(createdKey);
      setCreated(true);
    }
    setLoading(false);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ── submit handler (create agent) ─────────────────────────────────────────
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) {
      setFormError("Agent name is required.");
      return;
    }

    setSubmitting(true);
    setFormError(null);

    const resource = props.resource as { id?: string } | undefined;

    const api = new ApiClient();
    try {
      const data: Record<string, unknown> = { name: name.trim() };
      if (description.trim()) data.description = description.trim();
      if (rateLimitRps.trim()) data.rate_limit_rps = Number(rateLimitRps);
      if (expiresIn !== null) data.expires_in = expiresIn;

      const resp = await api.resourceAction({
        resourceId: resource?.id ?? "agents",
        actionName: "new",
        method: "post",
        data,
      });

      const result = resp.data as {
        record?: { params?: Record<string, unknown> };
        notice?: { message: string; type: string };
        redirectUrl?: string;
      };

      if (result?.notice?.type === "error") {
        setFormError(result.notice.message || "Failed to create agent.");
        return;
      }

      // Extract from record.params (DD-2 approach)
      const params = result?.record?.params ?? {};
      const createdId = params["created_agent_id"] as string | undefined;
      const createdKey = params["created_api_key"] as string | undefined;

      if (createdId && createdKey) {
        setAgentId(createdId);
        setApiKey(createdKey);
        setCreated(true);
        return;
      }

      // Fallback: parse from legacy notice message
      const msg = result?.notice?.message ?? "";
      if (msg) {
        const parsed = parseNoticeMessage(msg);
        if (parsed.agentId && parsed.apiKey) {
          setAgentId(parsed.agentId);
          setApiKey(parsed.apiKey);
          setCreated(true);
          return;
        }
        // If no key but we got an ID, redirect to show page
        if (parsed.agentId) {
          navigate(`/admin/resources/agents/records/${parsed.agentId}/show`);
          return;
        }
      }

      // Fallback: extract from redirectUrl
      const redirect = result?.redirectUrl ?? "";
      const idFromUrl = redirect.match(/records\/([^/]+)\/show/)?.[1] ?? "";
      if (idFromUrl) {
        // No api_key in response — navigate directly
        navigate(`/admin/resources/agents/records/${idFromUrl}/show`);
      } else {
        navigate("/admin/resources/agents");
      }
    } catch (err: unknown) {
      setFormError(err instanceof Error ? err.message : "Request failed.");
    } finally {
      setSubmitting(false);
    }
  };

  // ── loading state ──────────────────────────────────────────────────────────
  if (loading) {
    return (
      <Box variant="white" p="xxl" data-testid="agent-created-notice-loading">
        <Text>Loading…</Text>
      </Box>
    );
  }

  // ── success / show-once state ──────────────────────────────────────────────
  if (created && agentId) {
    const showUrl = `/admin/resources/agents/records/${agentId}/show`;

    return (
      <Box variant="white" p="xxl" data-testid="agent-created-notice">
        {/* Warning banner */}
        <Box
          mb="xl"
          p="lg"
          style={{
            background: "#fff3cd",
            border: "1px solid #ffc107",
            borderRadius: 4,
          }}
          data-testid="agent-key-warning"
        >
          <Text style={{ fontWeight: 600, color: "#856404" }}>
            This API key will not be shown again — copy it now.
            It cannot be retrieved after you leave this page.
          </Text>
        </Box>

        <H3 mb="xl">Agent Created</H3>

        {/* Agent ID row */}
        <Box mb="lg" data-testid="agent-id-row">
          <Label style={{ display: "block", marginBottom: 4 }}>Agent ID</Label>
          <Box
            style={{ display: "flex", alignItems: "center", gap: 8 }}
          >
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
              data-testid="agent-id-value"
            >
              {agentId}
            </Box>
            <CopyButton
              value={agentId}
              testId="agent-id-copy-btn"
              label="Copy ID"
            />
          </Box>
        </Box>

        {/* API key row */}
        <Box mb="xl" data-testid="agent-api-key-row">
          <Label style={{ display: "block", marginBottom: 4 }}>
            API Key <span style={{ color: "#856404", fontSize: 12 }}>(shown once)</span>
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
              data-testid="agent-api-key-value"
            >
              {apiKey}
            </Box>
            <Button
              variant="primary"
              size="sm"
              onClick={async () => {
                if (!apiKey) return;
                try {
                  await navigator.clipboard.writeText(apiKey);
                } catch {
                  try {
                    const el = document.createElement("textarea");
                    el.value = apiKey;
                    document.body.appendChild(el);
                    el.select();
                    document.execCommand("copy");
                    document.body.removeChild(el);
                  } catch {
                    // silently fail
                  }
                }
              }}
              data-testid="agent-api-key-copy-btn"
              style={{ whiteSpace: "nowrap", flexShrink: 0 }}
            >
              Copy API Key
            </Button>
          </Box>
          <Text style={{ fontSize: 12, color: "#856404", marginTop: 4 }}>
            Store this key securely. It will not be shown again.
          </Text>
        </Box>

        {/* CTA */}
        <Box flex style={{ gap: 12 }}>
          <Button
            as="a"
            href={showUrl}
            variant="primary"
            data-testid="agent-go-to-agent-btn"
          >
            Go to agent
          </Button>
          <Button
            as="a"
            href="/admin/resources/agents"
            variant="light"
            data-testid="agent-list-btn"
          >
            Back to agents list
          </Button>
        </Box>
      </Box>
    );
  }

  // ── Error state (component loaded in show-once context but no key) ─────────
  if (error) {
    return (
      <Box variant="white" p="xxl" data-testid="agent-created-notice-error">
        <Box
          mb="lg"
          p="lg"
          style={{
            background: "#f8d7da",
            border: "1px solid #f5c6cb",
            borderRadius: 4,
          }}
        >
          <Text style={{ color: "#721c24" }}>{error}</Text>
        </Box>
        <Button as="a" href="/admin/resources/agents" variant="light">
          Back to agents list
        </Button>
      </Box>
    );
  }

  // ── Create form (initial state — no agent created yet) ─────────────────────
  // This form renders on GET (before submission).
  // After submission, the handler returns created_agent_id/api_key in params,
  // and useEffect picks them up to show the success screen.
  const resource = props.resource as { id?: string } | undefined;

  return (
    <Box variant="white" p="xxl" data-testid="agent-create-form">
      <H3 mb="default">Create Agent</H3>
      <Text mb="xl" style={{ color: "#6c757d" }}>
        Create a new agent. The API key is shown exactly once — copy it before leaving this page.
      </Text>

      <form onSubmit={handleSubmit} noValidate>
        {/* Name */}
        <Box mb="default" data-testid="field-name">
          <Label htmlFor="agent-name" required>Name</Label>
          <input
            id="agent-name"
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="my-agent"
            required
            data-testid="field-input-name"
            style={{
              width: "100%",
              padding: "8px 12px",
              border: "1px solid #dee2e6",
              borderRadius: 4,
              fontSize: 14,
              boxSizing: "border-box",
            }}
          />
        </Box>

        {/* Description */}
        <Box mb="default" data-testid="field-description">
          <Label htmlFor="agent-description">Description</Label>
          <textarea
            id="agent-description"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Optional description"
            rows={3}
            data-testid="field-input-description"
            style={{
              width: "100%",
              padding: "8px 12px",
              border: "1px solid #dee2e6",
              borderRadius: 4,
              fontSize: 14,
              boxSizing: "border-box",
              resize: "vertical",
            }}
          />
        </Box>

        {/* Key expiry */}
        <Box mb="default" data-testid="field-expires-in">
          <Label htmlFor="agent-expires-in">API Key Expiry</Label>
          <select
            id="agent-expires-in"
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
            <option value="">Never</option>
            <option value="30d">30 days</option>
            <option value="90d">90 days</option>
            <option value="180d">180 days</option>
            <option value="365d">365 days</option>
          </select>
        </Box>

        {/* Rate limit */}
        <Box mb="xl" data-testid="field-rate-limit">
          <Label htmlFor="agent-rate-limit-rps">Rate limit (req/s, blank = no limit)</Label>
          <input
            id="agent-rate-limit-rps"
            type="number"
            value={rateLimitRps}
            onChange={(e) => setRateLimitRps(e.target.value)}
            placeholder="leave blank for no limit"
            min={0}
            data-testid="field-input-rate-limit-rps"
            style={{
              width: "100%",
              padding: "8px 12px",
              border: "1px solid #dee2e6",
              borderRadius: 4,
              fontSize: 14,
              boxSizing: "border-box",
            }}
          />
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
            data-testid="create-error"
          >
            <Text style={{ color: "#721c24" }}>{formError}</Text>
          </Box>
        )}

        {/* Buttons */}
        <Box flex style={{ gap: 12 }}>
          <Button
            type="submit"
            variant="primary"
            disabled={submitting}
            data-testid="agent-create-submit"
          >
            {submitting ? "Creating…" : "Create Agent"}
          </Button>
          <Button
            as="a"
            href={`/admin/resources/${resource?.id ?? "agents"}`}
            variant="light"
            data-testid="agent-create-cancel"
          >
            Cancel
          </Button>
        </Box>
      </form>
    </Box>
  );
};

export default AgentCreatedNotice;
