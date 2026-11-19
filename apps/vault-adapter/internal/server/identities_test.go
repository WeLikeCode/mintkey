package server

import (
	"context"
	"errors"
	"reflect"
	"strings"
	"testing"
)

// bootRegistrar is the boot-time registration contract of VaultService. The
// methods are reached through this interface so the test compiles before they
// exist; the type assertion fails (with t.Fatal) when they are missing.
type bootRegistrar interface {
	RegisterBootIdentities(env string, lookup func(name string) (string, error)) ([]string, error)
	RegisterBootIdentitiesFromEnv(env string) ([]string, error)
}

func newBootRegistrar(t *testing.T, svc *VaultService) bootRegistrar {
	t.Helper()
	reg, ok := any(svc).(bootRegistrar)
	if !ok {
		t.Fatal("*server.VaultService does not implement RegisterBootIdentities and RegisterBootIdentitiesFromEnv")
	}
	return reg
}

// bootLookup builds the lookup RegisterBootIdentities reads its variables
// through: a missing key yields "", nil, and a key in failing yields its error.
func bootLookup(values map[string]string, failing map[string]error) func(string) (string, error) {
	return func(name string) (string, error) {
		if err, ok := failing[name]; ok {
			return "", err
		}
		return values[name], nil
	}
}

func repeatToken(letter string) string {
	return strings.Repeat(letter, 32)
}

func allBootTokens() map[string]string {
	return map[string]string{
		"MINTKEY_VAULT_PROXY_TOKEN":       repeatToken("a"),
		"MINTKEY_VAULT_ADMIN_TOKEN":       repeatToken("b"),
		"MINTKEY_VAULT_SSH_PROXY_TOKEN":   repeatToken("c"),
		"MINTKEY_VAULT_EMAIL_PROXY_TOKEN": repeatToken("d"),
		"MINTKEY_VAULT_MCP_TOKEN":         repeatToken("e"),
	}
}

func assertBootIdentityAccepted(t *testing.T, svc *VaultService, id, token string) {
	t.Helper()
	if _, ok := svc.ValidateServiceIdentity(context.Background(), id, []byte(token)); !ok {
		t.Fatalf("ValidateServiceIdentity(%q) refused the registered token", id)
	}
}

func assertBootIdentityRefused(t *testing.T, svc *VaultService, id, token string) {
	t.Helper()
	if _, ok := svc.ValidateServiceIdentity(context.Background(), id, []byte(token)); ok {
		t.Fatalf("ValidateServiceIdentity(%q) accepted %q, want refusal", id, token)
	}
}

func TestRegisterBootIdentities_EveryTokenSet_C_bb56de98(t *testing.T) {
	svc := makeTestVaultService(t)
	reg := newBootRegistrar(t, svc)

	values := allBootTokens()
	unset, err := reg.RegisterBootIdentities("dev", bootLookup(values, nil))
	if err != nil {
		t.Fatalf("RegisterBootIdentities: %v", err)
	}
	if len(unset) != 0 {
		t.Fatalf("unset = %v, want an empty list", unset)
	}

	identities := []struct {
		id    string
		token string
	}{
		{id: "svcid_proxy", token: values["MINTKEY_VAULT_PROXY_TOKEN"]},
		{id: "svcid_admin_api", token: values["MINTKEY_VAULT_ADMIN_TOKEN"]},
		{id: "svcid_ssh_proxy", token: values["MINTKEY_VAULT_SSH_PROXY_TOKEN"]},
		{id: "svcid_email_proxy", token: values["MINTKEY_VAULT_EMAIL_PROXY_TOKEN"]},
		{id: "svcid_mcp", token: values["MINTKEY_VAULT_MCP_TOKEN"]},
	}
	for _, tc := range identities {
		assertBootIdentityAccepted(t, svc, tc.id, tc.token)
	}
	for i, tc := range identities {
		other := identities[(i+1)%len(identities)].token
		assertBootIdentityRefused(t, svc, tc.id, other)
	}
}

func TestRegisterBootIdentities_IDVariableSet_C_d7a0bdd1(t *testing.T) {
	svc := makeTestVaultService(t)
	reg := newBootRegistrar(t, svc)

	values := allBootTokens()
	values["MINTKEY_VAULT_PROXY_IDENTITY_ID"] = "svcid_proxy_custom"
	unset, err := reg.RegisterBootIdentities("dev", bootLookup(values, nil))
	if err != nil {
		t.Fatalf("RegisterBootIdentities: %v", err)
	}
	if len(unset) != 0 {
		t.Fatalf("unset = %v, want an empty list", unset)
	}

	proxyToken := values["MINTKEY_VAULT_PROXY_TOKEN"]
	assertBootIdentityAccepted(t, svc, "svcid_proxy_custom", proxyToken)
	assertBootIdentityRefused(t, svc, "svcid_proxy", proxyToken)
}

