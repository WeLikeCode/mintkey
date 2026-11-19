package kong_test

import (
	"testing"

	"github.com/mintkey/mintkey/services/kong-syncer/internal/kong"
	"gopkg.in/yaml.v3"
)

// TestVirtualHostRouteCarriesRoutingHeaders covers the scenario "the virtual-host
// route carries the headers": every route of a generated service, including the
// virtual-host route, carries one request-transformer plugin that adds the
// service and tenant routing headers.
func TestVirtualHostRouteCarriesRoutingHeaders_C_a3a11a7d(t *testing.T) {
	services := []kong.ServiceEntry{{
		ID:         "svc_01HX1234567890ABCDEFGHIJKL",
		TenantID:   "tenant_01HX1234567890ABCDEFGHIJKL",
		TenantSlug: "t_default",
		Slug:       "openai",
		BaseURL:    "https://api.openai.com",
	}}

	out, err := kong.GenerateDeclarativeYAML(services, "http://proxy-plugin:8086")
	if err != nil {
		t.Fatalf("GenerateDeclarativeYAML returned error: %v", err)
	}

	var doc map[string]any
	if err := yaml.Unmarshal([]byte(out), &doc); err != nil {
		t.Fatalf("generated YAML does not parse: %v\nGot:\n%s", err, out)
	}

	svcList, ok := doc["services"].([]any)
	if !ok || len(svcList) != 1 {
		t.Fatalf("services = %#v, want a list of length 1\nGot:\n%s", doc["services"], out)
	}
	svc := asStringMap(t, svcList[0])
	routes, ok := svc["routes"].([]any)
	if !ok || len(routes) != 2 {
		t.Fatalf("routes = %#v, want a list of length 2\nGot:\n%s", svc["routes"], out)
	}

	wantHeaders := []string{
		"X-Mintkey-Service-ID:svc_01HX1234567890ABCDEFGHIJKL",
		"X-Mintkey-Tenant-ID:tenant_01HX1234567890ABCDEFGHIJKL",
	}

	for i, rawRoute := range routes {
		route := asStringMap(t, rawRoute)
		name, _ := route["name"].(string)
		plugins, ok := route["plugins"].([]any)
		if !ok {
			t.Fatalf("route %q: plugins = %#v, want a list", name, route["plugins"])
		}

		var transformers []map[string]any
		for _, rawPlugin := range plugins {
			plugin := asStringMap(t, rawPlugin)
			if plugin["name"] == "request-transformer" {
				transformers = append(transformers, plugin)
			}
		}
		if len(transformers) != 1 {
			t.Fatalf("route %q: request-transformer plugins = %d, want exactly 1 (route %d)", name, len(transformers), i)
		}

		config := asStringMap(t, transformers[0]["config"])
		add := asStringMap(t, config["add"])
		rawHeaders, ok := add["headers"].([]any)
		if !ok {
			t.Fatalf("route %q: config.add.headers = %#v, want a list", name, add["headers"])
		}
		gotHeaders := make([]string, 0, len(rawHeaders))
		for _, rawHeader := range rawHeaders {
			header, ok := rawHeader.(string)
			if !ok {
				t.Fatalf("route %q: header %#v is not a string", name, rawHeader)
			}
			gotHeaders = append(gotHeaders, header)
		}
		if len(gotHeaders) != len(wantHeaders) {
			t.Fatalf("route %q: config.add.headers = %#v, want %#v", name, gotHeaders, wantHeaders)
		}
		for j := range wantHeaders {
			if gotHeaders[j] != wantHeaders[j] {
				t.Fatalf("route %q: config.add.headers[%d] = %q, want %q", name, j, gotHeaders[j], wantHeaders[j])
			}
		}
	}
}

// asStringMap converts a YAML-decoded mapping to map[string]any.
func asStringMap(t *testing.T, v any) map[string]any {
	t.Helper()
	switch m := v.(type) {
	case map[string]any:
		return m
	case map[any]any:
		out := make(map[string]any, len(m))
		for k, val := range m {
			key, ok := k.(string)
			if !ok {
				t.Fatalf("mapping key %#v is not a string", k)
			}
			out[key] = val
		}
		return out
	default:
		t.Fatalf("value %#v is not a mapping", v)
		return nil
	}
}
