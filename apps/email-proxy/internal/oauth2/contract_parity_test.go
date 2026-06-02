// Package oauth2_test — contract-parity tests for Manager.refresh ↔ admin-api handler.
//
// Wave-2 batch audit found a HARD BLOCKER: the pre-fix Manager sent
// {tenant_id, service_id, refresh_token} as a JSON body with no
// X-Mintkey-Service-Token header.  admin-api's handler expects:
//   - query string: tenant_id, service_id
//   - header: X-Mintkey-Service-Token
//   - empty body (admin-api fetches refresh_token from vault — NFR-17)
//
// This file contains an httptest-based test that asserts the EXACT HTTP
// contract the admin-api handler enforces, so that any future regression
// (e.g. accidentally re-adding a body field or dropping the header) fails
// immediately.
//
// Running this test against the pre-fix code WILL fail with one or more
// of the following:
//   - FAIL: X-Mintkey-Service-Token header missing
//   - FAIL: tenant_id query param missing
//   - FAIL: service_id query param missing
//   - FAIL: body is not empty (refresh_token leaked in body)
package oauth2_test

import (
	"context"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"regexp"
	"strings"
	"testing"
	"time"

	"github.com/mintkey/mintkey/services/email-proxy/internal/oauth2"
)

const (
	testServiceToken = "sk_test_service_token_32bytes_xyz"
	testTenantID     = "tnt_contract_parity_tenant"
	testServiceID    = "svc_contract_parity_service"
	testAccessToken  = "at_contract_parity_access_token"
)

// providerRefreshPathRE matches /v1/internal/oauth2/{provider}/refresh.
var providerRefreshPathRE = regexp.MustCompile(`^/v1/internal/oauth2/[a-z]+/refresh$`)

// contractCheckingServer builds an httptest.Server whose handler enforces
// the exact admin-api HTTP contract for POST /v1/internal/oauth2/{provider}/refresh.
//
// It records all violations in a slice so the calling test can assert on
// them after the Manager call returns.
func contractCheckingServer(
	t *testing.T,
	violations *[]string,
) *httptest.Server {
	t.Helper()

	mux := http.NewServeMux()
	mux.HandleFunc("/v1/internal/oauth2/", func(w http.ResponseWriter, r *http.Request) {
		// 1. Method must be POST.
		if r.Method != http.MethodPost {
			*violations = append(*violations, "method must be POST, got "+r.Method)
		}

		// 2. Path must match /v1/internal/oauth2/{provider}/refresh.
		if !providerRefreshPathRE.MatchString(r.URL.Path) {
			*violations = append(*violations, "path did not match provider refresh pattern: "+r.URL.Path)
		}

		// 3. X-Mintkey-Service-Token header must be present and match.
		hdr := r.Header.Get("X-Mintkey-Service-Token")
		if hdr == "" {
			*violations = append(*violations, "X-Mintkey-Service-Token header missing")
		} else if hdr != testServiceToken {
			*violations = append(*violations, "X-Mintkey-Service-Token mismatch: got "+hdr)
		}

		// 4. tenant_id query param must be present and non-empty.
		if tID := r.URL.Query().Get("tenant_id"); tID == "" {
			*violations = append(*violations, "tenant_id query param missing or empty")
		}

		// 5. service_id query param must be present and non-empty.
		if sID := r.URL.Query().Get("service_id"); sID == "" {
			*violations = append(*violations, "service_id query param missing or empty")
		}

		// 6. Body must be empty — no refresh_token in transit (NFR-17).
		rawBody, readErr := io.ReadAll(r.Body)
		if readErr == nil && len(rawBody) > 0 {
			bodyStr := strings.TrimSpace(string(rawBody))
			if bodyStr != "" {
				*violations = append(*violations, "body must be empty (NFR-17), got: "+bodyStr)
			}
		}

		// Respond with a valid refresh response so GetAccessToken can complete.
		resp := adminAPIRefreshResponse{
			AccessToken: testAccessToken,
			ExpiresAt:   time.Now().Add(10 * time.Minute),
		}
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		json.NewEncoder(w).Encode(resp) //nolint:errcheck
	})

	srv := httptest.NewServer(mux)
	t.Cleanup(srv.Close)
	return srv
}

// TestContractParity_RefreshEndpointShape asserts that Manager.refresh sends:
//   - POST to /v1/internal/oauth2/{provider}/refresh
//   - X-Mintkey-Service-Token header matching the manager's serviceToken
//   - tenant_id and service_id as URL query parameters
//   - empty body (no refresh_token in transit — NFR-17)
func TestContractParity_RefreshEndpointShape(t *testing.T) {
	var violations []string
	srv := contractCheckingServer(t, &violations)

	m := oauth2.NewManager(srv.URL, &stubVault{}, testServiceToken)

	tok, err := m.GetAccessToken(context.Background(), testTenantID, testServiceID)
	if err != nil {
		t.Fatalf("GetAccessToken returned unexpected error: %v", err)
	}
	if tok == "" {
		t.Fatal("GetAccessToken returned empty token")
	}

	// All contract violations collected during the HTTP exchange.
	if len(violations) > 0 {
		t.Errorf("HTTP contract violations (%d):", len(violations))
		for _, v := range violations {
			t.Errorf("  - %s", v)
		}
	}
}

