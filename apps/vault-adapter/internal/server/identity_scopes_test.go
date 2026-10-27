// Package server — tests for the scopes each boot identity holds.
//
// These tests pin the least-privilege scope table in BootIdentities and prove
// through a bufconn server that the proxy identity cannot write a credential
// while the admin identity can, and that the SSH proxy can store a host key
// but cannot write a credential.
//
// Source: vault-method-authorization; design D7.
package server

import (
	"bytes"
	"context"
	"net"
	"reflect"
	"strings"
	"testing"
	"time"

	vaultv1 "github.com/mintkey/mintkey/packages/go/vault/v1"
	"github.com/mintkey/mintkey/services/vault-adapter/internal/sshvault"
	"github.com/mintkey/mintkey/services/vault-adapter/internal/store"
	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/credentials/insecure"
	"google.golang.org/grpc/metadata"
	"google.golang.org/grpc/status"
	"google.golang.org/grpc/test/bufconn"
)

const identityScopesBufSize = 1024 * 1024

// identityScopesTokens builds one distinct 32-byte token per boot token
// variable at run time.
func identityScopesTokens() map[string]string {
	seeds := []struct {
		tokenVar string
		letter   string
	}{
		{"MINTKEY_VAULT_PROXY_TOKEN", "a"},
		{"MINTKEY_VAULT_ADMIN_TOKEN", "b"},
		{"MINTKEY_VAULT_SSH_PROXY_TOKEN", "c"},
		{"MINTKEY_VAULT_EMAIL_PROXY_TOKEN", "d"},
		{"MINTKEY_VAULT_MCP_TOKEN", "e"},
	}
	tokens := make(map[string]string, len(seeds))
	for _, seed := range seeds {
		tokens[seed.tokenVar] = strings.Repeat(seed.letter, 32)
	}
	return tokens
}

// identityScopesLookup returns the variable lookup RegisterBootIdentities reads
// through: each token variable yields its token and every identity id variable
// yields "" (the spec's default id).
func identityScopesLookup(tokens map[string]string) func(string) (string, error) {
	return func(name string) (string, error) {
		return tokens[name], nil
	}
}

func identityScopesOutgoing(ctx context.Context, identity, token string) context.Context {
	return metadata.NewOutgoingContext(ctx, metadata.Pairs(
		"x-mintkey-service-identity", identity,
		"x-mintkey-service-token", token,
	))
}

type identityScopesFixture struct {
	conn   *grpc.ClientConn
	tokens map[string]string
	stop   func()
}

// newIdentityScopesFixture registers every boot identity on a VaultService and
// serves the server buildGRPCServer returns for an SSH-configured VaultServer.
func newIdentityScopesFixture(t *testing.T) identityScopesFixture {
	t.Helper()

	kek := make([]byte, 32)
	for i := range kek {
		kek[i] = byte(i + 7)
	}
	st, err := store.New(":memory:")
	if err != nil {
		t.Fatalf("store.New: %v", err)
	}
	svc := NewVaultService(kek, st)

	tokens := identityScopesTokens()
	if _, err := svc.RegisterBootIdentities("dev", identityScopesLookup(tokens)); err != nil {
		_ = st.Close()
		t.Fatalf("RegisterBootIdentities: %v", err)
	}

	srv := New(kek).WithSSHStore(&fakeSSHStore{
		agents:   map[string]*store.AgentSSHRecord{},
		hostKeys: map[string]string{},
	})
	builder, ok := interface{}(srv).(grpcServerBuilder)
	if !ok {
		_ = st.Close()
		t.Fatalf("%T does not implement grpcServerBuilder", srv)
	}
	grpcSrv := builder.buildGRPCServer(svc)

	lis := bufconn.Listen(identityScopesBufSize)
	go func() { _ = grpcSrv.Serve(lis) }()

	conn, err := grpc.NewClient(
		"passthrough:///bufnet",
		grpc.WithContextDialer(func(ctx context.Context, _ string) (net.Conn, error) {
			return lis.DialContext(ctx)
		}),
		grpc.WithTransportCredentials(insecure.NewCredentials()),
	)
	if err != nil {
		grpcSrv.Stop()
		_ = st.Close()
		t.Fatalf("grpc.NewClient: %v", err)
	}

	return identityScopesFixture{
		conn:   conn,
		tokens: tokens,
		stop: func() {
			_ = conn.Close()
			grpcSrv.Stop()
			_ = st.Close()
		},
	}
}

func TestBootIdentities_LeastPrivilegeScopes_C_5ecd45eb(t *testing.T) {
	want := []struct {
		tokenVar string
		scopes   []string
	}{
		{"MINTKEY_VAULT_PROXY_TOKEN", []string{"vault.read"}},
		{"MINTKEY_VAULT_ADMIN_TOKEN", []string{"vault.read", "vault.put", "vault.secret.put", "vault.secret.delete"}},
		{"MINTKEY_VAULT_SSH_PROXY_TOKEN", []string{"vault.read", "vault.hostkey.put"}},
		{"MINTKEY_VAULT_EMAIL_PROXY_TOKEN", []string{"vault.read"}},
		{"MINTKEY_VAULT_MCP_TOKEN", []string{"vault.secret.put", "vault.secret.read", "vault.secret.delete"}},
	}

	scopeValues := make(map[string]bool, len(methodScopes))
	for _, scope := range methodScopes {
		scopeValues[scope] = true
	}

	byTokenVar := make(map[string][]string, len(BootIdentities))
	for _, spec := range BootIdentities {
		byTokenVar[spec.TokenVar] = spec.Scopes
	}

	for _, tc := range want {
		got, ok := byTokenVar[tc.tokenVar]
		if !ok {
			t.Errorf("BootIdentities has no entry with TokenVar %q", tc.tokenVar)
			continue
		}
		if !reflect.DeepEqual(got, tc.scopes) {
			t.Errorf("BootIdentities[%q].Scopes = %v, want %v", tc.tokenVar, got, tc.scopes)
		}
		for _, scope := range got {
			if !scopeValues[scope] {
				t.Errorf("identity %q holds scope %q, which is not a value of methodScopes", tc.tokenVar, scope)
			}
		}
	}
	if len(byTokenVar) != len(want) {
		t.Errorf("BootIdentities has %d entries, want %d", len(byTokenVar), len(want))
	}
}

