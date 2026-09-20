/**
 * AccessRequestsPage — the Requests_Review_Area (agent access requests).
 *
 * A dedicated AdminJS custom page, registered in its OWN navigation section
 * ("Requests Review") clearly separated from the Services / Agents / Permissions
 * resources (Req 4.5). Same BFF pattern as BudgetConsumersPage / budget-management-ui:
 * a React page backed by the /admin/api/access-requests BFF routes (Task 8.1),
 * NOT a DB-backed AdminJS resource (ADR-0019 — the Admin Console holds no DB
 * connection).
 *
 * Layout is in-page master/detail (AdminJS renders a single component per page):
 *   - List view: pending-first table of requests with kind, status, requesting
 *     agent, target summary, created_at, expires_at + status/kind filter controls.
 *   - Detail view (row selected): full request; for an integration proposal it
 *     renders the non-secret proposed_config PLUS empty, clearly-labelled
 *     "operator-supplied" secret input fields (Req 4.6) — never prefilled.
 *
 * Actions (Approve / Reject / Test / Finalize) are Task 8.3. This page renders
 * the action controls as DISABLED, clearly-labelled placeholders with stable
 * data-testids so 8.3 can attach behavior without restructuring the page.
 * See the ACTION SEAM markers below.
 *
 * Requirements: 4.1, 4.2, 4.5, 4.6.
 */

import React, { useState, useEffect, useCallback } from "react";
import { Box, Text, Button, H3, H4, Badge, Label } from "@adminjs/design-system";
import {
  filterRequests,
  targetSummary,
  operatorSecretFields,
  nonSecretConfigEntries,
  rejectReasonValid,
  finalizeEnabled,
  buildProposalActionBody,
  formatConnectionTestResult,
  REQUEST_KINDS,
  REQUEST_STATUSES,
  type AccessRequest,
  type RequestFilterState,
  type ConnectionTestResult,
} from "./access-requests.utils.js";