// TestContractParity_NoRefreshTokenInBody is a more targeted assertion that
// the request body contains no refresh_token field at all — covers the NFR-17
// "proxy logging chain can observe the wire" threat model.
func TestContractParity_NoRefreshTokenInBody(t *testing.T) {
	var capturedBodies []string

	mux := http.NewServeMux()
	mux.HandleFunc("/v1/internal/oauth2/", func(w http.ResponseWriter, r *http.Request) {
		raw, _ := io.ReadAll(r.Body)
		capturedBodies = append(capturedBodies, string(raw))

		resp := adminAPIRefreshResponse{
			AccessToken: "at_nfr17_check",
			ExpiresAt:   time.Now().Add(10 * time.Minute),
		}
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(resp) //nolint:errcheck
	})
	srv := httptest.NewServer(mux)
	defer srv.Close()

	m := oauth2.NewManager(srv.URL, &stubVault{}, testServiceToken)
	if _, err := m.GetAccessToken(context.Background(), testTenantID, testServiceID); err != nil {
		t.Fatalf("GetAccessToken: %v", err)
	}

	for i, body := range capturedBodies {
		if strings.Contains(body, "refresh_token") {
			t.Errorf("request[%d] body contains 'refresh_token' — NFR-17 violation: %q", i, body)
		}
	}
}

// TestContractParity_ServiceTokenHeader verifies that the correct service token
// is sent in the X-Mintkey-Service-Token header on every refresh call.
func TestContractParity_ServiceTokenHeader(t *testing.T) {
	var capturedTokens []string

	mux := http.NewServeMux()
	mux.HandleFunc("/v1/internal/oauth2/", func(w http.ResponseWriter, r *http.Request) {
		capturedTokens = append(capturedTokens, r.Header.Get("X-Mintkey-Service-Token"))
		resp := adminAPIRefreshResponse{
			AccessToken: "at_header_check",
			ExpiresAt:   time.Now().Add(10 * time.Minute),
		}
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(resp) //nolint:errcheck
	})
	srv := httptest.NewServer(mux)
	defer srv.Close()

	const myToken = "my_unique_service_token_abc123"
	m := oauth2.NewManager(srv.URL, &stubVault{}, myToken)
	if _, err := m.GetAccessToken(context.Background(), testTenantID, testServiceID); err != nil {
		t.Fatalf("GetAccessToken: %v", err)
	}

	if len(capturedTokens) == 0 {
		t.Fatal("no outbound request captured")
	}
	for i, tok := range capturedTokens {
		if tok != myToken {
			t.Errorf("request[%d]: X-Mintkey-Service-Token = %q, want %q", i, tok, myToken)
		}
	}
}

// TestContractParity_QueryParams verifies tenant_id and service_id appear in
// the query string, not the body.
func TestContractParity_QueryParams(t *testing.T) {
	var capturedQueries []string

	mux := http.NewServeMux()
	mux.HandleFunc("/v1/internal/oauth2/", func(w http.ResponseWriter, r *http.Request) {
		capturedQueries = append(capturedQueries, r.URL.RawQuery)
		resp := adminAPIRefreshResponse{
			AccessToken: "at_qp_check",
			ExpiresAt:   time.Now().Add(10 * time.Minute),
		}
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(resp) //nolint:errcheck
	})
	srv := httptest.NewServer(mux)
	defer srv.Close()

	m := oauth2.NewManager(srv.URL, &stubVault{}, testServiceToken)
	if _, err := m.GetAccessToken(context.Background(), "tnt_qp_test", "svc_qp_test"); err != nil {
		t.Fatalf("GetAccessToken: %v", err)
	}

	if len(capturedQueries) == 0 {
		t.Fatal("no outbound request captured")
	}
	q := capturedQueries[0]
	if !strings.Contains(q, "tenant_id=") {
		t.Errorf("query string %q missing tenant_id parameter", q)
	}
	if !strings.Contains(q, "service_id=") {
		t.Errorf("query string %q missing service_id parameter", q)
	}
	if strings.Contains(q, "tnt_qp_test") && !strings.Contains(q, "tenant_id=tnt_qp_test") {
		// The value appears somewhere but not as the correct key — flag it.
		t.Errorf("tenant_id value is not properly bound in query: %q", q)
	}
}
