// Package server — egress-scope tests for the vault adapter gRPC surface.
//
// The egress scope travels in gRPC call metadata under the key
// "x-mintkey-egress-scope": a PutCredential request may name it and every
// GetCredential response answers it in a response header.
//
// Source: proxy-public-egress spec, requirement "The vault adapter stores and
// returns the scope"; design D1/D6.
package server

import (
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"fmt"
	"net"
	"sync"
	"testing"

	vaultv1 "github.com/mintkey/mintkey/packages/go/vault/v1"
	"github.com/mintkey/mintkey/services/vault-adapter/internal/googleserviceaccount"
	"github.com/mintkey/mintkey/services/vault-adapter/internal/store"
	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/credentials/insecure"
	"google.golang.org/grpc/metadata"
	"google.golang.org/grpc/status"
	"google.golang.org/grpc/test/bufconn"
)

// newTestGRPCServerWithBackend spins up a grpcVaultServer over the given store
// backend, as newTestGRPCServer does for the in-memory SQLite store.
func newTestGRPCServerWithBackend(t *testing.T, backend store.Backend) (vaultv1.VaultAdapterClient, func()) {
	t.Helper()

	kek := make([]byte, 32)
	for i := range kek {
		kek[i] = byte(i + 1)
	}
	svc := NewVaultService(kek, backend)

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
		_ = backend.Close()
	}
	return vaultv1.NewVaultAdapterClient(conn), cleanup
}

// noRowsGetBackend wraps a store.Backend and overrides Get(version 0) so the
// lookup of the current version reports "no such row" the way a store may
// while the service has no version. Once a version is stored, Get reads it
// normally so the result can be observed.
type noRowsGetBackend struct {
	store.Backend
	err       error
	nilResult bool
}

func (b *noRowsGetBackend) Get(ctx context.Context, tenantID, serviceID string, keyVersion uint32) (*store.CredentialRecord, error) {
	if keyVersion == 0 {
		if rec, err := b.Backend.Get(ctx, tenantID, serviceID, 0); err == nil && rec != nil {
			return rec, nil
		}
		if b.nilResult {
			return nil, nil
		}
		return nil, b.err
	}
	return b.Backend.Get(ctx, tenantID, serviceID, keyVersion)
}

// failingGetBackend wraps a store.Backend whose Get always fails with an error
// that is not "no rows".
type failingGetBackend struct {
	store.Backend
	err error
}

func (b *failingGetBackend) Get(context.Context, string, string, uint32) (*store.CredentialRecord, error) {
	return nil, b.err
}

// putCredentialScoped sends one PutCredential call with zero or more values of
// the egress-scope metadata key.
func putCredentialScoped(ctx context.Context, client vaultv1.VaultAdapterClient, tenantID, serviceID string, scheme vaultv1.AuthScheme, value []byte, scopes ...string) (*vaultv1.PutCredentialResponse, error) {
	for _, scope := range scopes {
		ctx = metadata.AppendToOutgoingContext(ctx, "x-mintkey-egress-scope", scope)
	}
	return client.PutCredential(ctx, &vaultv1.PutCredentialRequest{
		TenantId:   tenantID,
		ServiceId:  serviceID,
		AuthScheme: scheme,
		Value:      value,
	})
}

// getCredentialScoped reads one credential and returns the egress-scope
// response header values alongside the response.
func getCredentialScoped(ctx context.Context, client vaultv1.VaultAdapterClient, tenantID, serviceID string, keyVersion uint32) ([]string, *vaultv1.GetCredentialResponse, error) {
	var md metadata.MD
	resp, err := client.GetCredential(ctx, &vaultv1.GetCredentialRequest{
		TenantId:   tenantID,
		ServiceId:  serviceID,
		KeyVersion: keyVersion,
	}, grpc.Header(&md))
	return md.Get("x-mintkey-egress-scope"), resp, err
}

