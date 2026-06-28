/**
 * Pure utility functions for the Budget Consumers Dashboard.
 *
 * Source: budget-consumers-dashboard spec; Requirements 5.1–5.4, 6.1, 6.5, 8.1, 8.2.
 */

export interface BudgetConsumerRecord {
  permission_id: string;
  agent_id: string;
  agent_name: string;
  service_id: string;
  service_name: string;
  consumption_percentage: number;
  used: number;
  ceiling: number;
  period: "hourly" | "daily" | "weekly" | "monthly";
  period_start: string | null;
  period_end: string | null;
  requests_last_30_min: number;
}

export interface FilterState {
  threshold: number | null;
  agentName: string;
  serviceName: string;
}

/**
 * Filters budget consumer records by threshold, agent name, and service name.
 * All active filters are applied as logical AND.
 *
 * - threshold: show only rows where consumption_percentage > threshold
 * - agentName: case-insensitive substring match on agent_name
 * - serviceName: case-insensitive substring match on service_name
 */
export function filterConsumers(
  records: BudgetConsumerRecord[],
  filters: FilterState,
): BudgetConsumerRecord[] {
  return records.filter((r) => {
    if (filters.threshold != null && r.consumption_percentage <= filters.threshold) return false;
    if (filters.agentName && !r.agent_name.toLowerCase().includes(filters.agentName.toLowerCase()))
      return false;
    if (
      filters.serviceName &&
      !r.service_name.toLowerCase().includes(filters.serviceName.toLowerCase())
    )
      return false;
    return true;
  });
}

/**
 * Returns true if the budget is exhausted (used >= ceiling).
 */
export function isExhausted(record: BudgetConsumerRecord): boolean {
  return record.used >= record.ceiling;
}