func TestRegisterBootIdentities_EmptyTokenNotRegistered_C_03905893(t *testing.T) {
	svc := makeTestVaultService(t)
	reg := newBootRegistrar(t, svc)

	values := allBootTokens()
	delete(values, "MINTKEY_VAULT_MCP_TOKEN")
	unset, err := reg.RegisterBootIdentities("dev", bootLookup(values, nil))
	if err != nil {
		t.Fatalf("RegisterBootIdentities: %v", err)
	}
	want := []string{"MINTKEY_VAULT_MCP_TOKEN"}
	if !reflect.DeepEqual(unset, want) {
		t.Fatalf("unset = %v, want %v", unset, want)
	}

	assertBootIdentityAccepted(t, svc, "svcid_proxy", values["MINTKEY_VAULT_PROXY_TOKEN"])
	assertBootIdentityAccepted(t, svc, "svcid_admin_api", values["MINTKEY_VAULT_ADMIN_TOKEN"])
	assertBootIdentityAccepted(t, svc, "svcid_ssh_proxy", values["MINTKEY_VAULT_SSH_PROXY_TOKEN"])
	assertBootIdentityAccepted(t, svc, "svcid_email_proxy", values["MINTKEY_VAULT_EMAIL_PROXY_TOKEN"])

	assertBootIdentityRefused(t, svc, "svcid_mcp", "")
	assertBootIdentityRefused(t, svc, "svcid_mcp", repeatToken("z"))
}

func TestRegisterBootIdentities_LookupErrorRegistersNothing_C_75a979b4(t *testing.T) {
	svc := makeTestVaultService(t)
	reg := newBootRegistrar(t, svc)

	lookupErr := errors.New("lookup failed")
	values := allBootTokens()
	delete(values, "MINTKEY_VAULT_ADMIN_TOKEN")
	unset, err := reg.RegisterBootIdentities("dev", bootLookup(values, map[string]error{
		"MINTKEY_VAULT_ADMIN_TOKEN": lookupErr,
	}))
	if err == nil {
		t.Fatal("RegisterBootIdentities = nil error, want the lookup error")
	}
	if !errors.Is(err, lookupErr) {
		t.Fatalf("RegisterBootIdentities error = %v, want one wrapping %v", err, lookupErr)
	}
	if unset != nil {
		t.Fatalf("unset = %v, want nil", unset)
	}
	assertBootIdentityRefused(t, svc, "svcid_proxy", values["MINTKEY_VAULT_PROXY_TOKEN"])
}

func TestRegisterBootIdentitiesFromEnv_ReadsEnvironment_C_312b2c0e(t *testing.T) {
	svc := makeTestVaultService(t)
	reg := newBootRegistrar(t, svc)

	for _, name := range []string{
		"MINTKEY_VAULT_PROXY_IDENTITY_ID",
		"MINTKEY_VAULT_ADMIN_IDENTITY_ID",
		"MINTKEY_VAULT_SSH_PROXY_IDENTITY_ID",
		"MINTKEY_VAULT_EMAIL_PROXY_IDENTITY_ID",
		"MINTKEY_VAULT_MCP_IDENTITY_ID",
		"MINTKEY_VAULT_PROXY_TOKEN",
		"MINTKEY_VAULT_ADMIN_TOKEN",
		"MINTKEY_VAULT_SSH_PROXY_TOKEN",
		"MINTKEY_VAULT_EMAIL_PROXY_TOKEN",
		"MINTKEY_VAULT_MCP_TOKEN",
	} {
		t.Setenv(name, "")
	}
	proxyToken := repeatToken("a")
	adminToken := repeatToken("b")
	t.Setenv("MINTKEY_VAULT_PROXY_TOKEN", proxyToken)
	t.Setenv("MINTKEY_VAULT_ADMIN_TOKEN", adminToken)

	unset, err := reg.RegisterBootIdentitiesFromEnv("dev")
	if err != nil {
		t.Fatalf("RegisterBootIdentitiesFromEnv: %v", err)
	}
	want := []string{
		"MINTKEY_VAULT_SSH_PROXY_TOKEN",
		"MINTKEY_VAULT_EMAIL_PROXY_TOKEN",
		"MINTKEY_VAULT_MCP_TOKEN",
	}
	if !reflect.DeepEqual(unset, want) {
		t.Fatalf("unset = %v, want %v", unset, want)
	}

	assertBootIdentityAccepted(t, svc, "svcid_proxy", proxyToken)
	assertBootIdentityAccepted(t, svc, "svcid_admin_api", adminToken)
}