func TestProxyIdentity_CannotPutCredential_AdminCan_C_b2d83dba(t *testing.T) {
	fixture := newIdentityScopesFixture(t)
	defer fixture.stop()

	const tenantID = "tenant_proxy_least_privilege"
	const serviceID = "service_proxy_least_privilege"

	client := vaultv1.NewVaultAdapterClient(fixture.conn)
	proxyCtx, cancel := context.WithTimeout(
		identityScopesOutgoing(context.Background(), "svcid_proxy", fixture.tokens["MINTKEY_VAULT_PROXY_TOKEN"]),
		5*time.Second,
	)
	defer cancel()

	_, err := client.PutCredential(proxyCtx, &vaultv1.PutCredentialRequest{
		TenantId:   tenantID,
		ServiceId:  serviceID,
		AuthScheme: vaultv1.AuthScheme_AUTH_SCHEME_API_KEY_HEADER,
		Value:      []byte("the-proxy-must-not-write-this"),
	})
	st, ok := status.FromError(err)
	if !ok || st.Code() != codes.PermissionDenied {
		t.Fatalf("proxy PutCredential: got %v, want PERMISSION_DENIED", err)
	}

	adminValue := []byte("the-admin-identity-wrote-this")
	adminCtx, cancelAdmin := context.WithTimeout(
		identityScopesOutgoing(context.Background(), "svcid_admin_api", fixture.tokens["MINTKEY_VAULT_ADMIN_TOKEN"]),
		5*time.Second,
	)
	defer cancelAdmin()

	adminResp, err := client.PutCredential(adminCtx, &vaultv1.PutCredentialRequest{
		TenantId:   tenantID,
		ServiceId:  serviceID,
		AuthScheme: vaultv1.AuthScheme_AUTH_SCHEME_API_KEY_HEADER,
		Value:      adminValue,
	})
	if err != nil {
		t.Fatalf("admin PutCredential: %v", err)
	}
	if adminResp.GetKeyVersion() == 0 {
		t.Fatal("admin PutCredential: key_version = 0, want a stored version")
	}

	got, err := client.GetCredential(proxyCtx, &vaultv1.GetCredentialRequest{
		TenantId:  tenantID,
		ServiceId: serviceID,
	})
	if err != nil {
		t.Fatalf("proxy GetCredential after the admin write: %v", err)
	}
	if !bytes.Equal(got.GetValue(), adminValue) {
		t.Errorf("proxy GetCredential value = %q, want %q", got.GetValue(), adminValue)
	}
}

func TestSSHProxyIdentity_StoresHostKeyButCannotPutCredential_C_35dca710(t *testing.T) {
	fixture := newIdentityScopesFixture(t)
	defer fixture.stop()

	const tenantID = "tenant_ssh_proxy_least_privilege"
	const serviceID = "service_ssh_proxy_least_privilege"
	const fingerprint = "SHA256:identity-scopes-host-key"

	sshCtx, cancel := context.WithTimeout(
		identityScopesOutgoing(context.Background(), "svcid_ssh_proxy", fixture.tokens["MINTKEY_VAULT_SSH_PROXY_TOKEN"]),
		5*time.Second,
	)
	defer cancel()

	storeResp := &sshvault.StoreHostKeyFingerprintResponse{}
	if err := fixture.conn.Invoke(
		sshCtx,
		"/mintkey.vault.v1.SSHVaultAdapter/StoreHostKeyFingerprint",
		&sshvault.StoreHostKeyFingerprintRequest{
			TenantID:    tenantID,
			ServiceID:   serviceID,
			Fingerprint: fingerprint,
		},
		storeResp,
		grpc.ForceCodec(sshvault.JSONCodec{}),
	); err != nil {
		t.Fatalf("SSH proxy StoreHostKeyFingerprint: %v", err)
	}

	getResp := &sshvault.HostKeyFingerprintResponse{}
	if err := fixture.conn.Invoke(
		sshCtx,
		"/mintkey.vault.v1.SSHVaultAdapter/GetHostKeyFingerprint",
		&sshvault.HostKeyFingerprintRequest{TenantID: tenantID, ServiceID: serviceID},
		getResp,
		grpc.ForceCodec(sshvault.JSONCodec{}),
	); err != nil {
		t.Fatalf("SSH proxy GetHostKeyFingerprint: %v", err)
	}
	if getResp.Fingerprint != fingerprint {
		t.Errorf("SSH proxy GetHostKeyFingerprint = %q, want %q", getResp.Fingerprint, fingerprint)
	}

	client := vaultv1.NewVaultAdapterClient(fixture.conn)
	_, err := client.PutCredential(sshCtx, &vaultv1.PutCredentialRequest{
		TenantId:   tenantID,
		ServiceId:  serviceID,
		AuthScheme: vaultv1.AuthScheme_AUTH_SCHEME_API_KEY_HEADER,
		Value:      []byte("the-ssh-proxy-must-not-write-this"),
	})
	st, ok := status.FromError(err)
	if !ok || st.Code() != codes.PermissionDenied {
		t.Fatalf("SSH proxy PutCredential: got %v, want PERMISSION_DENIED", err)
	}
}
