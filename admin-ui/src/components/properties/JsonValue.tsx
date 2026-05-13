/**
 * JsonValue — Show-page renderer for JSONB / mixed-type properties.
 *
 * AdminJS's default mixed renderer iterates subProperties, which don't exist
 * for flat JSONB columns from the REST API. Instead, we render the raw value
 * as pretty-printed JSON inside a <pre> block. When the value is null,
 * undefined, or an empty object/array, we show a "—" placeholder.
 *
 * Mirrors the default Show layout: wraps in a ValueGroup for the property
 * label, then renders the value below it.
 *
 * Registered in components/index.ts as "JsonValue" and wired per property
 * via `properties.<name>.components.show` in each resource config.
 *
 * Source: fix-show-page-react-31 chunk.
 */

import React from "react";
// eslint-disable-next-line @typescript-eslint/ban-ts-comment
// @ts-ignore — adminjs re-exports ValueGroup from @adminjs/design-system
import { ValueGroup } from "@adminjs/design-system";

interface Props {
  record?: { params?: Record<string, unknown> };
  property?: { path?: string; label?: string; resourceId?: string };
}

const JsonValue: React.FC<Props> = ({ record, property }) => {
  const path = property?.path ?? "";
  const label = property?.label ?? path;
  const raw = record?.params?.[path];

  const isEmpty =
    raw === null ||
    raw === undefined ||
    (typeof raw === "object" && !Array.isArray(raw) && Object.keys(raw as Record<string, unknown>).length === 0) ||
    (Array.isArray(raw) && (raw as unknown[]).length === 0) ||
    raw === "";

  return (
    <ValueGroup label={label}>
      <pre
        style={{
          margin: 0,
          padding: "4px 8px",
          background: "#f5f5f5",
          borderRadius: 4,
          fontFamily: "monospace",
          fontSize: 13,
          whiteSpace: "pre-wrap",
          wordBreak: "break-word",
          color: isEmpty ? "#aaa" : "inherit",
        }}
      >
        {isEmpty ? "—" : JSON.stringify(raw, null, 2)}
      </pre>
    </ValueGroup>
  );
};

export default JsonValue;
