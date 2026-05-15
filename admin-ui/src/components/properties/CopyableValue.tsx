/**
 * CopyableValue — show-page property component (OPS-X).
 *
 * Renders a value with a "Copy" button. Used for the proxy_url virtual property
 * on the service show page.
 *
 * Props: receives `record` from AdminJS (property components get the full record
 * context) and `property` for metadata. The actual value is computed in
 * services.ts and passed via record.params.proxy_url.
 *
 * Source: OPS-SUX chunk X; UX-CLARITY I (held).
 */

import React, { useState } from "react";
import {
  Box,
  Text,
  Button,
  Label,
} from "@adminjs/design-system";

// ── types ────────────────────────────────────────────────────────────────────

interface PropertyInterface {
  label?: string;
  description?: string;
  path?: string;
}

interface RecordInterface {
  params?: Record<string, unknown>;
}

interface CopyableValueProps {
  property?: PropertyInterface;
  record?: RecordInterface;
  // For direct usage outside of AdminJS property context:
  value?: string;
  label?: string;
  description?: string;
}

// ── CopyableValue ─────────────────────────────────────────────────────────────

const CopyableValue = (props: CopyableValueProps): React.ReactElement => {
  const { property, record } = props;

  // Value comes from record.params[property.path] when used as AdminJS property component
  const path = property?.path ?? "proxy_url";
  const value =
    props.value ??
    (record?.params?.[path] as string | undefined) ??
    "";
  const label = props.label ?? property?.label ?? path;
  const description = props.description ?? property?.description;

  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    if (!value) return;
    navigator.clipboard
      .writeText(value)
      .then(() => {
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
      })
      .catch(() => {
        // Fallback: select the text manually in a textarea
        const el = document.createElement("textarea");
        el.value = value;
        document.body.appendChild(el);
        el.select();
        document.execCommand("copy");
        document.body.removeChild(el);
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
      });
  };

  return (
    <Box mb="default" data-testid="copyable-value">
      {label && (
        <Label style={{ display: "block", marginBottom: 4 }}>
          {label}
        </Label>
      )}

      <Box
        style={{
          display: "flex",
          alignItems: "center",
          gap: 8,
          flexWrap: "wrap",
        }}
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
          data-testid="copyable-value-text"
        >
          {value || <span style={{ color: "#6c757d", fontStyle: "italic" }}>(no value)</span>}
        </Box>

        {value && (
          <Button
            variant={copied ? "success" : "light"}
            size="sm"
            onClick={handleCopy}
            data-testid="copyable-value-copy-btn"
            style={{ whiteSpace: "nowrap", flexShrink: 0 }}
          >
            {copied ? "Copied!" : "Copy"}
          </Button>
        )}
      </Box>

      {description && (
        <Text
          style={{ fontSize: 12, color: "#6c757d", marginTop: 4 }}
          data-testid="copyable-value-description"
        >
          {description}
        </Text>
      )}
    </Box>
  );
};

export default CopyableValue;
