// Package kong generates Kong declarative YAML from a list of brokered services.
//
// Each service gets two routes per ADR-0007:
//   - Path route:         /v1/call/<service_id>
//   - Virtual-host route: <slug>.<tenant_slug>.proxy.local
//
// Source: ADR-0007; T-1.2.2.
package kong

import (
	"fmt"

	"gopkg.in/yaml.v3"
)

// ServiceEntry is the input record for the Kong YAML generator.
type ServiceEntry struct {
	ID         string
	TenantID   string
	TenantSlug string
	Slug       string
	BaseURL    string
}

// declarativeConfig is the top-level Kong declarative YAML document.
type declarativeConfig struct {
	FormatVersion string           `yaml:"_format_version"`
	Services      []kongService    `yaml:"services,omitempty"`
}

type kongService struct {
	Name   string      `yaml:"name"`
	URL    string      `yaml:"url"`
	Routes []kongRoute `yaml:"routes"`
}

type kongPlugin struct {
	Name   string         `yaml:"name"`
	Config map[string]any `yaml:"config,omitempty"`
}

type kongRoute struct {
	Name      string       `yaml:"name"`
	Paths     []string     `yaml:"paths,omitempty"`
	Hosts     []string     `yaml:"hosts,omitempty"`
	StripPath bool         `yaml:"strip_path"`
	Plugins   []kongPlugin `yaml:"plugins,omitempty"`
}

// GenerateDeclarativeYAML produces Kong declarative YAML (format version 3.0)
// for the given service list. Each service receives:
//  1. A path route  /v1/call/<service_id>          (ADR-0007 option A)
//  2. A virtual-host route <slug>.<tenant_slug>.proxy.local  (ADR-0007 option C)
func GenerateDeclarativeYAML(services []ServiceEntry) (string, error) {
	cfg := declarativeConfig{
		FormatVersion: "3.0",
	}

	for _, svc := range services {
		ks := kongService{
			// All Kong services point to the proxy-plugin which validates JWTs,
			// fetches credentials from the Vault Adapter, and reverse-proxies.
			Name: svc.ID,
			URL:  "http://proxy-plugin:8086",
			Routes: []kongRoute{
				{
					// strip_path: true removes /v1/call/<svc_id> so the proxy-plugin
					// receives the bare API path (e.g. /api-key-header).
					// request-transformer injects routing metadata used by the
					// classical-key branch (ADR-0018) to identify the service and tenant
					// without relying on the URL path after stripping.
					Name:      fmt.Sprintf("%s-path", svc.ID),
					Paths:     []string{fmt.Sprintf("/v1/call/%s", svc.ID)},
					StripPath: true,
					Plugins: []kongPlugin{
						{
							Name: "request-transformer",
							Config: map[string]any{
								"add": map[string]any{
									"headers": []string{
										"X-Mintkey-Service-ID:" + svc.ID,
										"X-Mintkey-Tenant-ID:" + svc.TenantID,
									},
								},
							},
						},
					},
				},
				{
					Name:      fmt.Sprintf("%s-vhost", svc.ID),
					Hosts:     []string{fmt.Sprintf("%s.%s.proxy.local", svc.Slug, svc.TenantSlug)},
					StripPath: false,
				},
			},
		}
		cfg.Services = append(cfg.Services, ks)
	}

	out, err := yaml.Marshal(&cfg)
	if err != nil {
		return "", fmt.Errorf("kong: marshal declarative YAML: %w", err)
	}
	return string(out), nil
}
