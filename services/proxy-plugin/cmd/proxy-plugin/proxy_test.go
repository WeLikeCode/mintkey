// Package main tests the proxy HTTP handler.
package main

import (
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/mintkey/mintkey/services/proxy-plugin/internal/config"
	proxyjwt "github.com/mintkey/mintkey/services/proxy-plugin/internal/jwt"
	"github.com/mintkey/mintkey/services/proxy-plugin/internal/vault"
)

func testHandler() *proxyHandler {
	cfg := &config.Config{
		VaultAddrGRPC: "localhost:1",
		JWKSEndpoint:  "http://localhost:1/.well-known/jwks.json",
		PluginPort:    8086,
		DefaultTarget: "http://localhost:1",
	}
	return newProxyHandler(cfg, vault.NewClient("localhost:1", ""), proxyjwt.NewJWKSRefreshLimiter())
}

// TestProxy_MissingAuthHeader verifies that requests without Authorization → 401.
func TestProxy_MissingAuthHeader(t *testing.T) {
	h := testHandler()
	req := httptest.NewRequest(http.MethodGet, "/", nil)
	rw := httptest.NewRecorder()
	h.ServeHTTP(rw, req)
	if rw.Code != http.StatusUnauthorized {
		t.Fatalf("expected 401, got %d", rw.Code)
	}
}

// TestProxy_InvalidJWT verifies that a non-JWT Authorization header → 401.
func TestProxy_InvalidJWT(t *testing.T) {
	h := testHandler()
	req := httptest.NewRequest(http.MethodGet, "/", nil)
	req.Header.Set("Authorization", "Bearer not.a.jwt")
	rw := httptest.NewRecorder()
	h.ServeHTTP(rw, req)
	if rw.Code != http.StatusUnauthorized {
		t.Fatalf("expected 401, got %d", rw.Code)
	}
}
