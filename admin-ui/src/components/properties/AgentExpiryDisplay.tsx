/**
 * AgentExpiryDisplay — relative + absolute display for api_key_expires_at.
 *
 * Renders:
 *   - "Never" (gray) when api_key_expires_at is null
 *   - "Expired N days ago" (red) when past
 *   - "in N hours" / "in N days" (yellow if <7d, default otherwise) when future
 *
 * Used in both Agents list (compact) and Agents show page (expanded with absolute date).
 */
import React from "react";
// eslint-disable-next-line @typescript-eslint/ban-ts-comment
// @ts-ignore — adminjs re-exports
import { Text, Tooltip } from "@adminjs/design-system";
import { formatRelativeExpiry, type ExpiryTone } from "../../lib/key-expiry.js";

// Re-export so callers that import from this module still work
export { formatRelativeExpiry };

type Props = {
  record?: { params?: Record<string, unknown> };
  property?: { path?: string };
  variant?: "list" | "show";
};

type Tone = ExpiryTone;

const TONE_COLOR: Record<Tone, string> = {
  ok: "#28a745",
  warn: "#ffc107",
  danger: "#dc3545",
  expired: "#dc3545",
  never: "#6c757d",
};

const AgentExpiryDisplay: React.FC<Props> = ({ record, property, variant = "show" }) => {
  const path = property?.path ?? "api_key_expires_at";
  const raw = record?.params?.[path] as string | null | undefined;
  const fmt = formatRelativeExpiry(raw);
  const color = TONE_COLOR[fmt.tone];

  if (variant === "list") {
    return (
      <Tooltip direction="top" title={fmt.absolute || "No expiry set"}>
        <Text style={{ color, fontWeight: fmt.tone === "expired" || fmt.tone === "warn" ? 600 : 400 }}>
          {fmt.label}
        </Text>
      </Tooltip>
    );
  }
  return (
    <Text style={{ color, fontWeight: 600 }}>
      {fmt.label}{fmt.absolute ? ` (${fmt.absolute})` : ""}
    </Text>
  );
};

export default AgentExpiryDisplay;