// TestEgressScopeRoundTrip: public, any and no value at put time come back as
// public, any and any in the GetCredential response header.
func TestEgressScopeRoundTrip_C_cbe614ee(t *testing.T) {
	t.Run("C-cbe614ee", func(t *testing.T) {
		ctx := context.Background()
		client, cleanup := newTestGRPCServer(t)
		defer cleanup()

		cases := []struct {
			serviceID string
			scopes    []string
			want      string
		}{
			{serviceID: "S1", scopes: []string{"public"}, want: "public"},
			{serviceID: "S2", scopes: []string{"any"}, want: "any"},
			{serviceID: "S3", scopes: nil, want: "any"},
		}

		for _, tc := range cases {
			if _, err := putCredentialScoped(ctx, client, "tenant_egress_roundtrip", tc.serviceID, vaultv1.AuthScheme_AUTH_SCHEME_API_KEY_HEADER, []byte("secret-"+tc.serviceID), tc.scopes...); err != nil {
				t.Fatalf("PutCredential(%s): %v", tc.serviceID, err)
			}

			got, _, err := getCredentialScoped(ctx, client, "tenant_egress_roundtrip", tc.serviceID, 0)
			if err != nil {
				t.Fatalf("GetCredential(%s): %v", tc.serviceID, err)
			}
			if len(got) != 1 || got[0] != tc.want {
				t.Errorf("service %s: egress scope header = %v, want [%q]", tc.serviceID, got, tc.want)
			}
		}
	})
}

// TestEgressScopeRotationKeepsScope: a put that names no scope keeps the
// current version's scope; a put that names one replaces it.
func TestEgressScopeRotationKeepsScope_C_b52d2f54(t *testing.T) {
	t.Run("C-b52d2f54", func(t *testing.T) {
		ctx := context.Background()
		client, cleanup := newTestGRPCServer(t)
		defer cleanup()

		const tenantID = "tenant_egress_rotation"
		const serviceID = "svc_egress_rotation"

		first, err := putCredentialScoped(ctx, client, tenantID, serviceID, vaultv1.AuthScheme_AUTH_SCHEME_BEARER_TOKEN, []byte("one"), "public")
		if err != nil {
			t.Fatalf("PutCredential(public): %v", err)
		}
		if first.GetKeyVersion() != 1 {
			t.Fatalf("first key version = %d, want 1", first.GetKeyVersion())
		}

		second, err := putCredentialScoped(ctx, client, tenantID, serviceID, vaultv1.AuthScheme_AUTH_SCHEME_BEARER_TOKEN, []byte("two"))
		if err != nil {
			t.Fatalf("PutCredential(no scope): %v", err)
		}
		if second.GetKeyVersion() != 2 {
			t.Fatalf("second key version = %d, want 2", second.GetKeyVersion())
		}

		got, _, err := getCredentialScoped(ctx, client, tenantID, serviceID, 0)
		if err != nil {
			t.Fatalf("GetCredential after no-scope rotation: %v", err)
		}
		if len(got) != 1 || got[0] != "public" {
			t.Errorf("second version scope = %v, want [public]", got)
		}

		third, err := putCredentialScoped(ctx, client, tenantID, serviceID, vaultv1.AuthScheme_AUTH_SCHEME_BEARER_TOKEN, []byte("three"), "any")
		if err != nil {
			t.Fatalf("PutCredential(any): %v", err)
		}
		if third.GetKeyVersion() != 3 {
			t.Fatalf("third key version = %d, want 3", third.GetKeyVersion())
		}

		got, _, err = getCredentialScoped(ctx, client, tenantID, serviceID, 0)
		if err != nil {
			t.Fatalf("GetCredential after any: %v", err)
		}
		if len(got) != 1 || got[0] != "any" {
			t.Errorf("third version scope = %v, want [any]", got)
		}
	})
}