const AccessRequestsPage: React.FC = () => {
  const [records, setRecords] = useState<AccessRequest[]>([]);
  const [loadError, setLoadError] = useState(false);
  const [selected, setSelected] = useState<AccessRequest | null>(null);
  const [detailError, setDetailError] = useState(false);
  const [filters, setFilters] = useState<RequestFilterState>({
    status: "",
    kind: "",
  });

  const fetchList = useCallback(async () => {
    // Forward the active server-side filters (Req 4.1); the client filter
    // (filterRequests) mirrors them for instant feedback.
    const params = new URLSearchParams();
    if (filters.status) params.set("status", filters.status);
    if (filters.kind) params.set("kind", filters.kind);
    const qs = params.toString();
    try {
      const res = await fetch(
        `/admin/api/access-requests${qs ? `?${qs}` : ""}`,
      );
      if (res.ok) {
        const data: AccessRequest[] = await res.json();
        setRecords(data);
        setLoadError(false);
      } else {
        setLoadError(true);
      }
    } catch {
      setLoadError(true);
    }
  }, [filters.status, filters.kind]);

  useEffect(() => {
    fetchList();
  }, [fetchList]);

  const openDetail = useCallback(async (requestId: string) => {
    setDetailError(false);
    try {
      const res = await fetch(`/admin/api/access-requests/${requestId}`);
      if (res.ok) {
        const data: AccessRequest = await res.json();
        setSelected(data);
      } else {
        setDetailError(true);
      }
    } catch {
      setDetailError(true);
    }
  }, []);

  const closeDetail = useCallback(() => {
    setSelected(null);
    setDetailError(false);
  }, []);

  const handleStatusFilter = useCallback(
    (e: React.ChangeEvent<HTMLSelectElement>) => {
      setFilters((prev) => ({
        ...prev,
        status: e.target.value as RequestFilterState["status"],
      }));
    },
    [],
  );

  const handleKindFilter = useCallback(
    (e: React.ChangeEvent<HTMLSelectElement>) => {
      setFilters((prev) => ({
        ...prev,
        kind: e.target.value as RequestFilterState["kind"],
      }));
    },
    [],
  );

  // After a successful action (approve / reject / finalize) refresh the list and
  // return to it so the operator sees the updated status.
  const handleActioned = useCallback(() => {
    setSelected(null);
    setDetailError(false);
    fetchList();
  }, [fetchList]);

  // Detail view takes over the page when a request is selected.
  if (selected) {
    return (
      <AccessRequestDetail
        request={selected}
        onBack={closeDetail}
        onActioned={handleActioned}
        loadError={detailError}
      />
    );
  }

  const visible = filterRequests(records, filters);

  return (
    <Box p="xl" data-testid="access-requests-page">
      <H3>Requests Review</H3>
      <Text mb="lg" style={{ color: "#6c757d" }}>
        Agent access requests, integration proposals, and share requests awaiting
        operator review.
      </Text>

      {/* Filter bar (Req 4.1) */}
      <Box mb="lg" style={{ display: "flex", gap: 12, alignItems: "center" }}>
        <select
          data-testid="filter-status"
          value={filters.status}
          onChange={handleStatusFilter}
          style={{ padding: "6px 8px", borderRadius: 4, border: "1px solid #ccc" }}
        >
          <option value="">All statuses</option>
          {REQUEST_STATUSES.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
        <select
          data-testid="filter-kind"
          value={filters.kind}
          onChange={handleKindFilter}
          style={{ padding: "6px 8px", borderRadius: 4, border: "1px solid #ccc" }}
        >
          <option value="">All kinds</option>
          {REQUEST_KINDS.map((k) => (
            <option key={k} value={k}>
              {k}
            </option>
          ))}
        </select>
      </Box>

      {loadError && (
        <Box mb="default" data-testid="list-error">
          <Text style={{ color: "#dc3545", fontSize: 12 }}>
            Could not load requests — try again.
          </Text>
        </Box>
      )}

      {visible.length === 0 ? (
        <Box p="xl" style={{ textAlign: "center" }}>
          <Text data-testid="empty-state" style={{ color: "#6c757d", fontStyle: "italic" }}>
            No requests found
          </Text>
        </Box>
      ) : (
        <Box style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr>
                <th style={thStyle}>Kind</th>
                <th style={thStyle}>Status</th>
                <th style={thStyle}>Requesting Agent</th>
                <th style={thStyle}>Target</th>
                <th style={thStyle}>Created</th>
                <th style={thStyle}>Expires</th>
                <th style={thStyle}></th>
              </tr>
            </thead>
            <tbody>
              {visible.map((r) => (
                <tr key={r.request_id} data-testid={`row-${r.request_id}`}>
                  <td style={tdStyle}>{r.kind}</td>
                  <td style={tdStyle}>
                    <Badge variant={statusVariant(r.status)}>{r.status}</Badge>
                  </td>
                  <td style={tdStyle}>{r.requesting_agent_id}</td>
                  <td style={tdStyle}>{targetSummary(r)}</td>
                  <td style={tdStyle}>{r.created_at}</td>
                  <td style={tdStyle}>{r.expires_at}</td>
                  <td style={tdStyle}>
                    <Button
                      size="sm"
                      data-testid={`view-${r.request_id}`}
                      onClick={() => openDetail(r.request_id)}
                    >
                      View
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Box>
      )}
    </Box>
  );
};

/**
 * Detail view for a single request. Integration proposals additionally render
 * the non-secret proposed config and empty operator-supplied secret inputs
 * (Req 4.6).
 */
/**
 * Detail view for a single request. Integration proposals additionally render
 * the non-secret proposed config and empty operator-supplied secret inputs
 * (Req 4.6), and — via Task 8.3 — the functional action controls:
 *   - Approve (access / share): POST .../:id/approve with an empty body.
 *   - Reject (all kinds): POST .../:id/reject with { reason }; submission is
 *     blocked when the reason is empty/whitespace (Req 8.5).
 *   - Integration proposals additionally get editable non-secret config, a
 *     Test connection control (POST .../:id/test) that displays the
 *     Connection_Test result, and a Finalize control (POST .../:id/approve with
 *     { credential, config }) enabled only after the required secrets are
 *     supplied (Req 6.8).
 *
 * The operator-typed secret is held in component state ONLY to drive the
 * finalize guard + request body; it is never prefilled, never persisted, and
 * never echoed back (Req 6.1). It leaves the page only inside the test/approve
 * request body, which the BFF forwards without logging (Task 8.1).
 */
const AccessRequestDetail: React.FC<{
  request: AccessRequest;
  onBack: () => void;
  onActioned: () => void;
  loadError: boolean;
}> = ({ request, onBack, onActioned, loadError }) => {
  const isIntegration = request.kind === "integration";
  const secretFields = operatorSecretFields(request);
  const configEntries = nonSecretConfigEntries(request);

  // Operator-typed secret values (never prefilled — Req 6.1/4.6). Keyed by field name.
  const [secretValues, setSecretValues] = useState<Record<string, string>>({});
  // Editable non-secret config, seeded from the proposed values (Req 6.2).
  const [editedConfig, setEditedConfig] = useState<Record<string, string>>(() =>
    Object.fromEntries(configEntries),
  );
  // Reject reason (Req 8.5).
  const [reason, setReason] = useState("");
  // Connection_Test result (Req 6.8).
  const [testResult, setTestResult] = useState<ConnectionTestResult | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const reasonOk = rejectReasonValid(reason);
  const finalizeOk = finalizeEnabled(request, secretValues);

  const setSecret = useCallback((name: string, value: string) => {
    setSecretValues((prev) => ({ ...prev, [name]: value }));
  }, []);

  const setConfig = useCallback((key: string, value: string) => {
    setEditedConfig((prev) => ({ ...prev, [key]: value }));
  }, []);

  // Approve an access / share request (empty body).
  const handleApprove = useCallback(async () => {
    setActionError(null);
    setBusy(true);
    try {
      const res = await fetch(
        `/admin/api/access-requests/${request.request_id}/approve`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({}),
        },
      );
      if (res.ok) {
        onActioned();
      } else {
        setActionError("Approve failed — please try again.");
      }
    } catch {
      setActionError("Approve failed — please try again.");
    } finally {
      setBusy(false);
    }
  }, [request.request_id, onActioned]);

  // Reject with a reason — guarded to block empty/whitespace (Req 8.5).
  const handleReject = useCallback(async () => {
    if (!reasonOk) {
      setActionError("A reason is required to reject a request.");
      return;
    }
    setActionError(null);
    setBusy(true);
    try {
      const res = await fetch(
        `/admin/api/access-requests/${request.request_id}/reject`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ reason }),
        },
      );
      if (res.ok) {
        onActioned();
      } else {
        setActionError("Reject failed — please try again.");
      }
    } catch {
      setActionError("Reject failed — please try again.");
    } finally {
      setBusy(false);
    }
  }, [request.request_id, reason, reasonOk, onActioned]);

  // Test connection (integration) — sends operator secret + edited config, shows result.
  const handleTest = useCallback(async () => {
    setActionError(null);
    setTestResult(null);
    setBusy(true);
    try {
      const body = buildProposalActionBody(request, secretValues, editedConfig);
      const res = await fetch(
        `/admin/api/access-requests/${request.request_id}/test`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        },
      );
      if (res.ok) {
        const data: ConnectionTestResult = await res.json();
        setTestResult(data);
      } else {
        setActionError("Test connection failed — please try again.");
      }
    } catch {
      setActionError("Test connection failed — please try again.");
    } finally {
      setBusy(false);
    }
  }, [request, secretValues, editedConfig]);

  // Finalize (integration) — approve with { credential, config }; guarded on secrets (Req 6.8).
  const handleFinalize = useCallback(async () => {
    if (!finalizeOk) return;
    setActionError(null);
    setBusy(true);
    try {
      const body = buildProposalActionBody(request, secretValues, editedConfig);
      const res = await fetch(
        `/admin/api/access-requests/${request.request_id}/approve`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        },
      );
      if (res.ok) {
        onActioned();
      } else {
        setActionError("Finalize failed — please try again.");
      }
    } catch {
      setActionError("Finalize failed — please try again.");
    } finally {
      setBusy(false);
    }
  }, [request, secretValues, editedConfig, finalizeOk, onActioned]);

  return (
    <Box p="xl" data-testid="access-request-detail">
      <Button size="sm" variant="light" onClick={onBack} data-testid="detail-back">
        ← Back to list
      </Button>

      <H3 mt="lg">Request {request.request_id}</H3>

      {loadError && (
        <Box mb="default" data-testid="detail-error">
          <Text style={{ color: "#dc3545", fontSize: 12 }}>
            Could not refresh this request.
          </Text>
        </Box>
      )}

      {/* Core fields */}
      <Box mt="default" style={{ display: "grid", gridTemplateColumns: "180px 1fr", gap: 6 }}>
        <DetailRow label="Kind" value={request.kind} />
        <DetailRow label="Status" value={request.status} testid="detail-status" />
        <DetailRow label="Requesting agent" value={request.requesting_agent_id} />
        {request.service_id && <DetailRow label="Service" value={request.service_id} />}
        {request.action && <DetailRow label="Action" value={request.action} />}
        {request.target_agent_id && (
          <DetailRow label="Target agent" value={request.target_agent_id} />
        )}
        {request.share_direction && (
          <DetailRow label="Share direction" value={request.share_direction} />
        )}
        <DetailRow label="Created" value={request.created_at} />
        <DetailRow label="Expires" value={request.expires_at} />
        {request.reason && <DetailRow label="Reject reason" value={request.reason} />}
      </Box>

      {/* Integration proposal: EDITABLE non-secret config + empty operator-supplied secrets (Req 4.6, 6.2) */}
      {isIntegration && (
        <Box mt="xl" data-testid="integration-detail">
          <H4>Proposed configuration (non-secret)</H4>
          {configEntries.length === 0 ? (
            <Text style={{ color: "#6c757d", fontStyle: "italic" }}>
              No non-secret config provided.
            </Text>
          ) : (
            configEntries.map(([k]) => (
              <Box key={k} mb="default" data-testid={`config-${k}`}>
                <Label>{k}</Label>
                <input
                  data-testid={`config-input-${k}`}
                  type="text"
                  value={editedConfig[k] ?? ""}
                  onChange={(e) => setConfig(k, e.target.value)}
                  style={{
                    width: "100%",
                    padding: "6px 8px",
                    borderRadius: 4,
                    border: "1px solid #ccc",
                  }}
                />
              </Box>
            ))
          )}

          <H4 mt="xl">Operator-supplied secrets</H4>
          <Text mb="default" style={{ color: "#6c757d", fontSize: 12 }}>
            These fields are intentionally blank. The requesting agent never
            supplies secret material — enter it here at approval time. Values are
            sent to the credential store and are never stored on the request.
          </Text>
          {secretFields.length === 0 ? (
            <Text data-testid="no-secret-fields" style={{ color: "#6c757d", fontStyle: "italic" }}>
              This auth scheme needs no operator secret.
            </Text>
          ) : (
            secretFields.map((f) => (
              <Box key={f.name} mb="default" data-testid={`secret-field-${f.name}`}>
                <Label>
                  {f.label}{" "}
                  <Text as="span" style={{ color: "#6c757d", fontWeight: 400 }}>
                    (operator-supplied)
                  </Text>
                </Label>
                {f.type === "textarea" ? (
                  <textarea
                    data-testid={`secret-input-${f.name}`}
                    placeholder={f.placeholder ?? ""}
                    // Controlled but never prefilled: value starts "" (Req 6.1/4.6).
                    value={secretValues[f.name] ?? ""}
                    onChange={(e) => setSecret(f.name, e.target.value)}
                    rows={4}
                    style={{
                      width: "100%",
                      padding: "6px 8px",
                      borderRadius: 4,
                      border: "1px solid #ccc",
                      fontFamily: "monospace",
                    }}
                  />
                ) : (
                  <input
                    data-testid={`secret-input-${f.name}`}
                    type="password"
                    placeholder={f.placeholder ?? ""}
                    value={secretValues[f.name] ?? ""}
                    onChange={(e) => setSecret(f.name, e.target.value)}
                    style={{
                      width: "100%",
                      padding: "6px 8px",
                      borderRadius: 4,
                      border: "1px solid #ccc",
                    }}
                  />
                )}
              </Box>
            ))
          )}

          {/* Connection_Test result (Req 6.8) */}
          {testResult && (
            <Box
              mt="default"
              data-testid="test-result"
              style={{
                padding: "8px 12px",
                borderRadius: 4,
                background: testResult.ok ? "#d4edda" : "#f8d7da",
                color: testResult.ok ? "#155724" : "#721c24",
                fontSize: 13,
              }}
            >
              {formatConnectionTestResult(testResult)}
            </Box>
          )}
        </Box>
      )}

      {/* Reject reason (Req 8.5) — required to reject any request kind. */}
      <Box mt="xl" data-testid="reject-reason-box">
        <Label>Reject reason</Label>
        <textarea
          data-testid="reject-reason"
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          rows={2}
          placeholder="Required if rejecting — explain why."
          style={{
            width: "100%",
            padding: "6px 8px",
            borderRadius: 4,
            border: "1px solid #ccc",
          }}
        />
      </Box>

      {actionError && (
        <Box mt="default" data-testid="action-error">
          <Text style={{ color: "#dc3545", fontSize: 12 }}>{actionError}</Text>
        </Box>
      )}

      {/* ─────────────────────────────────────────────────────────────────────
          ACTION CONTROLS (Task 8.3). Same data-testids as the 8.2 seam so the
          render test's expectations swap from "disabled" to functional.
          ───────────────────────────────────────────────────────────────────── */}
      <Box
        mt="xl"
        data-testid="action-seam"
        style={{ display: "flex", gap: 12, borderTop: "1px solid #dee2e6", paddingTop: 16 }}
      >
        {/* Approve applies to access + share; integrations finalize instead. */}
        {!isIntegration && (
          <Button
            data-testid="action-approve"
            variant="primary"
            disabled={busy}
            onClick={handleApprove}
          >
            Approve
          </Button>
        )}
        <Button
          data-testid="action-reject"
          variant="danger"
          disabled={busy || !reasonOk}
          onClick={handleReject}
        >
          Reject
        </Button>
        {isIntegration && (
          <>
            <Button
              data-testid="action-test"
              variant="light"
              disabled={busy}
              onClick={handleTest}
            >
              Test connection
            </Button>
            <Button
              data-testid="action-finalize"
              variant="primary"
              disabled={busy || !finalizeOk}
              onClick={handleFinalize}
            >
              Finalize
            </Button>
          </>
        )}
      </Box>
    </Box>
  );
};

const DetailRow: React.FC<{ label: string; value: string; testid?: string }> = ({
  label,
  value,
  testid,
}) => (
  <>
    <Text style={{ fontWeight: 600, color: "#495057" }}>{label}</Text>
    <Text data-testid={testid} style={{ wordBreak: "break-word" }}>
      {value}
    </Text>
  </>
);

function statusVariant(
  status: AccessRequest["status"],
): "success" | "danger" | "default" | "info" {
  switch (status) {
    case "approved":
      return "success";
    case "rejected":
    case "expired":
      return "danger";
    case "pending":
      return "info";
    default:
      return "default";
  }
}

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

export default AccessRequestsPage;
