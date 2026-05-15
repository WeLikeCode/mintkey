/**
 * ServiceTemplatePicker — resource action component (OPS-S).
 *
 * Fetches /admin/api/resources/services/actions/template-list (BFF passthrough)
 * on mount and renders a card grid of service templates.
 *
 * Card click → navigate to /new?template=<slug> so ServiceCreateForm can
 * pre-fill from the template.
 *
 * Source: OPS-SUX chunk S.
 */

import React, { useEffect, useState } from "react";
import {
  Box,
  H3,
  Text,
  Button,
} from "@adminjs/design-system";
import { ApiClient } from "adminjs";
import { useNavigate } from "react-router-dom";

// ── types ────────────────────────────────────────────────────────────────────

interface ServiceTemplate {
  slug: string;
  name: string;
  description?: string;
  base_url?: string;
  auth_scheme?: string;
  openapi_url?: string;
}

// Props injected by AdminJS for resource-type actions
// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Props = Record<string, any>;

// ── ServiceTemplatePicker ─────────────────────────────────────────────────────

const ServiceTemplatePicker = (_props: Props): React.ReactElement => {
  const navigate = useNavigate();

  const [templates, setTemplates] = useState<ServiceTemplate[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

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

  const pickTemplate = (slug: string) => {
    navigate(`/admin/resources/services/actions/new?template=${encodeURIComponent(slug)}`);
  };

  const skipTemplate = () => {
    navigate("/admin/resources/services/actions/new");
  };

  return (
    <Box variant="white" p="xxl" data-testid="service-template-picker">
      <H3 mb="default">Create from Template</H3>
      <Text mb="xl" style={{ color: "#6c757d" }}>
        Pick a template to pre-fill the service form. Credential values are never
        pre-filled — you will supply those after selecting a template.
      </Text>

      {loading && (
        <Text data-testid="template-loading" style={{ color: "#6c757d" }}>
          Loading templates…
        </Text>
      )}

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

      {!loading && !error && templates.length === 0 && (
        <Text style={{ color: "#6c757d" }} data-testid="template-empty">
          No templates available.
        </Text>
      )}

      {/* ── Card grid ────────────────────────────────────────────────── */}
      {!loading && templates.length > 0 && (
        <Box
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))",
            gap: 16,
            marginBottom: 32,
          }}
          data-testid="template-card-grid"
        >
          {templates.map((tpl) => (
            <Box
              key={tpl.slug}
              p="lg"
              style={{
                border: "1px solid #dee2e6",
                borderRadius: 6,
                background: "#fff",
                cursor: "pointer",
                transition: "box-shadow 0.15s ease",
              }}
              data-testid={`template-card-${tpl.slug}`}
            >
              <H3
                mb="default"
                style={{ fontSize: 16, marginBottom: 8 }}
              >
                {tpl.name}
              </H3>

              {tpl.description && (
                <Text
                  mb="default"
                  style={{ fontSize: 13, color: "#6c757d", marginBottom: 8 }}
                >
                  {tpl.description}
                </Text>
              )}

              {tpl.base_url && (
                <Text
                  style={{
                    fontSize: 12,
                    color: "#495057",
                    fontFamily: "monospace",
                    marginBottom: 12,
                    wordBreak: "break-all",
                  }}
                >
                  {tpl.base_url}
                </Text>
              )}

              {tpl.auth_scheme && (
                <Box
                  mb="default"
                  style={{
                    display: "inline-block",
                    background: "#e9ecef",
                    borderRadius: 3,
                    padding: "2px 6px",
                    fontSize: 11,
                    fontFamily: "monospace",
                    marginBottom: 12,
                  }}
                >
                  {tpl.auth_scheme}
                </Box>
              )}

              <Box>
                <Button
                  variant="primary"
                  size="sm"
                  onClick={() => pickTemplate(tpl.slug)}
                  data-testid={`template-pick-${tpl.slug}`}
                >
                  Use this template
                </Button>
              </Box>
            </Box>
          ))}
        </Box>
      )}

      {/* ── Skip template ──────────────────────────────────────────────── */}
      <Box
        pt="lg"
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
