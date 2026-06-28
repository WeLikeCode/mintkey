/**
 * BudgetConsumersPage — live table of all budget-configured permission grants
 * ranked by consumption percentage with inline unlock (reset) for exhausted budgets.
 *
 * Polls `/admin/api/budget-consumers` every 30s. Client-side filtering via
 * `filterConsumers`. Red highlight + "Unlock" button on exhausted rows.
 *
 * Requirements: 4.1-4.4, 5.1-5.4, 6.1-6.5, 7.1-7.4, 8.1-8.2
 */

import React, { useState, useEffect, useCallback, useRef } from "react";
import { Box, Text, Button, H3 } from "@adminjs/design-system";
import {
  filterConsumers,
  isExhausted,
  type BudgetConsumerRecord,
  type FilterState,
} from "./budget-consumers.utils.js";

const POLL_INTERVAL_MS = 30_000;

const BudgetConsumersPage: React.FC = () => {
  const [records, setRecords] = useState<BudgetConsumerRecord[]>([]);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [stale, setStale] = useState(false);
  const [filters, setFilters] = useState<FilterState>({
    threshold: null,
    agentName: "",
    serviceName: "",
  });
  const [unlockError, setUnlockError] = useState<Record<string, string>>({});
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchData = useCallback(async () => {
    try {
      const res = await fetch("/admin/api/budget-consumers");
      if (res.ok) {
        const data: BudgetConsumerRecord[] = await res.json();
        setRecords(data);
        setLastUpdated(new Date());
        setStale(false);
      } else {
        setStale(true);
      }
    } catch {
      setStale(true);
    }
  }, []);

  useEffect(() => {
    fetchData();
    intervalRef.current = setInterval(fetchData, POLL_INTERVAL_MS);
    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
      }
    };
  }, [fetchData]);

  const handleUnlock = useCallback(
    async (permId: string) => {
      setUnlockError((prev) => {
        const next = { ...prev };
        delete next[permId];
        return next;
      });

      try {
        const res = await fetch(`/admin/api/budget/${permId}/reset`, {
          method: "POST",
        });
        if (res.ok) {
          await fetchData();
        } else {
          const msg =
            res.status === 404
              ? "Budget not found — may have been removed"
              : "Reset failed — try again";
          setUnlockError((prev) => ({ ...prev, [permId]: msg }));
        }
      } catch {
        setUnlockError((prev) => ({
          ...prev,
          [permId]: "Reset failed — try again",
        }));
      }
    },
    [fetchData],
  );

  const handleThresholdChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const val = e.target.value;
      setFilters((prev) => ({
        ...prev,
        threshold: val === "" ? null : Number(val),
      }));
    },
    [],
  );

  const handleAgentNameChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      setFilters((prev) => ({ ...prev, agentName: e.target.value }));
    },
    [],
  );

  const handleServiceNameChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      setFilters((prev) => ({ ...prev, serviceName: e.target.value }));
    },
    [],
  );

  const filteredRecords = filterConsumers(records, filters);

  return (
    <Box p="xl">
      <H3>Budget Consumers</H3>

      {/* Filter Bar */}
      <Box mb="lg" style={{ display: "flex", gap: 12, alignItems: "center" }}>
        <input
          data-testid="filter-threshold"
          type="number"
          placeholder="Threshold %"
          value={filters.threshold ?? ""}
          onChange={handleThresholdChange}
          style={{ padding: "6px 8px", borderRadius: 4, border: "1px solid #ccc" }}
        />
        <input
          data-testid="filter-agent-name"
          type="text"
          placeholder="Agent name"
          value={filters.agentName}
          onChange={handleAgentNameChange}
          style={{ padding: "6px 8px", borderRadius: 4, border: "1px solid #ccc" }}
        />
        <input
          data-testid="filter-service-name"
          type="text"
          placeholder="Service name"
          value={filters.serviceName}
          onChange={handleServiceNameChange}
          style={{ padding: "6px 8px", borderRadius: 4, border: "1px solid #ccc" }}
        />
      </Box>

      {/* Last Updated */}
      <Box mb="default">
        <Text
          data-testid="last-updated"
          style={{ fontSize: 12, color: stale ? "#dc3545" : "#6c757d" }}
        >
          {lastUpdated
            ? `Last updated: ${lastUpdated.toLocaleTimeString()}${stale ? " (stale)" : ""}`
            : "Last updated: loading..."}
        </Text>
      </Box>

      {/* Empty State */}
      {filteredRecords.length === 0 ? (
        <Box p="xl" style={{ textAlign: "center" }}>
          <Text style={{ color: "#6c757d", fontStyle: "italic" }}>
            No budget-configured grants found
          </Text>
        </Box>
      ) : (
        /* Data Table */
        <Box style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr>
                <th style={thStyle}>Agent Name</th>
                <th style={thStyle}>Service</th>
                <th style={thStyle}>Consumption %</th>
                <th style={thStyle}>Used</th>
                <th style={thStyle}>Ceiling</th>
                <th style={thStyle}>Period</th>
                <th style={thStyle}>Requests 30 min</th>
                <th style={thStyle}></th>
              </tr>
            </thead>
            <tbody>
              {filteredRecords.map((record) => {
                const exhausted = isExhausted(record);
                return (
                  <tr
                    key={record.permission_id}
                    data-testid={`row-${record.permission_id}`}
                    data-exhausted={String(exhausted)}
                    style={{
                      backgroundColor: exhausted ? "#f8d7da" : undefined,
                    }}
                  >
                    <td style={tdStyle}>{record.agent_name}</td>
                    <td style={tdStyle}>{record.service_name}</td>
                    <td style={tdStyle}>{record.consumption_percentage}%</td>
                    <td style={tdStyle}>{record.used}</td>
                    <td style={tdStyle}>{record.ceiling}</td>
                    <td style={tdStyle}>{record.period}</td>
                    <td style={tdStyle}>{record.requests_last_30_min}</td>
                    <td style={tdStyle}>
                      {exhausted && (
                        <Button
                          data-testid="unlock-btn"
                          size="sm"
                          onClick={() => handleUnlock(record.permission_id)}
                        >
                          Unlock
                        </Button>
                      )}
                      {unlockError[record.permission_id] && (
                        <Text
                          style={{
                            color: "#dc3545",
                            fontSize: 11,
                            marginTop: 4,
                          }}
                        >
                          {unlockError[record.permission_id]}
                        </Text>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </Box>
      )}
    </Box>
  );
};

const thStyle: React.CSSProperties = {
  textAlign: "left",
  padding: "8px 12px",
  borderBottom: "2px solid #dee2e6",
  fontSize: 13,
  fontWeight: 600,
  color: "#495057",
};

const tdStyle: React.CSSProperties = {
  padding: "8px 12px",
  borderBottom: "1px solid #dee2e6",
  fontSize: 13,
};

export default BudgetConsumersPage;
