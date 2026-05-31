// Package server — gRPC handler tests for AUTH_SCHEME_GOOGLE_SERVICE_ACCOUNT.
//
// These tests exercise the GetCredential handler's Google service account branch
// end-to-end: stored-blob parse → cache lookup / token-endpoint fetch →
// access token returned as Value.
//
// Test-server pattern: an httptest.NewServer is stood up per cache-miss test;
// the Google JSON key's token_uri field is overridden to point at it.
// The GlobalCache is reset via Invalidate / cache swap between tests so they
// do not bleed into each other.
package server

import (
	"context"
	"crypto/rand"
	"crypto/rsa"
	"crypto/x509"
	"encoding/json"
	"encoding/pem"
	"fmt"
	"net/http"
	"net/http/httptest"
	"sync/atomic"
	"testing"

	vaultv1 "github.com/mintkey/mintkey/packages/go/vault/v1"
	"github.com/mintkey/mintkey/services/vault-adapter/internal/googleserviceaccount"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

// generateTestRSAKey returns a PKCS1 PEM-encoded RSA-2048 private key for use
// in tests.  Using PKCS1 ("RSA PRIVATE KEY") because it is the format Google
// issues and is the fallback path in FetchAccessToken's key parser.
func generateTestRSAKey(t *testing.T) string {
	t.Helper()
	priv, err := rsa.GenerateKey(rand.Reader, 2048)
	if err != nil {
		t.Fatalf("rsa.GenerateKey: %v", err)
	}
	pemBlock := &pem.Block{
		Type:  "RSA PRIVATE KEY",
		Bytes: x509.MarshalPKCS1PrivateKey(priv),
	}
	return string(pem.EncodeToMemory(pemBlock))
}

// buildStoredBlob constructs the two-layer JSON blob that is stored (encrypted)
// in the vault for AUTH_SCHEME_GOOGLE_SERVICE_ACCOUNT credentials:
//
//	outer  → { "json_key": <raw bytes>, "scope": "..." }
//	inner  → Google service account JSON key object
//
// tokenURI is patched to point at a test HTTP server so no real Google calls
// are made.
func buildStoredBlob(t *testing.T, privateKeyPEM, privateKeyID, tokenURI, scope string) []byte {
	t.Helper()

	type innerKey struct {
		Type         string `json:"type"`
		ProjectID    string `json:"project_id"`
		PrivateKeyID string `json:"private_key_id"`
		PrivateKey   string `json:"private_key"`
		ClientEmail  string `json:"client_email"`
		TokenURI     string `json:"token_uri"`
	}

	inner := innerKey{
		Type:         "service_account",
		ProjectID:    "test-project",
		PrivateKeyID: privateKeyID,
		PrivateKey:   privateKeyPEM,
		ClientEmail:  "test@test-project.iam.gserviceaccount.com",
		TokenURI:     tokenURI,
	}

	innerBytes, err := json.Marshal(inner)
	if err != nil {
		t.Fatalf("marshal inner key: %v", err)
	}

	type outerBlob struct {
		JSONKey json.RawMessage `json:"json_key"`
		Scope   string          `json:"scope"`
	}
	outer := outerBlob{
		JSONKey: json.RawMessage(innerBytes),
		Scope:   scope,
	}
	blob, err := json.Marshal(outer)
	if err != nil {
		t.Fatalf("marshal outer blob: %v", err)
	}
	return blob
}

// tokenServerHits is an atomic counter so we can verify the token endpoint was
// (or was not) called.
type tokenServerHits struct{ n atomic.Int64 }

func (h *tokenServerHits) inc() { h.n.Add(1) }
func (h *tokenServerHits) get() int64 { return h.n.Load() }

// newTokenServer returns an httptest.Server that returns a well-formed Google
// token response, plus a hit-counter.  Pass statusCode=200 for success,
// anything else for error.
func newTokenServer(t *testing.T, statusCode int, accessToken string) (*httptest.Server, *tokenServerHits) {
	t.Helper()
	hits := &tokenServerHits{}
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		hits.inc()
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(statusCode)
		if statusCode == http.StatusOK {
			fmt.Fprintf(w, `{"access_token":%q,"expires_in":3600,"token_type":"Bearer"}`, accessToken)
		} else {
			fmt.Fprint(w, `{"error":"server_error"}`)
		}
	}))
	t.Cleanup(ts.Close)
	return ts, hits
}