// TestEgressScopeFirstPutAndConcurrentPuts: a first put that names no scope
// stores any whether the store reports absence as a wrapped sql.ErrNoRows or as
// (nil, nil), and concurrent no-scope puts keep the current public scope.
func TestEgressScopeFirstPutAndConcurrentPuts_C_43146073(t *testing.T) {
	t.Run("C-43146073/no_rows_error", func(t *testing.T) {
		ctx := context.Background()
		backend, err := store.New(":memory:")
		if err != nil {
			t.Fatalf("store.New: %v", err)
		}
		wrapped := &noRowsGetBackend{Backend: backend, err: fmt.Errorf("x: %w", sql.ErrNoRows)}
		client, cleanup := newTestGRPCServerWithBackend(t, wrapped)
		defer cleanup()

		const tenantID = "tenant_egress_no_rows"
		const serviceID = "svc_egress_no_rows"

		put, err := putCredentialScoped(ctx, client, tenantID, serviceID, vaultv1.AuthScheme_AUTH_SCHEME_API_KEY_HEADER, []byte("secret"))
		if err != nil {
			t.Fatalf("PutCredential: %v", err)
		}
		if put.GetKeyVersion() != 1 {
			t.Fatalf("key version = %d, want 1", put.GetKeyVersion())
		}

		got, _, err := getCredentialScoped(ctx, client, tenantID, serviceID, 1)
		if err != nil {
			t.Fatalf("GetCredential(version 1): %v", err)
		}
		if len(got) != 1 || got[0] != "any" {
			t.Errorf("first put scope = %v, want [any]", got)
		}
	})

	t.Run("C-43146073/nil_nil", func(t *testing.T) {
		ctx := context.Background()
		backend, err := store.New(":memory:")
		if err != nil {
			t.Fatalf("store.New: %v", err)
		}
		wrapped := &noRowsGetBackend{Backend: backend, nilResult: true}
		client, cleanup := newTestGRPCServerWithBackend(t, wrapped)
		defer cleanup()

		const tenantID = "tenant_egress_nil_nil"
		const serviceID = "svc_egress_nil_nil"

		put, err := putCredentialScoped(ctx, client, tenantID, serviceID, vaultv1.AuthScheme_AUTH_SCHEME_API_KEY_HEADER, []byte("secret"))
		if err != nil {
			t.Fatalf("PutCredential: %v", err)
		}
		if put.GetKeyVersion() != 1 {
			t.Fatalf("key version = %d, want 1", put.GetKeyVersion())
		}

		got, _, err := getCredentialScoped(ctx, client, tenantID, serviceID, 1)
		if err != nil {
			t.Fatalf("GetCredential(version 1): %v", err)
		}
		if len(got) != 1 || got[0] != "any" {
			t.Errorf("first put scope = %v, want [any]", got)
		}
	})

	t.Run("C-43146073/concurrent", func(t *testing.T) {
		ctx := context.Background()
		client, cleanup := newTestGRPCServer(t)
		defer cleanup()

		const tenantID = "tenant_egress_concurrent"
		const serviceID = "svc_egress_concurrent"

		if _, err := putCredentialScoped(ctx, client, tenantID, serviceID, vaultv1.AuthScheme_AUTH_SCHEME_API_KEY_HEADER, []byte("initial"), "public"); err != nil {
			t.Fatalf("PutCredential(public): %v", err)
		}

		const writers = 8
		errs := make([]error, writers)
		var wg sync.WaitGroup
		for i := 0; i < writers; i++ {
			wg.Add(1)
			go func(i int) {
				defer wg.Done()
				_, errs[i] = putCredentialScoped(ctx, client, tenantID, serviceID, vaultv1.AuthScheme_AUTH_SCHEME_API_KEY_HEADER, []byte(fmt.Sprintf("writer-%d", i)))
			}(i)
		}
		wg.Wait()
		for i, err := range errs {
			if err != nil {
				t.Fatalf("concurrent PutCredential %d: %v", i, err)
			}
		}

		list, err := client.ListVersions(ctx, &vaultv1.ListVersionsRequest{
			TenantId:  tenantID,
			ServiceId: serviceID,
		})
		if err != nil {
			t.Fatalf("ListVersions: %v", err)
		}
		if len(list.GetVersions()) != writers+1 {
			t.Fatalf("ListVersions returned %d versions, want %d", len(list.GetVersions()), writers+1)
		}

		for _, version := range list.GetVersions() {
			got, _, err := getCredentialScoped(ctx, client, tenantID, serviceID, version.GetKeyVersion())
			if err != nil {
				t.Fatalf("GetCredential(version %d): %v", version.GetKeyVersion(), err)
			}
			if len(got) != 1 || got[0] != "public" {
				t.Errorf("version %d scope = %v, want [public]", version.GetKeyVersion(), got)
			}
		}
	})
}

