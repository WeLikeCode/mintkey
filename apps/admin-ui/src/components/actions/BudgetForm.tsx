/**
 * BudgetForm — budget constraint create/edit action component.
 *
 * Used in two contexts:
 *   1. Create mode — embedded in permission grant `new` action (optional fields)
 *   2. Edit mode — rendered when `editBudget` custom action fires (pre-populated)
 *
 * Props (AdminJS-injected):
 *   record — the permission grant record; in edit mode, `constraints.budget.*`
 *            params carry existing budget values.
 *   resource — `{ id: "permission_grants" }`
 *   action — `{ name: "editBudget", label: "Edit Budget" }`
 *
 * Validation uses `validateBudgetInput` from utils/budget-validate.ts.
 * On valid submit: POST to `/admin/api/budget/{permId}/edit`.
 *
 * Spec: .kiro/specs/budget-management-ui
 * Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 3.1, 3.2
 */

import React, { useState } from "react";
import { Box, H3, Text, Button, Label, FormGroup } from "@adminjs/design-system";
import { validateBudgetInput } from "../utils/budget-validate.js";

// ── types ────────────────────────────────────────────────────────────────────

interface BudgetFormProps {
  record: {
    id: string | number;
    params: Record<string, unknown>;
  };
  resource: { id: string };
  action: { name: string; label: string };
  [key: string]: unknown;
}

interface BudgetFormData {
  ceiling: string;
  period: string;
  alert_thresholds: string;
}

// ── constants ────────────────────────────────────────────────────────────────

const PERIODS = ["hourly", "daily", "weekly", "monthly"] as const;
const DEFAULT_THRESHOLDS = [50, 80, 100];

// ── component ────────────────────────────────────────────────────────────────