// putGSACredential stores a google_service_account blob via gRPC PutCredential
// and returns the assigned key_version.
func putGSACredential(t *testing.T, client vaultv1.VaultAdapterClient, tenantID, serviceID string, blob []byte) uint32 {
	t.Helper()
	ctx := context.Background()
	resp, err := client.PutCredential(ctx, &vaultv1.PutCredentialRequest{
		TenantId:   tenantID,
		ServiceId:  serviceID,
		AuthScheme: vaultv1.AuthScheme_AUTH_SCHEME_GOOGLE_SERVICE_ACCOUNT,
		Value:      blob,
	})
	if err != nil {
		t.Fatalf("PutCredential (gsa): %v", err)
	}
	return resp.KeyVersion
}

// -----------------------------------------------------------------------
// TestGoogleServiceAccount_HappyPath_CacheMiss
//
// Seed vault with a stored blob (real RSA-2048 key, httptest token server).
// Call GetCredential → token endpoint must be hit exactly once → returned
// Value must equal the access token from the test server.
// -----------------------------------------------------------------------

func TestGoogleServiceAccount_HappyPath_CacheMiss(t *testing.T) {
	client, cleanup := newTestGRPCServer(t)
	defer cleanup()

	tenantID := "tenant_gsa_cache_miss"
	serviceID := "svc_gsa_cache_miss"
	privateKeyID := "key-id-cachemiss-001"
	wantToken := "ya29.real-token-cachemiss"

	ts, hits := newTokenServer(t, http.StatusOK, wantToken)

	pemKey := generateTestRSAKey(t)
	blob := buildStoredBlob(t, pemKey, privateKeyID, ts.URL, "https://www.googleapis.com/auth/cloud-platform")

	// Ensure no stale cache entry for this key.
	googleserviceaccount.GlobalCache.Invalidate(tenantID, serviceID, privateKeyID)

	putGSACredential(t, client, tenantID, serviceID, blob)

	ctx := context.Background()
	getResp, err := client.GetCredential(ctx, &vaultv1.GetCredentialRequest{
		TenantId:   tenantID,
		ServiceId:  serviceID,
		KeyVersion: 0,
	})
	if err != nil {
		t.Fatalf("GetCredential: %v", err)
	}

	if string(getResp.Value) != wantToken {
		t.Errorf("GetCredential Value=%q, want %q", getResp.Value, wantToken)
	}
	if getResp.AuthScheme != vaultv1.AuthScheme_AUTH_SCHEME_GOOGLE_SERVICE_ACCOUNT {
		t.Errorf("AuthScheme=%v, want AUTH_SCHEME_GOOGLE_SERVICE_ACCOUNT", getResp.AuthScheme)
	}
	if hits.get() != 1 {
		t.Errorf("token endpoint hit count=%d, want 1 (cache miss should call endpoint once)", hits.get())
	}

	// Cleanup cache after test.
	googleserviceaccount.GlobalCache.Invalidate(tenantID, serviceID, privateKeyID)
}

// -----------------------------------------------------------------------
// TestGoogleServiceAccount_HappyPath_CacheHit
//
// Pre-populate GlobalCache with a known token.  Call GetCredential → the
// token endpoint must NOT be called → returned Value must equal the cached token.
// -----------------------------------------------------------------------

func TestGoogleServiceAccount_HappyPath_CacheHit(t *testing.T) {
	client, cleanup := newTestGRPCServer(t)
	defer cleanup()

	tenantID := "tenant_gsa_cache_hit"
	serviceID := "svc_gsa_cache_hit"
	privateKeyID := "key-id-cachehit-001"
	cachedToken := "cached-token-xyz"

	// Token server that should NOT be called.
	ts, hits := newTokenServer(t, http.StatusOK, "should-not-be-returned")

	pemKey := generateTestRSAKey(t)
	blob := buildStoredBlob(t, pemKey, privateKeyID, ts.URL, "https://www.googleapis.com/auth/cloud-platform")

	// Pre-seed the cache — expiresIn=3600 so it is well within renewalBuffer.
	googleserviceaccount.GlobalCache.Set(tenantID, serviceID, privateKeyID, cachedToken, 3600)

	putGSACredential(t, client, tenantID, serviceID, blob)

	ctx := context.Background()
	getResp, err := client.GetCredential(ctx, &vaultv1.GetCredentialRequest{
		TenantId:   tenantID,
		ServiceId:  serviceID,
		KeyVersion: 0,
	})
	if err != nil {
		t.Fatalf("GetCredential: %v", err)
	}

	if string(getResp.Value) != cachedToken {
		t.Errorf("GetCredential Value=%q, want cached token %q", getResp.Value, cachedToken)
	}
	if hits.get() != 0 {
		t.Errorf("token endpoint hit count=%d, want 0 (cache hit must NOT call endpoint)", hits.get())
	}

	// Cleanup.
	googleserviceaccount.GlobalCache.Invalidate(tenantID, serviceID, privateKeyID)
}