// TestEgressScopeUnusableValueRefused: a value other than any/public (the empty
// string included) and more than one value are InvalidArgument and store
// nothing.
func TestEgressScopeUnusableValueRefused_C_48ff464c(t *testing.T) {
	t.Run("C-48ff464c", func(t *testing.T) {
		ctx := context.Background()
		client, cleanup := newTestGRPCServer(t)
		defer cleanup()

		cases := []struct {
			name      string
			serviceID string
			scopes    []string
		}{
			{name: "private", serviceID: "svc_scope_private", scopes: []string{"private"}},
			{name: "empty", serviceID: "svc_scope_empty", scopes: []string{""}},
			{name: "two values", serviceID: "svc_scope_two", scopes: []string{"any", "any"}},
		}

		for _, tc := range cases {
			_, err := putCredentialScoped(ctx, client, "tenant_egress_refused", tc.serviceID, vaultv1.AuthScheme_AUTH_SCHEME_API_KEY_HEADER, []byte("secret"), tc.scopes...)
			if err == nil {
				t.Errorf("%s: PutCredential succeeded, want InvalidArgument", tc.name)
			} else {
				st, ok := status.FromError(err)
				if !ok {
					t.Fatalf("%s: expected a gRPC status error, got %T: %v", tc.name, err, err)
				}
				if st.Code() != codes.InvalidArgument {
					t.Errorf("%s: code = %v, want InvalidArgument", tc.name, st.Code())
				}
			}

			list, err := client.ListVersions(ctx, &vaultv1.ListVersionsRequest{
				TenantId:  "tenant_egress_refused",
				ServiceId: tc.serviceID,
			})
			if err != nil {
				t.Fatalf("%s: ListVersions: %v", tc.name, err)
			}
			if len(list.GetVersions()) != 0 {
				t.Errorf("%s: ListVersions returned %d versions, want 0", tc.name, len(list.GetVersions()))
			}
		}
	})
}

// TestEgressScopeFailingLookupFailsPut: when the lookup of the current version
// fails for a reason other than "no rows", the put fails and stores nothing.
func TestEgressScopeFailingLookupFailsPut_C_eac1baf3(t *testing.T) {
	t.Run("C-eac1baf3", func(t *testing.T) {
		ctx := context.Background()
		backend, err := store.New(":memory:")
		if err != nil {
			t.Fatalf("store.New: %v", err)
		}
		wrapped := &failingGetBackend{Backend: backend, err: errors.New("lookup failed")}
		client, cleanup := newTestGRPCServerWithBackend(t, wrapped)
		defer cleanup()

		const tenantID = "tenant_egress_lookup_fail"
		const serviceID = "svc_egress_lookup_fail"

		if _, err := putCredentialScoped(ctx, client, tenantID, serviceID, vaultv1.AuthScheme_AUTH_SCHEME_API_KEY_HEADER, []byte("secret")); err == nil {
			t.Fatal("PutCredential succeeded, want a failed lookup to fail the put")
		}

		list, err := client.ListVersions(ctx, &vaultv1.ListVersionsRequest{
			TenantId:  tenantID,
			ServiceId: serviceID,
		})
		if err != nil {
			t.Fatalf("ListVersions: %v", err)
		}
		if len(list.GetVersions()) != 0 {
			t.Errorf("ListVersions returned %d versions, want 0", len(list.GetVersions()))
		}
	})
}

