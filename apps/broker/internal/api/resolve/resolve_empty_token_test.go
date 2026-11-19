package resolve_test

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/mintkey/mintkey/services/broker/internal/api/resolve"
)

type emptyTokenCountingStore struct {
	lookups    int
	agentCalls int
}

func (s *emptyTokenCountingStore) LookupByFingerprint(context.Context, string, string) (*resolve.KeyRow, error) {
	s.lookups++
	return nil, nil
}

func (s *emptyTokenCountingStore) AgentActive(context.Context, string, string) (bool, error) {
	s.agentCalls++
	return false, nil
}

func TestResolve_EmptyConfiguredToken_RefusesEveryRequest_C_db03b7e7(t *testing.T) {
	store := &emptyTokenCountingStore{}
	h := resolve.NewHandler(store, "")

	body, err := json.Marshal(map[string]any{
		"key_fingerprint": "aabbccdd",
		"presented_key":   "mk_svckey_X",
		"service_id":      "svc_01",
		"tenant_id":       "tenant_01",
	})
	if err != nil {
		t.Fatal(err)
	}

	cases := []struct {
		name      string
		header    string
		setHeader bool
	}{
		{name: "no header"},
		{name: "empty header", header: "", setHeader: true},
		{name: "any header", header: "some-token", setHeader: true},
	}

	for _, tc := range cases {
		req := httptest.NewRequest(http.MethodPost, "/v1/api-keys/resolve", bytes.NewReader(body))
		req.Header.Set("Content-Type", "application/json")
		if tc.setHeader {
			req.Header.Set("X-Mintkey-Service-Token", tc.header)
		}

		w := httptest.NewRecorder()
		h.ServeHTTP(w, req)

		if w.Code != http.StatusUnauthorized {
			t.Fatalf("%s: status = %d, want 401; body: %s", tc.name, w.Code, w.Body.String())
		}
		var resp map[string]any
		if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
			t.Fatalf("%s: unmarshal response: %v", tc.name, err)
		}
		if resp["mintkey:code"] != "unauthenticated" {
			t.Fatalf("%s: mintkey:code = %v, want unauthenticated", tc.name, resp["mintkey:code"])
		}
		if store.lookups != 0 || store.agentCalls != 0 {
			t.Fatalf("%s: store calls = LookupByFingerprint %d, AgentActive %d; want 0, 0",
				tc.name, store.lookups, store.agentCalls)
		}
	}
}
