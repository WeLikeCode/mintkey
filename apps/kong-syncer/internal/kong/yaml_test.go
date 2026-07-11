// Package kong_test tests Kong declarative YAML generation.
//
// Routes conform to ADR-0007 (proxy deployment topology):
//   - Path route:        /v1/call/<service_id>
//   - Virtual-host route: <slug>.<tenant_slug>.proxy.local
//
// Source: ADR-0007; T-1.2.2.
package kong_test

import (
	"strings"
	"testing"

	"github.com/mintkey/mintkey/services/kong-syncer/internal/kong"
)

// mustContain is a small helper so individual test bodies stay readable.
func mustContain(t *testing.T, label, haystack, needle string) {
	t.Helper()
	if !strings.Contains(haystack, needle) {
		t.Errorf("%s: expected output to contain %q\nGot:\n%s", label, needle, haystack)
	}
}

// TestYAMLGeneration_PathRoute asserts that the output contains a path route
// matching /v1/call/<service_id> (ADR-0007, option A).
func TestYAMLGeneration_PathRoute(t *testing.T) {
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

	mustContain(t, "path route", out, "/v1/call/svc_01HX1234567890ABCDEFGHIJKL")
}

// TestYAMLGeneration_VirtualHostRoute asserts that the output contains a
// virtual-host route matching <slug>.<tenant_slug>.proxy.local (ADR-0007, option C).
func TestYAMLGeneration_VirtualHostRoute(t *testing.T) {
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

	mustContain(t, "virtual-host route", out, "openai.t_default.proxy.local")
}

// TestYAMLGeneration_EmptyServicesIsValid asserts that an empty service list
// produces valid YAML with the required _format_version header and no services.
func TestYAMLGeneration_EmptyServicesIsValid(t *testing.T) {
	out, err := kong.GenerateDeclarativeYAML([]kong.ServiceEntry{}, "http://proxy-plugin:8086")
	if err != nil {
		t.Fatalf("GenerateDeclarativeYAML returned error on empty list: %v", err)
	}

	mustContain(t, "format version", out, `_format_version: "3.0"`)

	if strings.Contains(out, "/v1/call/") {
		t.Errorf("empty input: unexpected /v1/call/ in output:\n%s", out)
	}
}

// TestYAMLGeneration_MultipleServices asserts that each service in the list
// gets its own path route and virtual-host route.
func TestYAMLGeneration_MultipleServices(t *testing.T) {
	services := []kong.ServiceEntry{
		{
			ID:         "svc_AAAAAAAAAAAAAAAAAAAAAAAAA1",
			TenantID:   "tenant_01HX1234567890ABCDEFGHIJKL",
			TenantSlug: "t_default",
			Slug:       "openai",
			BaseURL:    "https://api.openai.com",
		},
		{
			ID:         "svc_BBBBBBBBBBBBBBBBBBBBBBBBB2",
			TenantID:   "tenant_01HX1234567890ABCDEFGHIJKL",
			TenantSlug: "t_default",
			Slug:       "stripe",
			BaseURL:    "https://api.stripe.com",
		},
	}

	out, err := kong.GenerateDeclarativeYAML(services, "http://proxy-plugin:8086")
	if err != nil {
		t.Fatalf("GenerateDeclarativeYAML returned error: %v", err)
	}

	mustContain(t, "svc1 path", out, "/v1/call/svc_AAAAAAAAAAAAAAAAAAAAAAAAA1")
	mustContain(t, "svc1 vhost", out, "openai.t_default.proxy.local")
	mustContain(t, "svc2 path", out, "/v1/call/svc_BBBBBBBBBBBBBBBBBBBBBBBBB2")
	mustContain(t, "svc2 vhost", out, "stripe.t_default.proxy.local")
}

// TestYAMLGeneration_UsesProxyPluginURL asserts that the configured proxy-plugin
// URL is used as every service's upstream, so deployments (e.g. Kubernetes, where
// the Service is release-name-prefixed) can point Kong at the right host instead
// of the hard-coded docker-compose name.
func TestYAMLGeneration_UsesProxyPluginURL(t *testing.T) {
	services := []kong.ServiceEntry{{
		ID:         "svc_01HX1234567890ABCDEFGHIJKL",
		TenantID:   "tenant_01HX1234567890ABCDEFGHIJKL",
		TenantSlug: "t_default",
		Slug:       "openai",
		BaseURL:    "https://api.openai.com",
	}}

	out, err := kong.GenerateDeclarativeYAML(services, "http://mintkey-proxy-plugin:8086")
	if err != nil {
		t.Fatalf("GenerateDeclarativeYAML returned error: %v", err)
	}

	mustContain(t, "custom upstream", out, "url: http://mintkey-proxy-plugin:8086")
	if strings.Contains(out, "http://proxy-plugin:8086") {
		t.Errorf("expected the configured upstream to override the compose default; got:\n%s", out)
	}
}
