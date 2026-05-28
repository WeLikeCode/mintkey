/**
 * ServiceTemplatePicker — enhanced resource action component (OPS-S).
 *
 * Fetches /admin/api/resources/services/actions/template-list (BFF passthrough)
 * on mount and renders a template catalog with:
 *   - Category grouping with collapsible sections
 *   - Search input filtering by name/display_name/description (case-insensitive)
 *   - Template detail panel showing config_notes and version
 *   - Pre-fill service registration form on template selection
 *   - Submit calls POST /v1/tenants/{tid}/services/from-template
 *
 * Requirements: 17.1, 17.2, 17.3, 17.4
 * Source: OPS-S; service-templates spec task 12.1.
 */

import React, { useEffect, useState, useMemo } from "react";
import {
  Box,
  H3,
  Text,
  Button,
  Input,
  Label,
} from "@adminjs/design-system";
import { ApiClient } from "adminjs";
import { useNavigate } from "react-router-dom";

// ── types ────────────────────────────────────────────────────────────────────

interface ServiceTemplate {
  template_id: string;
  slug?: string;
  name: string;
  display_name: string;
  description?: string;
  base_url?: string;
  auth_type?: string;
  auth_scheme?: string;
  openapi_spec_url?: string;
  openapi_url?: string;
  category?: string;
  version?: string;
  config_notes?: string | null;
  credential_hint?: Record<string, unknown> | null;
  test_path?: string;
}

// Props injected by AdminJS for resource-type actions
// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Props = Record<string, any>;

// ── Category display names ───────────────────────────────────────────────────

const CATEGORY_LABELS: Record<string, string> = {
  ci_cd: "CI/CD",
  app_store: "App Stores",
  platform: "Platform",
  search: "Search",
  communications: "Communications",
  payments: "Payments",
  infrastructure: "Infrastructure",
  observability: "Observability",
  incident_management: "Incident Management",
};

