// Package vault_test verifies the Vault Adapter gRPC client architecture constraints.
//
// Source: ADR-0014.4 (no plaintext cache in proxy plugin); T-1.6.3.
package vault_test

import (
	"context"
	"reflect"
	"testing"

	"github.com/mintkey/mintkey/services/proxy-plugin/internal/vault"
)

// TestVaultClient_HasNoCache is an architecture test: per ADR-0014.4 the proxy
// plugin must NOT cache plaintext credentials. The Client struct must have no
// "cache" or "Cache" field.
func TestVaultClient_HasNoCache(t *testing.T) {
	c := vault.NewClient("localhost:8084", "svcid_proxy_test_token")
	ct := reflect.TypeOf(*c)
	for i := 0; i < ct.NumField(); i++ {
		field := ct.Field(i)
		if field.Name == "cache" || field.Name == "Cache" {
			t.Fatalf("VaultClient must not have a cache field (ADR-0014.4): found field %q", field.Name)
		}
	}
}

// TestVaultClient_UnreachableReturnsError verifies that a missing Vault Adapter
// returns an error rather than panicking.
func TestVaultClient_UnreachableReturnsError(t *testing.T) {
	// port 1 is always unreachable (root-only, never listened on in tests)
	client := vault.NewClient("localhost:1", "test_token")
	_, err := client.GetCredential(context.Background(), vault.GetCredentialRequest{
		TenantID:  "tenant_01HXTEST00000000000000001",
		ServiceID: "svc_01HXTEST00000000000000001",
	})
	if err == nil {
		t.Fatal("expected error when vault adapter is unreachable, got nil")
	}
}

// TestVaultClient_ServiceTokenInMetadata verifies that the client stores the
// service token for injection into outgoing gRPC metadata.
func TestVaultClient_ServiceTokenInMetadata(t *testing.T) {
	client := vault.NewClient("localhost:8084", "my_service_token")
	if client.ServiceToken() != "my_service_token" {
		t.Fatalf("expected service token %q, got %q", "my_service_token", client.ServiceToken())
	}
}
