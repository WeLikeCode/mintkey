import React from "react";
// eslint-disable-next-line @typescript-eslint/ban-ts-comment
// @ts-ignore — adminjs re-exports ValueGroup
import { ValueGroup } from "@adminjs/design-system";
import { useTranslation } from "adminjs";

interface PropertyJSON {
  path: string;
  label: string;
  description?: string;
  resourceId: string;
}

interface ShowPropertyProps {
  property: PropertyJSON;
  record: { params: Record<string, unknown> };
  resource: { id: string };
}

const DescriptiveShowProperty: React.FC<ShowPropertyProps> = (props) => {
  const { property, record } = props;
  const { translateProperty, tm } = useTranslation();
  const value = record?.params?.[property.path];
  const label = translateProperty(property.label, property.resourceId);
  const description = property.description
    ? tm(property.description, property.resourceId)
    : "";

  const displayValue =
    value === null || value === undefined || value === ""
      ? "—"
      : typeof value === "object"
      ? JSON.stringify(value, null, 2)
      : String(value);

  return (
    <ValueGroup label={label}>
      <div data-testid={`show-value-${property.path}`}>{displayValue}</div>
      {description && (
        <div
          data-testid={`show-description-${property.path}`}
          style={{
            marginTop: 6,
            fontSize: 12,
            color: "#6c757d",
            fontStyle: "italic",
            lineHeight: 1.4,
            whiteSpace: "pre-wrap",
          }}
        >
          {description}
        </div>
      )}
    </ValueGroup>
  );
};

export default DescriptiveShowProperty;
