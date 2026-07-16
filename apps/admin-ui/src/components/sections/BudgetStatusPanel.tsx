/**
 * BudgetStatusPanel — show-page panel for budget status on a permission grant.
 *
 * Rendered as a property.components.show override on a virtual `_budgetPanel`
 * property placed on the permission grant show page (AdminJS 7.x pattern).
 *
 * Surfaces to the operator:
 *   1. Progress bar showing used / ceiling with percentage label.
 *   2. Threshold markers positioned at each alert_threshold percentage.
 *   3. Period info (type + start/end in human-readable format).
 *   4. Exhaustion indicator (red when used >= ceiling).
 *   5. Action buttons: Edit Budget, Reset Budget, Remove Budget.
 *   6. Empty state: "No budget configured" when API returns 404.
 *   7. Error state: "Unable to load budget status" with retry on 5xx.
 *
 * Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6
 */

import React, { useState, useEffect, useCallback } from "react";
import { Box, Text, Button } from "@adminjs/design-system";
// eslint-disable-next-line @typescript-eslint/ban-ts-comment
// @ts-ignore — adminjs re-exports ValueGroup from @adminjs/design-system
import { ValueGroup } from "@adminjs/design-system";
import { formatPeriod } from "../utils/budget-format.js";

// ── types ────────────────────────────────────────────────────────────────────

interface BudgetStatus {
  ceiling: number;
  period: "hourly" | "daily" | "weekly" | "monthly";
  used: number;
  remaining: number;
  period_start: string;
  period_end: string;
  alert_thresholds: number[];
}

interface Props {
  record?: {
    id?: string | number;
    params?: Record<string, unknown>;
  };
  property?: { path?: string; label?: string };
}

type State =
  | { kind: "loading" }
  | { kind: "loaded"; data: BudgetStatus }
  | { kind: "empty" }
  | { kind: "error" };

// ── component ─────────────────────────────────────────────────────────────────

const BudgetStatusPanel: React.FC<Props> = ({ record, property }) => {
  const label = property?.label ?? "Budget Status";
  const permId = (record?.params?.id ?? record?.id ?? "") as string;

  const [state, setState] = useState<State>({ kind: "loading" });

  const fetchBudget = useCallback(async () => {
    if (!permId) {
      setState({ kind: "empty" });
      return;
    }

    setState({ kind: "loading" });

    try {
      const res = await fetch(`/admin/api/budget/${permId}`);

      if (res.status === 404) {
        setState({ kind: "empty" });
        return;
      }

      if (!res.ok) {
        setState({ kind: "error" });
        return;
      }

      const data: BudgetStatus = await res.json();
      setState({ kind: "loaded", data });
    } catch {
      setState({ kind: "error" });
    }
  }, [permId]);

  useEffect(() => {
    fetchBudget();
  }, [fetchBudget]);

  // ── empty state ─────────────────────────────────────────────────────────

  if (state.kind === "empty") {
    return (
      <ValueGroup label={label}>
        <Box data-testid="budget-empty-state" p="default">
          <Text style={{ color: "#6c757d", fontStyle: "italic" }}>
            No budget configured
          </Text>
        </Box>
      </ValueGroup>
    );
  }

  // ── error state ─────────────────────────────────────────────────────────

  if (state.kind === "error") {
    return (
      <ValueGroup label={label}>
        <Box data-testid="budget-error-state" p="default">
          <Text style={{ color: "#dc3545", marginBottom: 8 }}>
            Unable to load budget status
          </Text>
          <Button
            data-testid="budget-retry-btn"
            onClick={fetchBudget}
          >
            Retry
          </Button>
        </Box>
      </ValueGroup>
    );
  }

  // ── loading state ───────────────────────────────────────────────────────

  if (state.kind === "loading") {
    return (
      <ValueGroup label={label}>
        <Box data-testid="budget-loading" p="default">
          <Text style={{ color: "#6c757d" }}>Loading budget...</Text>
        </Box>
      </ValueGroup>
    );
  }

  // ── loaded state ────────────────────────────────────────────────────────

  const { data } = state;
  const percentage = Math.round((data.used / data.ceiling) * 100);
  const isExhausted = data.used >= data.ceiling;

  return (
    <ValueGroup label={label}>
      <Box data-testid="budget-status-panel" mb="xl">
        {/* ── Progress bar ───────────────────────────────────────────── */}
        <Box mb="default">
          <Box
            data-testid="budget-progress-bar"
            data-percentage={String(percentage)}
            data-exhausted={String(isExhausted)}
            style={{
              position: "relative",
              height: 24,
              background: "#e9ecef",
              borderRadius: 4,
              overflow: "visible",
            }}
          >
            {/* Fill bar */}
            <Box
              style={{
                position: "absolute",
                top: 0,
                left: 0,
                height: "100%",
                width: `${Math.min(percentage, 100)}%`,
                background: isExhausted ? "#dc3545" : "#28a745",
                borderRadius: 4,
                transition: "width 0.3s ease",
              }}
            />

            {/* Threshold markers */}
            {data.alert_thresholds.map((threshold) => (
              <Box
                key={threshold}
                data-testid={`budget-threshold-marker-${threshold}`}
                style={{
                  position: "absolute",
                  left: `${threshold}%`,
                  top: 0,
                  height: "100%",
                  width: 2,
                  background: "#6c757d",
                  opacity: 0.7,
                }}
              />
            ))}
          </Box>

          {/* Usage text and percentage */}
          <Box style={{ display: "flex", justifyContent: "space-between", marginTop: 4 }}>
            <Text data-testid="budget-usage-text" style={{ fontSize: 12, color: "#495057" }}>
              {data.used} / {data.ceiling}
            </Text>
            <Text
              data-testid="budget-percentage-label"
              style={{ fontSize: 12, fontWeight: "bold", color: isExhausted ? "#dc3545" : "#495057" }}
            >
              {percentage}%
            </Text>
          </Box>
        </Box>

        {/* ── Period info ─────────────────────────────────────────────── */}
        <Box mb="default">
          <Text data-testid="budget-period-info" style={{ fontSize: 13, color: "#495057" }}>
            {formatPeriod(data.period, data.period_start, data.period_end)}
          </Text>
        </Box>

        {/* ── Action buttons ─────────────────────────────────────────── */}
        <Box style={{ display: "flex", gap: 8 }}>
          <Button data-testid="budget-btn-edit">
            Edit Budget
          </Button>
          <Button
            data-testid="budget-btn-reset"
            onClick={async () => {
              if (!window.confirm("Reset budget counter to zero? The agent can resume operations immediately.")) return;
              try {
                const res = await fetch(`/admin/api/budget/${permId}/reset`, { method: "POST" });
                if (res.ok) {
                  fetchBudget();
                }
              } catch {
                // Network error — silent; user can retry
              }
            }}
          >
            Reset Budget
          </Button>
          <Button
            data-testid="budget-btn-remove"
            onClick={async () => {
              if (!window.confirm("Remove budget constraint? The agent will revert to unlimited calls.")) return;
              try {
                const res = await fetch(`/admin/api/budget/${permId}/remove`, { method: "POST" });
                if (res.ok) {
                  setState({ kind: "empty" });
                }
              } catch {
                // Network error — silent; user can retry
              }
            }}
          >
            Remove Budget
          </Button>
        </Box>
      </Box>
    </ValueGroup>
  );
};

export default BudgetStatusPanel;