function getCategoryLabel(category: string): string {
  return CATEGORY_LABELS[category] ?? category.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

// ── styles ───────────────────────────────────────────────────────────────────

const searchInputStyle: React.CSSProperties = {
  width: "100%",
  padding: "10px 14px",
  border: "1px solid #dee2e6",
  borderRadius: 4,
  fontSize: 14,
  lineHeight: "1.5",
  boxSizing: "border-box",
};

const overrideInputStyle: React.CSSProperties = {
  width: "100%",
  padding: "8px 12px",
  border: "1px solid #dee2e6",
  borderRadius: 4,
  fontSize: 14,
  lineHeight: "1.5",
  boxSizing: "border-box",
};

// ── ServiceTemplatePicker ─────────────────────────────────────────────────────

const ServiceTemplatePicker = (_props: Props): React.ReactElement => {
  const navigate = useNavigate();

  const [templates, setTemplates] = useState<ServiceTemplate[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Search state
  const [searchTerm, setSearchTerm] = useState("");

  // Collapsed categories state (tracks which categories are collapsed)
  const [collapsedCategories, setCollapsedCategories] = useState<Set<string>>(new Set());

  // Selected template for detail panel
  const [selectedTemplate, setSelectedTemplate] = useState<ServiceTemplate | null>(null);

  // Override fields for the selected template
  type OverrideFields = {
    name: string;
    display_name: string;
    description: string;
    base_url: string;
  };
  const [overrides, setOverrides] = useState<OverrideFields>({ name: "", display_name: "", description: "", base_url: "" });

  // Submission state
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitSuccess, setSubmitSuccess] = useState<{ serviceId: string } | null>(null);

  // ── Fetch templates on mount ───────────────────────────────────────────────
  useEffect(() => {
    const api = new ApiClient();
    api
      .resourceAction({
        resourceId: "services",
        actionName: "template-list",
        method: "get",
      })
      .then((resp) => {
        const data = resp.data as {
          templates?: ServiceTemplate[];
          record?: { params?: { templates?: ServiceTemplate[] } };
        };
        const list =
          data?.templates ??
          data?.record?.params?.templates ??
          [];
        setTemplates(Array.isArray(list) ? list : []);
      })
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : "Failed to load templates");
      })
      .finally(() => setLoading(false));
  }, []);

  // ── Filter templates by search term ────────────────────────────────────────
  const filteredTemplates = useMemo(() => {
    if (!searchTerm.trim()) return templates;
    const term = searchTerm.toLowerCase().trim();
    return templates.filter((tpl: ServiceTemplate) => {
      const name = (tpl.name ?? "").toLowerCase();
      const displayName = (tpl.display_name ?? "").toLowerCase();
      const description = (tpl.description ?? "").toLowerCase();
      return name.includes(term) || displayName.includes(term) || description.includes(term);
    });
  }, [templates, searchTerm]);

  // ── Group templates by category ────────────────────────────────────────────
  const groupedTemplates = useMemo(() => {
    const groups: Record<string, ServiceTemplate[]> = {};
    for (const tpl of filteredTemplates) {
      const cat = tpl.category ?? "other";
      if (!groups[cat]) groups[cat] = [];
      groups[cat].push(tpl);
    }
    // Sort categories alphabetically by label
    const sorted = Object.entries(groups).sort(([a], [b]) =>
      getCategoryLabel(a).localeCompare(getCategoryLabel(b))
    );
    return sorted;
  }, [filteredTemplates]);

  // ── Toggle category collapse ───────────────────────────────────────────────
  const toggleCategory = (category: string) => {
    setCollapsedCategories((prev: Set<string>) => {
      const next = new Set(prev);
      if (next.has(category)) {
        next.delete(category);
      } else {
        next.add(category);
      }
      return next;
    });
  };

  // ── Select a template ──────────────────────────────────────────────────────
  const selectTemplate = (tpl: ServiceTemplate) => {
    setSelectedTemplate(tpl);
    setOverrides({
      name: tpl.name ?? "",
      display_name: tpl.display_name ?? "",
      description: tpl.description ?? "",
      base_url: tpl.base_url ?? "",
    });
    setSubmitError(null);
    setSubmitSuccess(null);
  };

  // ── Clear selection ────────────────────────────────────────────────────────
  const clearSelection = () => {
    setSelectedTemplate(null);
    setOverrides({ name: "", display_name: "", description: "", base_url: "" });
    setSubmitError(null);
    setSubmitSuccess(null);
  };

  // ── Submit: call POST /v1/tenants/{tid}/services/from-template ─────────────
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedTemplate) return;

    setSubmitting(true);
    setSubmitError(null);

    const templateId = selectedTemplate.template_id ?? selectedTemplate.slug ?? selectedTemplate.name;

    // Build overrides — only include fields that differ from template defaults
    const overridePayload: Record<string, string> = {};
    if (overrides.name && overrides.name !== selectedTemplate.name) {
      overridePayload.name = overrides.name;
    }
    if (overrides.display_name && overrides.display_name !== selectedTemplate.display_name) {
      overridePayload.display_name = overrides.display_name;
    }
    if (overrides.description && overrides.description !== (selectedTemplate.description ?? "")) {
      overridePayload.description = overrides.description;
    }
    if (overrides.base_url && overrides.base_url !== (selectedTemplate.base_url ?? "")) {
      overridePayload.base_url = overrides.base_url;
    }

    const body: { template_id: string; overrides?: Record<string, string> } = {
      template_id: templateId,
    };
    if (Object.keys(overridePayload).length > 0) {
      body.overrides = overridePayload;
    }

    const api = new ApiClient();
    try {
      const resp = await api.resourceAction({
        resourceId: "services",
        actionName: "from-template",
        method: "post",
        data: body,
      });

      const data = resp.data as {
        service?: { id?: string };
        record?: { params?: { service_id?: string } };
        notice?: { message: string; type: string };
        redirectUrl?: string;
      };

      if (data?.notice?.type === "error") {
        setSubmitError(data.notice.message || "Failed to create service from template.");
        return;
      }

      const serviceId =
        data?.service?.id ??
        data?.record?.params?.service_id ??
        "";

      if (serviceId) {
        setSubmitSuccess({ serviceId });
      } else if (data?.redirectUrl) {
        navigate(data.redirectUrl);
      } else {
        // BUG-7a: no id and no redirectUrl means the response was unexpected — show error
        // instead of a false-success green banner.
        setSubmitError("Service creation returned an unexpected response. Please retry or contact support.");
      }
    } catch (err: unknown) {
      setSubmitError(err instanceof Error ? err.message : "Failed to create service from template.");
    } finally {
      setSubmitting(false);
    }
  };

  // ── Navigate to manual registration ────────────────────────────────────────
  const skipTemplate = () => {
    navigate("/admin/resources/services/actions/new");
  };

  // ── Navigate to pre-filled form (legacy path) ──────────────────────────────
  const useTemplateInForm = (slug: string) => {
    navigate(`/admin/resources/services/actions/new?template=${encodeURIComponent(slug)}`);
  };

  // ── Success state ──────────────────────────────────────────────────────────
  if (submitSuccess) {
    const showUrl = submitSuccess.serviceId
      ? `/admin/resources/services/records/${submitSuccess.serviceId}/show`
      : "/admin/resources/services";

    return (
      <Box variant="white" p="xxl" data-testid="template-submit-success">
        <Box
          mb="lg"
          p="lg"
          style={{
            background: "#d4edda",
            border: "1px solid #c3e6cb",
            borderRadius: 4,
          }}
        >
          <Text style={{ fontWeight: 600, color: "#155724" }}>
            Service created from template successfully.
          </Text>
        </Box>
        <Box flex style={{ gap: 12 }}>
          {submitSuccess.serviceId && (
            <Button
              as="a"
              href={showUrl}
              variant="primary"
              data-testid="view-service-btn"
            >
              View service
            </Button>
          )}
          <Button
            variant="light"
            onClick={() => {
              setSubmitSuccess(null);
              clearSelection();
            }}
            data-testid="create-another-btn"
          >
            Create another
          </Button>
        </Box>
      </Box>
    );
  }

  return (
    <Box variant="white" p="xxl" data-testid="service-template-picker">
      <H3 mb="default">Create from Template</H3>
      <Text mb="xl" style={{ color: "#6c757d" }}>
        Pick a template to pre-fill the service form, or create a service directly
        from a template. Credential values are never pre-filled — you will supply
        those after the service is created.
      </Text>

      {/* ── Loading state ──────────────────────────────────────────────── */}
      {loading && (
        <Text data-testid="template-loading" style={{ color: "#6c757d" }}>
          Loading templates…
        </Text>
      )}

      {/* ── Error state ────────────────────────────────────────────────── */}
      {error && (
        <Box
          mb="lg"
          p="lg"
          style={{ background: "#f8d7da", border: "1px solid #f5c6cb", borderRadius: 4 }}
          data-testid="template-error"
        >
          <Text style={{ color: "#721c24" }}>{error}</Text>
        </Box>
      )}

      {/* ── Empty state ────────────────────────────────────────────────── */}
      {!loading && !error && templates.length === 0 && (
        <Text style={{ color: "#6c757d" }} data-testid="template-empty">
          No templates available.
        </Text>
      )}

      {/* ── Main content: search + grouped catalog + detail panel ──────── */}
      {!loading && templates.length > 0 && (
        <Box style={{ display: "flex", gap: 24, alignItems: "flex-start" }}>
          {/* ── Left panel: search + category groups ──────────────────── */}
          <Box style={{ flex: "1 1 0%", minWidth: 0 }}>
            {/* ── Search input ──────────────────────────────────────────── */}
            <Box mb="lg" data-testid="template-search-box">
              <Input
                id="template-search"
                value={searchTerm}
                onChange={(e: React.ChangeEvent<HTMLInputElement>) => setSearchTerm(e.target.value)}
                placeholder="Search templates by name or description…"
                style={searchInputStyle}
                data-testid="template-search-input"
              />
            </Box>

            {/* ── No results ────────────────────────────────────────────── */}
            {filteredTemplates.length === 0 && searchTerm.trim() !== "" && (
              <Text style={{ color: "#6c757d" }} data-testid="template-no-results">
                No templates match &ldquo;{searchTerm}&rdquo;.
              </Text>
            )}

            {/* ── Category groups ───────────────────────────────────────── */}
            <Box data-testid="template-card-grid">
            {groupedTemplates.map(([category, categoryTemplates]: [string, ServiceTemplate[]]) => {
              const isCollapsed = collapsedCategories.has(category);
              return (
                <Box
                  key={category}
                  mb="lg"
                  data-testid={`template-category-${category}`}
                >
                  {/* Category header (collapsible) */}
                  <Box
                    style={{
                      display: "flex",
                      alignItems: "center",
                      cursor: "pointer",
                      padding: "8px 0",
                      borderBottom: "1px solid #dee2e6",
                      marginBottom: isCollapsed ? 0 : 12,
                      userSelect: "none",
                    }}
                    onClick={() => toggleCategory(category)}
                    data-testid={`template-category-header-${category}`}
                  >
                    <Text
                      style={{
                        fontWeight: 600,
                        fontSize: 14,
                        color: "#495057",
                        flex: 1,
                      }}
                    >
                      {getCategoryLabel(category)} ({categoryTemplates.length})
                    </Text>
                    <Text style={{ fontSize: 12, color: "#6c757d" }}>
                      {isCollapsed ? "▶" : "▼"}
                    </Text>
                  </Box>

                  {/* Template cards within category */}
                  {!isCollapsed && (
                    <Box
                      style={{
                        display: "grid",
                        gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))",
                        gap: 12,
                      }}
                      data-testid={`template-category-cards-${category}`}
                    >
                      {categoryTemplates.map((tpl: ServiceTemplate) => {
                        // BUG-19: match on stable template_id only — name fallback caused
                        // two templates with the same name to both highlight.
                        const isSelected = selectedTemplate?.template_id === tpl.template_id;
                        return (
                          <Box
                            key={tpl.template_id ?? tpl.name}
                            p="lg"
                            style={{
                              border: isSelected
                                ? "2px solid #0d6efd"
                                : "1px solid #dee2e6",
                              borderRadius: 6,
                              background: isSelected ? "#f0f7ff" : "#fff",
                              cursor: "pointer",
                              transition: "border-color 0.15s ease, background 0.15s ease",
                            }}
                            onClick={() => selectTemplate(tpl)}
                            data-testid={`template-card-${tpl.template_id ?? tpl.name}`}
                          >
                            <Text
                              style={{ fontWeight: 600, fontSize: 14, marginBottom: 4 }}
                            >
                              {tpl.display_name ?? tpl.name}
                            </Text>

                            {tpl.description && (
                              <Text
                                style={{
                                  fontSize: 12,
                                  color: "#6c757d",
                                  marginBottom: 6,
                                  display: "-webkit-box",
                                  WebkitLineClamp: 2,
                                  WebkitBoxOrient: "vertical",
                                  overflow: "hidden",
                                }}
                              >
                                {tpl.description}
                              </Text>
                            )}

                            <Box style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                              {(tpl.auth_type ?? tpl.auth_scheme) && (
                                <Box
                                  style={{
                                    display: "inline-block",
                                    background: "#e9ecef",
                                    borderRadius: 3,
                                    padding: "2px 6px",
                                    fontSize: 11,
                                    fontFamily: "monospace",
                                  }}
                                >
                                  {tpl.auth_type ?? tpl.auth_scheme}
                                </Box>
                              )}
                              {tpl.version && (
                                <Box
                                  style={{
                                    display: "inline-block",
                                    background: "#e2e3e5",
                                    borderRadius: 3,
                                    padding: "2px 6px",
                                    fontSize: 11,
                                    fontFamily: "monospace",
                                  }}
                                >
                                  v{tpl.version}
                                </Box>
                              )}
                            </Box>
                          </Box>
                        );
                      })}
                    </Box>
                  )}
                </Box>
              );
            })}
            </Box>
          </Box>

          {/* ── Right panel: template detail + overrides + submit ──────── */}
          {selectedTemplate && (
            <Box
              style={{
                flex: "0 0 380px",
                border: "1px solid #dee2e6",
                borderRadius: 6,
                background: "#f8f9fa",
                padding: 20,
                position: "sticky",
                top: 20,
                maxHeight: "calc(100vh - 120px)",
                overflowY: "auto",
              }}
              data-testid="template-detail-panel"
            >
              <Box style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 12 }}>
                <H3 style={{ fontSize: 16, margin: 0 }}>
                  {selectedTemplate.display_name ?? selectedTemplate.name}
                </H3>
                <Button
                  variant="light"
                  size="sm"
                  onClick={clearSelection}
                  data-testid="template-detail-close"
                  style={{ padding: "2px 8px", fontSize: 12 }}
                >
                  ✕
                </Button>
              </Box>

              {/* Version */}
              {selectedTemplate.version && (
                <Text style={{ fontSize: 12, color: "#6c757d", marginBottom: 8 }}>
                  Version: {selectedTemplate.version}
                </Text>
              )}

              {/* Description */}
              {selectedTemplate.description && (
                <Text style={{ fontSize: 13, color: "#495057", marginBottom: 12 }}>
                  {selectedTemplate.description}
                </Text>
              )}

              {/* Config notes */}
              {selectedTemplate.config_notes && (
                <Box
                  mb="default"
                  p="default"
                  style={{
                    background: "#fff3cd",
                    border: "1px solid #ffc107",
                    borderRadius: 4,
                    fontSize: 12,
                    color: "#856404",
                  }}
                  data-testid="template-config-notes"
                >
                  <Text style={{ fontWeight: 600, fontSize: 11, marginBottom: 4 }}>
                    Configuration Notes
                  </Text>
                  <Text style={{ fontSize: 12 }}>{selectedTemplate.config_notes}</Text>
                </Box>
              )}

              {/* Base URL */}
              {selectedTemplate.base_url && (
                <Text
                  style={{
                    fontSize: 12,
                    fontFamily: "monospace",
                    color: "#495057",
                    marginBottom: 8,
                    wordBreak: "break-all",
                  }}
                >
                  {selectedTemplate.base_url}
                </Text>
              )}

              {/* Auth type */}
              {(selectedTemplate.auth_type ?? selectedTemplate.auth_scheme) && (
                <Text style={{ fontSize: 12, color: "#6c757d", marginBottom: 16 }}>
                  Auth: {selectedTemplate.auth_type ?? selectedTemplate.auth_scheme}
                </Text>
              )}

              {/* ── Override form ──────────────────────────────────────── */}
              <Box
                style={{ borderTop: "1px solid #dee2e6", paddingTop: 16, marginTop: 8 }}
              >
                <Text style={{ fontWeight: 600, fontSize: 13, marginBottom: 12 }}>
                  Customize before creating
                </Text>

                <form onSubmit={handleSubmit} noValidate>
                  <Box mb="default">
                    <Label htmlFor="override-name" style={{ fontSize: 12 }}>Name</Label>
                    <input
                      id="override-name"
                      value={overrides.name}
                      onChange={(e) => setOverrides((prev) => ({ ...prev, name: e.target.value }))}
                      style={overrideInputStyle}
                      data-testid="override-name"
                    />
                  </Box>

                  <Box mb="default">
                    <Label htmlFor="override-display_name" style={{ fontSize: 12 }}>Display Name</Label>
                    <input
                      id="override-display_name"
                      value={overrides.display_name}
                      onChange={(e) => setOverrides((prev) => ({ ...prev, display_name: e.target.value }))}
                      style={overrideInputStyle}
                      data-testid="override-display_name"
                    />
                  </Box>

                  <Box mb="default">
                    <Label htmlFor="override-base_url" style={{ fontSize: 12 }}>Base URL</Label>
                    <input
                      id="override-base_url"
                      value={overrides.base_url}
                      onChange={(e) => setOverrides((prev) => ({ ...prev, base_url: e.target.value }))}
                      style={overrideInputStyle}
                      data-testid="override-base_url"
                    />
                  </Box>

                  <Box mb="lg">
                    <Label htmlFor="override-description" style={{ fontSize: 12 }}>Description</Label>
                    <textarea
                      id="override-description"
                      value={overrides.description}
                      onChange={(e) => setOverrides((prev) => ({ ...prev, description: e.target.value }))}
                      style={{ ...overrideInputStyle, minHeight: 60, resize: "vertical" }}
                      data-testid="override-description"
                    />
                  </Box>

                  {/* Submit error */}
                  {submitError && (
                    <Box
                      mb="default"
                      p="default"
                      style={{
                        background: "#f8d7da",
                        border: "1px solid #f5c6cb",
                        borderRadius: 4,
                      }}
                      data-testid="template-submit-error"
                    >
                      <Text style={{ color: "#721c24", fontSize: 12 }}>{submitError}</Text>
                    </Box>
                  )}

                  {/* Action buttons */}
                  <Box style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                    <Button
                      type="submit"
                      variant="primary"
                      disabled={submitting}
                      data-testid="template-submit-btn"
                    >
                      {submitting ? "Creating…" : "Create Service from Template"}
                    </Button>
                    <Button
                      type="button"
                      variant="light"
                      onClick={() => useTemplateInForm(selectedTemplate.template_id ?? selectedTemplate.slug ?? selectedTemplate.name)}
                      data-testid="template-prefill-form-btn"
                    >
                      Pre-fill form instead
                    </Button>
                  </Box>
                </form>
              </Box>
            </Box>
          )}
        </Box>
      )}

      {/* ── Skip template — manual registration ────────────────────────── */}
      <Box
        pt="lg"
        mt="lg"
        style={{ borderTop: "1px solid #dee2e6" }}
        data-testid="template-skip-section"
      >
        <Button
          variant="light"
          onClick={skipTemplate}
          data-testid="template-skip-btn"
        >
          Skip template — start blank
        </Button>
      </Box>
    </Box>
  );
};

export default ServiceTemplatePicker;
