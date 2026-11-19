package config_test

import (
	"reflect"
	"testing"

	"github.com/mintkey/mintkey/services/broker/internal/config"
)

// serviceTokenChecker is the start-up contract of Config. The methods are
// reached through this interface so the test compiles before they exist.
type serviceTokenChecker interface {
	MissingServiceTokens() []string
	Validate() error
}

func newServiceTokenChecker(t *testing.T, cfg *config.Config) serviceTokenChecker {
	t.Helper()
	checker, ok := any(cfg).(serviceTokenChecker)
	if !ok {
		t.Fatal("*config.Config does not implement MissingServiceTokens and Validate")
	}
	return checker
}

func assertMissingServiceTokens(t *testing.T, checker serviceTokenChecker, want []string) {
	t.Helper()
	if got := checker.MissingServiceTokens(); !reflect.DeepEqual(got, want) {
		t.Fatalf("MissingServiceTokens() = %v, want %v", got, want)
	}
}

func TestMissingServiceTokens_BothMissing_C_4a3dcd7f(t *testing.T) {
	checker := newServiceTokenChecker(t, &config.Config{})

	assertMissingServiceTokens(t, checker, []string{
		"MINTKEY_MCP_SERVICE_TOKEN",
		"MINTKEY_PROXY_SERVICE_TOKEN",
	})
}

func TestMissingServiceTokens_OneMissing_C_7811225a(t *testing.T) {
	checker := newServiceTokenChecker(t, &config.Config{
		MCPServiceToken: "mcp-value",
	})

	assertMissingServiceTokens(t, checker, []string{"MINTKEY_PROXY_SERVICE_TOKEN"})
}

func TestValidate_ProductionWithTokenMissing_C_c7136482(t *testing.T) {
	checker := newServiceTokenChecker(t, &config.Config{Env: "production"})

	err := checker.Validate()
	if err == nil {
		t.Fatal("Validate() = nil, want an error naming the missing variables")
	}

	const want = "production requires these variables to be set: MINTKEY_MCP_SERVICE_TOKEN, MINTKEY_PROXY_SERVICE_TOKEN"
	if err.Error() != want {
		t.Fatalf("Validate() error = %q, want %q", err.Error(), want)
	}
}

func TestValidate_ProductionWithBothTokens_C_5cf49df9(t *testing.T) {
	checker := newServiceTokenChecker(t, &config.Config{
		Env:               "production",
		MCPServiceToken:   "mcp-value",
		ProxyServiceToken: "proxy-value",
	})

	if err := checker.Validate(); err != nil {
		t.Fatalf("Validate() = %v, want nil", err)
	}
	if got := checker.MissingServiceTokens(); len(got) != 0 {
		t.Fatalf("MissingServiceTokens() = %v, want empty", got)
	}

	// A configuration that really is missing a token must not look like this
	// one, so the empty result above is a real answer rather than a zero value.
	missing := newServiceTokenChecker(t, &config.Config{
		Env:               "production",
		ProxyServiceToken: "proxy-value",
	})
	assertMissingServiceTokens(t, missing, []string{"MINTKEY_MCP_SERVICE_TOKEN"})
}

func TestValidate_DevWithTokensMissing_C_60346d8f(t *testing.T) {
	checker := newServiceTokenChecker(t, &config.Config{Env: "dev"})

	if err := checker.Validate(); err != nil {
		t.Fatalf("Validate() = %v, want nil outside production", err)
	}

	// Outside production the missing tokens are still reported, so the nil
	// above is a real answer rather than a zero value.
	assertMissingServiceTokens(t, checker, []string{
		"MINTKEY_MCP_SERVICE_TOKEN",
		"MINTKEY_PROXY_SERVICE_TOKEN",
	})
}