func TestRegisterBootIdentities_ProductionRequiresProxyAndAdmin_C_93d873f6(t *testing.T) {
	svc := makeTestVaultService(t)
	reg := newBootRegistrar(t, svc)

	values := map[string]string{
		"MINTKEY_VAULT_SSH_PROXY_TOKEN":   repeatToken("c"),
		"MINTKEY_VAULT_EMAIL_PROXY_TOKEN": repeatToken("d"),
		"MINTKEY_VAULT_MCP_TOKEN":         repeatToken("e"),
	}
	unset, err := reg.RegisterBootIdentities("production", bootLookup(values, nil))
	if err == nil {
		t.Fatal("RegisterBootIdentities = nil error, want the production refusal")
	}
	const want = "production requires these variables to be set: MINTKEY_VAULT_PROXY_TOKEN, MINTKEY_VAULT_ADMIN_TOKEN"
	if err.Error() != want {
		t.Fatalf("RegisterBootIdentities error = %q, want %q", err.Error(), want)
	}
	if unset != nil {
		t.Fatalf("unset = %v, want nil", unset)
	}
	assertBootIdentityRefused(t, svc, "svcid_mcp", values["MINTKEY_VAULT_MCP_TOKEN"])
}

func TestRegisterBootIdentities_ProductionWithoutOptionalTokens_C_57495bbe(t *testing.T) {
	svc := makeTestVaultService(t)
	reg := newBootRegistrar(t, svc)

	proxyToken := repeatToken("a")
	adminToken := repeatToken("b")
	values := map[string]string{
		"MINTKEY_VAULT_PROXY_TOKEN": proxyToken,
		"MINTKEY_VAULT_ADMIN_TOKEN": adminToken,
	}
	unset, err := reg.RegisterBootIdentities("production", bootLookup(values, nil))
	if err != nil {
		t.Fatalf("RegisterBootIdentities: %v", err)
	}
	want := []string{
		"MINTKEY_VAULT_SSH_PROXY_TOKEN",
		"MINTKEY_VAULT_EMAIL_PROXY_TOKEN",
		"MINTKEY_VAULT_MCP_TOKEN",
	}
	if !reflect.DeepEqual(unset, want) {
		t.Fatalf("unset = %v, want %v", unset, want)
	}

	assertBootIdentityAccepted(t, svc, "svcid_proxy", proxyToken)
	assertBootIdentityAccepted(t, svc, "svcid_admin_api", adminToken)
}

func TestRegisterBootIdentities_DevWithoutProxyToken_C_869146df(t *testing.T) {
	svc := makeTestVaultService(t)
	reg := newBootRegistrar(t, svc)

	values := allBootTokens()
	delete(values, "MINTKEY_VAULT_PROXY_TOKEN")
	unset, err := reg.RegisterBootIdentities("dev", bootLookup(values, nil))
	if err != nil {
		t.Fatalf("RegisterBootIdentities: %v", err)
	}
	want := []string{"MINTKEY_VAULT_PROXY_TOKEN"}
	if !reflect.DeepEqual(unset, want) {
		t.Fatalf("unset = %v, want %v", unset, want)
	}

	assertBootIdentityAccepted(t, svc, "svcid_admin_api", values["MINTKEY_VAULT_ADMIN_TOKEN"])
}

func TestRegisterServiceIdentity_EmptyTokenRefused_C_aed1806a(t *testing.T) {
	svc := makeTestVaultService(t)

	err := svc.RegisterServiceIdentity("svcid_x", []byte{}, []string{"vault.read"})
	if err == nil {
		t.Fatal("RegisterServiceIdentity = nil error, want a refusal of the empty token")
	}
	if !strings.Contains(err.Error(), "empty token") {
		t.Fatalf("RegisterServiceIdentity error = %q, want it to contain %q", err.Error(), "empty token")
	}

	assertBootIdentityRefused(t, svc, "svcid_x", "")
	assertBootIdentityRefused(t, svc, "svcid_x", repeatToken("z"))
}

func TestRegisterServiceIdentity_EmptyIDRefused_C_138aad20(t *testing.T) {
	svc := makeTestVaultService(t)

	token := []byte("a-32-byte-token-for-the-test-xx!")
	err := svc.RegisterServiceIdentity("", token, []string{"vault.read"})
	if err == nil {
		t.Fatal("RegisterServiceIdentity = nil error, want a refusal of the empty identity id")
	}
	if !strings.Contains(err.Error(), "empty identity id") {
		t.Fatalf("RegisterServiceIdentity error = %q, want it to contain %q", err.Error(), "empty identity id")
	}

	assertBootIdentityRefused(t, svc, "", string(token))
}
