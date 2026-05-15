// Package server — gRPC handler tests for ListVersions.
//
// These tests exercise the full gRPC layer (grpcVaultServer) using an
// in-process bufconn transport, so they validate the translation from
// proto request → VaultService → proto response without a network socket.
//
// Source: WS-10; vault.proto; T-1.3.1.
package server

import (
	"context"
	"net"
	"testing"

	vaultv1 "github.com/mintkey/mintkey/internal/vault/v1"
	"github.com/mintkey/mintkey/services/vault-adapter/internal/store"
	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/credentials/insecure"
	"google.golang.org/grpc/status"
	"google.golang.org/grpc/test/bufconn"
)

const bufSize = 1024 * 1024

// newTestGRPCServer spins up a grpcVaultServer backed by an in-memory store
// and returns a connected stub plus a cleanup func.
func newTestGRPCServer(t *testing.T) (vaultv1.VaultAdapterClient, func()) {
	t.Helper()

	kek := make([]byte, 32)
	for i := range kek {
		kek[i] = byte(i + 1)
	}
	s, err := store.New(":memory:")
	if err != nil {
		t.Fatalf("store.New: %v", err)
	}

	svc := NewVaultService(kek, s)

	lis := bufconn.Listen(bufSize)
	srv := grpc.NewServer()
	vaultv1.RegisterVaultAdapterServer(srv, &grpcVaultServer{svc: svc})

	go func() { _ = srv.Serve(lis) }()

	conn, err := grpc.NewClient(
		"passthrough:///bufnet",
		grpc.WithContextDialer(func(ctx context.Context, _ string) (net.Conn, error) {
			return lis.DialContext(ctx)
		}),
		grpc.WithTransportCredentials(insecure.NewCredentials()),
	)
	if err != nil {
		t.Fatalf("grpc.NewClient: %v", err)
	}

	cleanup := func() {
		conn.Close()
		srv.Stop()
		_ = s.Close()
	}
	return vaultv1.NewVaultAdapterClient(conn), cleanup
}

// TestGRPCListVersions_TwoVersions puts 2 credentials via gRPC PutCredential,
// then calls ListVersions and verifies:
//   - 2 entries are returned
//   - ordering is ASC by key_version
//   - version 2 is flagged is_current
//   - no plaintext bytes appear in any VersionDescriptor field
func TestGRPCListVersions_TwoVersions(t *testing.T) {
	ctx := context.Background()
	client, cleanup := newTestGRPCServer(t)
	defer cleanup()

	tenantID := "tenant_grpc_list"
	serviceID := "svc_grpc_list"
	secrets := [][]byte{[]byte("first-secret"), []byte("second-secret")}

	var putVersions []uint32
	for _, secret := range secrets {
		resp, err := client.PutCredential(ctx, &vaultv1.PutCredentialRequest{
			TenantId:  tenantID,
			ServiceId: serviceID,
			AuthScheme: vaultv1.AuthScheme_AUTH_SCHEME_API_KEY_HEADER,
			Value:     secret,
		})
		if err != nil {
			t.Fatalf("PutCredential: %v", err)
		}
		putVersions = append(putVersions, resp.KeyVersion)
	}

	if putVersions[0] >= putVersions[1] {
		t.Errorf("expected key_version to increment; got %d then %d", putVersions[0], putVersions[1])
	}

	listResp, err := client.ListVersions(ctx, &vaultv1.ListVersionsRequest{
		TenantId:  tenantID,
		ServiceId: serviceID,
	})
	if err != nil {
		t.Fatalf("ListVersions: %v", err)
	}

	if len(listResp.Versions) != 2 {
		t.Fatalf("expected 2 versions, got %d", len(listResp.Versions))
	}

	// ASC ordering.
	if listResp.Versions[0].KeyVersion >= listResp.Versions[1].KeyVersion {
		t.Errorf("versions not in ASC order: %d, %d",
			listResp.Versions[0].KeyVersion, listResp.Versions[1].KeyVersion)
	}

	// Only the latest (version 2) should be current.
	for _, v := range listResp.Versions {
		wantCurrent := v.KeyVersion == putVersions[1]
		if v.IsCurrent != wantCurrent {
			t.Errorf("version %d: IsCurrent=%v, want %v", v.KeyVersion, v.IsCurrent, wantCurrent)
		}
	}

	// CurrentKeyVersion convenience field should equal the latest version.
	if listResp.CurrentKeyVersion != putVersions[1] {
		t.Errorf("CurrentKeyVersion=%d, want %d", listResp.CurrentKeyVersion, putVersions[1])
	}

	// PLAINTEXT-LEAK CHECK: VersionDescriptor carries no value field.
	// The proto VersionDescriptor message has no bytes/value field at all;
	// we verify the secrets do not appear anywhere in the response string form.
	respStr := listResp.String()
	for _, secret := range secrets {
		if contains(respStr, string(secret)) {
			t.Errorf("SECURITY: plaintext %q leaked in ListVersions response", secret)
		}
	}
}