// TestEgressScopeEverySchemeResponse: every authentication scheme answers the
// stored scope in the GetCredential response header.
func TestEgressScopeEverySchemeResponse_C_a4ac0a47(t *testing.T) {
	t.Run("C-a4ac0a47", func(t *testing.T) {
		ctx := context.Background()
		client, cleanup := newTestGRPCServer(t)
		defer cleanup()

		const tenantID = "tenant_egress_schemes"

		// api_key_header
		apiKeyService := "svc_scheme_api_key_header"
		if _, err := putCredentialScoped(ctx, client, tenantID, apiKeyService, vaultv1.AuthScheme_AUTH_SCHEME_API_KEY_HEADER, []byte("api-key"), "public"); err != nil {
			t.Fatalf("PutCredential(api_key_header): %v", err)
		}

		// bearer_token
		bearerService := "svc_scheme_bearer_token"
		if _, err := putCredentialScoped(ctx, client, tenantID, bearerService, vaultv1.AuthScheme_AUTH_SCHEME_BEARER_TOKEN, []byte("bearer"), "public"); err != nil {
			t.Fatalf("PutCredential(bearer_token): %v", err)
		}

		// apple_jwt — envelope built as TestGRPCAppleJWT_HappyPath builds it.
		appleService := "svc_scheme_apple_jwt"
		pemBytes, _ := mustTestECKeyPEM(t)
		appleEnvelope, err := json.Marshal(appleJWTEnvelope{
			Scheme:   "apple_jwt",
			P8KeyPEM: string(pemBytes),
			KeyID:    "TESTKEY0001",
			IssuerID: "11111111-2222-3333-4444-555555555555",
		})
		if err != nil {
			t.Fatalf("marshal apple_jwt envelope: %v", err)
		}
		if _, err := putCredentialScoped(ctx, client, tenantID, appleService, vaultv1.AuthScheme_AUTH_SCHEME_APPLE_JWT, appleEnvelope, "public"); err != nil {
			t.Fatalf("PutCredential(apple_jwt): %v", err)
		}

		// google_service_account — blob and cache seeded as the existing GSA
		// tests build them; the token endpoint is never called on a cache hit.
		gsaService := "svc_scheme_google_service_account"
		gsaKeyID := "key-id-egress-scope-001"
		tokenServer, _ := newTokenServer(t, 200, "unused-token")
		gsaBlob := buildStoredBlob(t, generateTestRSAKey(t), gsaKeyID, tokenServer.URL, "https://www.googleapis.com/auth/cloud-platform")
		googleserviceaccount.GlobalCache.Set(tenantID, gsaService, gsaKeyID, "cached-token", 3600)
		t.Cleanup(func() { googleserviceaccount.GlobalCache.Invalidate(tenantID, gsaService, gsaKeyID) })
		if _, err := putCredentialScoped(ctx, client, tenantID, gsaService, vaultv1.AuthScheme_AUTH_SCHEME_GOOGLE_SERVICE_ACCOUNT, gsaBlob, "public"); err != nil {
			t.Fatalf("PutCredential(google_service_account): %v", err)
		}

		for _, serviceID := range []string{apiKeyService, bearerService, appleService, gsaService} {
			got, _, err := getCredentialScoped(ctx, client, tenantID, serviceID, 0)
			if err != nil {
				t.Fatalf("GetCredential(%s): %v", serviceID, err)
			}
			if len(got) != 1 || got[0] != "public" {
				t.Errorf("%s: egress scope header = %v, want [public]", serviceID, got)
			}
		}
	})
}