// -----------------------------------------------------------------------
// TestGoogleServiceAccount_InvalidEnvelope_BadJSON
//
// Stored plaintext = "not-json" → codes.InvalidArgument.
// -----------------------------------------------------------------------

func TestGoogleServiceAccount_InvalidEnvelope_BadJSON(t *testing.T) {
	client, cleanup := newTestGRPCServer(t)
	defer cleanup()

	tenantID := "tenant_gsa_badjson"
	serviceID := "svc_gsa_badjson"

	// Store raw garbage — not a valid JSON blob.
	ctx := context.Background()
	_, err := client.PutCredential(ctx, &vaultv1.PutCredentialRequest{
		TenantId:   tenantID,
		ServiceId:  serviceID,
		AuthScheme: vaultv1.AuthScheme_AUTH_SCHEME_GOOGLE_SERVICE_ACCOUNT,
		Value:      []byte("not-json"),
	})
	if err != nil {
		t.Fatalf("PutCredential: %v", err)
	}

	_, err = client.GetCredential(ctx, &vaultv1.GetCredentialRequest{
		TenantId:   tenantID,
		ServiceId:  serviceID,
		KeyVersion: 0,
	})
	if err == nil {
		t.Fatal("expected codes.InvalidArgument for bad JSON, got nil")
	}
	st, ok := status.FromError(err)
	if !ok {
		t.Fatalf("expected gRPC status error, got %T: %v", err, err)
	}
	if st.Code() != codes.InvalidArgument {
		t.Errorf("expected codes.InvalidArgument, got %v: %s", st.Code(), st.Message())
	}
}

// -----------------------------------------------------------------------
// TestGoogleServiceAccount_InvalidEnvelope_MissingFields
//
// Stored plaintext = valid JSON but missing required fields (empty json_key
// and empty scope) → codes.InvalidArgument.
// -----------------------------------------------------------------------

func TestGoogleServiceAccount_InvalidEnvelope_MissingFields(t *testing.T) {
	client, cleanup := newTestGRPCServer(t)
	defer cleanup()

	tenantID := "tenant_gsa_missingfields"
	serviceID := "svc_gsa_missingfields"

	// Valid JSON envelope but missing json_key and scope.
	badBlob := []byte(`{"json_key":null,"scope":""}`)

	ctx := context.Background()
	_, err := client.PutCredential(ctx, &vaultv1.PutCredentialRequest{
		TenantId:   tenantID,
		ServiceId:  serviceID,
		AuthScheme: vaultv1.AuthScheme_AUTH_SCHEME_GOOGLE_SERVICE_ACCOUNT,
		Value:      badBlob,
	})
	if err != nil {
		t.Fatalf("PutCredential: %v", err)
	}

	_, err = client.GetCredential(ctx, &vaultv1.GetCredentialRequest{
		TenantId:   tenantID,
		ServiceId:  serviceID,
		KeyVersion: 0,
	})
	if err == nil {
		t.Fatal("expected codes.InvalidArgument for missing fields, got nil")
	}
	st, ok := status.FromError(err)
	if !ok {
		t.Fatalf("expected gRPC status error, got %T: %v", err, err)
	}
	if st.Code() != codes.InvalidArgument {
		t.Errorf("expected codes.InvalidArgument, got %v: %s", st.Code(), st.Message())
	}
}

// -----------------------------------------------------------------------
// TestGoogleServiceAccount_TokenEndpoint500
//
// Token endpoint returns 500 → codes.Internal.
// -----------------------------------------------------------------------