// TestGRPCListVersions_Empty verifies an empty list is returned (not an error)
// when no credentials exist for the given (tenant_id, service_id).
func TestGRPCListVersions_Empty(t *testing.T) {
	ctx := context.Background()
	client, cleanup := newTestGRPCServer(t)
	defer cleanup()

	listResp, err := client.ListVersions(ctx, &vaultv1.ListVersionsRequest{
		TenantId:  "tenant_no_creds",
		ServiceId: "svc_no_creds",
	})
	if err != nil {
		t.Fatalf("ListVersions on empty store: %v", err)
	}
	if len(listResp.Versions) != 0 {
		t.Errorf("expected 0 versions for empty store, got %d", len(listResp.Versions))
	}
}

// TestGRPCListVersions_MissingTenantID verifies a validation error is returned
// when tenant_id is omitted.
func TestGRPCListVersions_MissingTenantID(t *testing.T) {
	ctx := context.Background()
	client, cleanup := newTestGRPCServer(t)
	defer cleanup()

	_, err := client.ListVersions(ctx, &vaultv1.ListVersionsRequest{
		ServiceId: "svc_01",
	})
	if err == nil {
		t.Fatal("expected error for missing tenant_id, got nil")
	}
	st, ok := status.FromError(err)
	if !ok {
		t.Fatalf("expected gRPC status error, got %T: %v", err, err)
	}
	if st.Code() != codes.Internal {
		t.Errorf("expected codes.Internal, got %v", st.Code())
	}
}

// TestGRPCListVersions_PutAndGetUnaffected verifies that implementing
// ListVersions does not regress PutCredential or GetCredential behaviour.
func TestGRPCListVersions_PutAndGetUnaffected(t *testing.T) {
	ctx := context.Background()
	client, cleanup := newTestGRPCServer(t)
	defer cleanup()

	plaintext := []byte("regression-check-secret")

	putResp, err := client.PutCredential(ctx, &vaultv1.PutCredentialRequest{
		TenantId:   "tenant_regress",
		ServiceId:  "svc_regress",
		AuthScheme: vaultv1.AuthScheme_AUTH_SCHEME_BEARER_TOKEN,
		Value:      plaintext,
	})
	if err != nil {
		t.Fatalf("PutCredential: %v", err)
	}
	if putResp.KeyVersion == 0 {
		t.Errorf("expected non-zero key_version from PutCredential")
	}

	getResp, err := client.GetCredential(ctx, &vaultv1.GetCredentialRequest{
		TenantId:   "tenant_regress",
		ServiceId:  "svc_regress",
		KeyVersion: 0,
	})
	if err != nil {
		t.Fatalf("GetCredential: %v", err)
	}
	if string(getResp.Value) != string(plaintext) {
		t.Errorf("GetCredential returned %q, want %q", getResp.Value, plaintext)
	}
}

// contains is a simple substring check (avoids importing strings in test file).
func contains(haystack, needle string) bool {
	if needle == "" {
		return false
	}
	for i := 0; i+len(needle) <= len(haystack); i++ {
		if haystack[i:i+len(needle)] == needle {
			return true
		}
	}
	return false
}