const BudgetForm = (props: Record<string, unknown>): React.ReactElement => {
  const { record } = props as BudgetFormProps;
  const permId = String(record?.params?.id ?? record?.id ?? "");

  // Extract existing budget values for edit mode
  const existingCeiling = record?.params?.["constraints.budget.ceiling"];
  const existingPeriod = record?.params?.["constraints.budget.period"];
  const existingThresholds = record?.params?.["constraints.budget.alert_thresholds"];

  const isEditMode =
    existingCeiling !== undefined && existingCeiling !== null;

  // Format thresholds for display
  const formatThresholds = (thresholds: unknown): string => {
    if (Array.isArray(thresholds)) {
      return thresholds.join(", ");
    }
    return "";
  };

  const [formData, setFormData] = useState<BudgetFormData>({
    ceiling: isEditMode ? String(existingCeiling) : "",
    period: isEditMode ? String(existingPeriod ?? "") : "",
    alert_thresholds: isEditMode ? formatThresholds(existingThresholds) : "",
  });

  const [errors, setErrors] = useState<string[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [notice, setNotice] = useState<{
    type: "success" | "error";
    message: string;
  } | null>(null);

  // ── handlers ─────────────────────────────────────────────────────────────

  const handleChange = (
    field: keyof BudgetFormData,
    value: string
  ) => {
    setFormData((prev) => ({ ...prev, [field]: value }));
    // Clear errors on change
    if (errors.length > 0) {
      setErrors([]);
    }
  };

  const parseThresholds = (raw: string): number[] => {
    if (!raw.trim()) return [];
    return raw
      .split(",")
      .map((s) => s.trim())
      .filter((s) => s !== "")
      .map((s) => Number(s));
  };

  const handleSubmit = async () => {
    setErrors([]);
    setNotice(null);

    // Parse form values for validation
    const ceilingRaw = formData.ceiling.trim();
    const periodRaw = formData.period;
    const thresholdsRaw = formData.alert_thresholds;

    // Determine what to validate
    const ceilingValue = ceilingRaw !== "" ? Number(ceilingRaw) : undefined;
    const periodValue = periodRaw || undefined;
    const thresholdsArray = parseThresholds(thresholdsRaw);

    // Run validation
    const result = validateBudgetInput(
      ceilingValue,
      periodValue,
      thresholdsArray
    );

    if (!result.valid) {
      setErrors(result.errors);
      return;
    }

    // Build request body
    const body: {
      ceiling: number;
      period: string;
      alert_thresholds: number[];
    } = {
      ceiling: ceilingValue as number,
      period: periodValue as string,
      alert_thresholds:
        thresholdsArray.length > 0 ? thresholdsArray : DEFAULT_THRESHOLDS,
    };

    // Submit to BFF
    setSubmitting(true);
    try {
      const response = await fetch(`/admin/api/budget/${permId}/edit`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });

      if (response.ok) {
        setNotice({ type: "success", message: "Budget updated successfully" });
      } else {
        const errBody = await response.json().catch(() => null);
        const msg =
          (errBody as { title?: string })?.title ??
          `Error: ${response.status}`;
        setNotice({ type: "error", message: msg });
      }
    } catch {
      setNotice({ type: "error", message: "Network error — please try again" });
    } finally {
      setSubmitting(false);
    }
  };

  // ── render ───────────────────────────────────────────────────────────────

  return (
    <Box variant="white" p="xxl" data-testid="budget-form">
      <H3 mb="lg">{isEditMode ? "Edit Budget" : "Set Budget"}</H3>

      {notice && (
        <Box
          mb="lg"
          p="lg"
          style={{
            background: notice.type === "success" ? "#d4edda" : "#f8d7da",
            border: `1px solid ${
              notice.type === "success" ? "#c3e6cb" : "#f5c6cb"
            }`,
            borderRadius: 4,
          }}
          data-testid="budget-form-notice"
        >
          <Text>{notice.message}</Text>
        </Box>
      )}

      {errors.length > 0 && (
        <Box
          mb="lg"
          p="lg"
          style={{
            background: "#f8d7da",
            border: "1px solid #f5c6cb",
            borderRadius: 4,
          }}
          data-testid="budget-form-errors"
        >
          {errors.map((err, i) => (
            <Text key={i}>{err}</Text>
          ))}
        </Box>
      )}

      <FormGroup>
        <Label htmlFor="budget-ceiling">Ceiling (requests per period)</Label>
        <input
          id="budget-ceiling"
          type="number"
          min="1"
          step="1"
          value={formData.ceiling}
          onChange={(e) => handleChange("ceiling", e.target.value)}
          placeholder="e.g. 1000"
          data-testid="budget-field-ceiling"
        />
      </FormGroup>

      <FormGroup>
        <Label htmlFor="budget-period">Period</Label>
        <select
          id="budget-period"
          value={formData.period}
          onChange={(e) => handleChange("period", e.target.value)}
          data-testid="budget-field-period"
        >
          <option value="">— Select period —</option>
          {PERIODS.map((p) => (
            <option key={p} value={p}>
              {p.charAt(0).toUpperCase() + p.slice(1)}
            </option>
          ))}
        </select>
      </FormGroup>

      <FormGroup>
        <Label htmlFor="budget-thresholds">
          Alert Thresholds (comma-separated, 1-100)
        </Label>
        <input
          id="budget-thresholds"
          type="text"
          value={formData.alert_thresholds}
          onChange={(e) => handleChange("alert_thresholds", e.target.value)}
          placeholder="50, 80, 100"
          data-testid="budget-field-alert-thresholds"
        />
        <Text>
          Optional. Defaults to 50, 80, 100 if left empty.
        </Text>
      </FormGroup>

      <Box mt="xl" style={{ display: "flex", gap: 12 }}>
        <Button
          type="button"
          disabled={submitting}
          onClick={handleSubmit}
          data-testid="budget-form-submit"
        >
          {submitting ? "Saving…" : "Save Budget"}
        </Button>
      </Box>
    </Box>
  );
};

export default BudgetForm;