func TestGoogleServiceAccount_TokenEndpoint500(t *testing.T) {
	client, cleanup := newTestGRPCServer(t)
	defer cleanup()

	tenantID := "tenant_gsa_500"
	serviceID := "svc_gsa_500"
	privateKeyID := "key-id-500-001"

	ts, _ := newTokenServer(t, http.StatusInternalServerError, "")

	pemKey := generateTestRSAKey(t)
	blob := buildStoredBlob(t, pemKey, privateKeyID, ts.URL, "https://www.googleapis.com/auth/cloud-platform")

	// Ensure no stale cache entry.
	googleserviceaccount.GlobalCache.Invalidate(tenantID, serviceID, privateKeyID)

	putGSACredential(t, client, tenantID, serviceID, blob)

	ctx := context.Background()
	_, err := client.GetCredential(ctx, &vaultv1.GetCredentialRequest{
		TenantId:   tenantID,
		ServiceId:  serviceID,
		KeyVersion: 0,
	})
	if err == nil {
		t.Fatal("expected codes.Internal for token endpoint 500, got nil")
	}
	st, ok := status.FromError(err)
	if !ok {
		t.Fatalf("expected gRPC status error, got %T: %v", err, err)
	}
	if st.Code() != codes.Internal {
		t.Errorf("expected codes.Internal, got %v: %s", st.Code(), st.Message())
	}

	// Cleanup.
	googleserviceaccount.GlobalCache.Invalidate(tenantID, serviceID, privateKeyID)
}

// -----------------------------------------------------------------------
// TestGoogleServiceAccount_ZeroizationCheck
//
// This test documents the zeroization code path.  The actual zeroization of
// keyFile.PrivateKey is performed inside grpc.go (visible by code inspection):
//
//   pemBytes := []byte(keyFile.PrivateKey)
//   for i := range pemBytes { pemBytes[i] = 0 }
//   keyFile.PrivateKey = ""
//
// This pattern runs on BOTH the cache-hit and cache-miss paths, as well as on
// the error path after FetchAccessToken.  A black-box gRPC test cannot assert
// that the in-process *KeyFile field was zeroed after the RPC returned, so this
// test instead validates that:
//   (a) a successful GetCredential following an earlier error (500) does not
//       return stale key material in the Value field, and
//   (b) the cache is empty after a 500 error (i.e. Set was NOT called on failure).
// -----------------------------------------------------------------------

func TestGoogleServiceAccount_ZeroizationCheck(t *testing.T) {
	client, cleanup := newTestGRPCServer(t)
	defer cleanup()

	tenantID := "tenant_gsa_zeroize"
	serviceID := "svc_gsa_zeroize"
	privateKeyID := "key-id-zeroize-001"
	wantToken := "ya29.zeroize-ok-token"

	// Phase 1: 500 server → codes.Internal; cache must NOT be populated.
	ts500, _ := newTokenServer(t, http.StatusInternalServerError, "")
	pemKey := generateTestRSAKey(t)
	blob500 := buildStoredBlob(t, pemKey, privateKeyID, ts500.URL, "https://www.googleapis.com/auth/cloud-platform")
	googleserviceaccount.GlobalCache.Invalidate(tenantID, serviceID, privateKeyID)
	putGSACredential(t, client, tenantID, serviceID, blob500)

	ctx := context.Background()
	_, err := client.GetCredential(ctx, &vaultv1.GetCredentialRequest{
		TenantId:   tenantID,
		ServiceId:  serviceID,
		KeyVersion: 0,
	})
	if err == nil {
		t.Fatal("expected error from 500 endpoint in zeroize test")
	}

	// Confirm cache was NOT populated on error.
	if tok, ok := googleserviceaccount.GlobalCache.Get(tenantID, serviceID, privateKeyID); ok {
		t.Errorf("cache should be empty after token-fetch error, got %q", tok)
	}

	// Phase 2: Replace with 200 server → success; Value == wantToken.
	ts200, _ := newTokenServer(t, http.StatusOK, wantToken)
	blob200 := buildStoredBlob(t, pemKey, privateKeyID, ts200.URL, "https://www.googleapis.com/auth/cloud-platform")
	putGSACredential(t, client, tenantID, serviceID, blob200)

	getResp, err := client.GetCredential(ctx, &vaultv1.GetCredentialRequest{
		TenantId:   tenantID,
		ServiceId:  serviceID,
		KeyVersion: 0,
	})
	if err != nil {
		t.Fatalf("GetCredential after replacing with 200 server: %v", err)
	}
	if string(getResp.Value) != wantToken {
		t.Errorf("GetCredential Value=%q, want %q", getResp.Value, wantToken)
	}

	// Cleanup.
	googleserviceaccount.GlobalCache.Invalidate(tenantID, serviceID, privateKeyID)
}
