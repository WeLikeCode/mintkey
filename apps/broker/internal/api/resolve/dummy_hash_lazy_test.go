package resolve_test

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"runtime"
	"testing"

	"github.com/mintkey/mintkey/services/broker/internal/api/resolve"
)

// totalAllocAtStart is runtime.MemStats.TotalAlloc read by TestMain before any
// test runs. The resolve package initialises before TestMain, so anything its
// package-level initialisation allocated (the dummy hash, today) is counted.
var totalAllocAtStart uint64

func TestMain(m *testing.M) {
	var ms runtime.MemStats
	runtime.ReadMemStats(&ms)
	totalAllocAtStart = ms.TotalAlloc
	os.Exit(m.Run())
}

func TestPackageInit_AllocatesUnder32MiB_C_91d7b471(t *testing.T) {
	if totalAllocAtStart >= 33554432 {
		t.Fatalf("package initialisation allocated %d bytes (TotalAlloc), want < %d", totalAllocAtStart, 33554432)
	}
}

// unknownFingerprintStore finds nothing for any lookup, so the handler takes
// its unknown-fingerprint (constant-time) path.
type unknownFingerprintStore struct{}

func (unknownFingerprintStore) LookupByFingerprint(context.Context, string, string) (*resolve.KeyRow, error) {
	return nil, nil
}

func (unknownFingerprintStore) AgentActive(context.Context, string, string) (bool, error) {
	return false, nil
}

func totalAlloc() uint64 {
	var ms runtime.MemStats
	runtime.ReadMemStats(&ms)
	return ms.TotalAlloc
}

func TestUnknownFingerprint_StillRefusedTwice_C_89e65307(t *testing.T) {
	const serviceToken = "svcid_proxy_dummy_hash_lazy_test"
	h := resolve.NewHandler(unknownFingerprintStore{}, serviceToken)

	body, err := json.Marshal(map[string]any{
		"key_fingerprint": "deadbeef",
		"presented_key":   "not-the-registered-key",
		"service_id":      "svc_01",
		"tenant_id":       "tenant_01",
	})
	if err != nil {
		t.Fatal(err)
	}

	call := func(iteration int) {
		req := httptest.NewRequest(http.MethodPost, "/v1/api-keys/resolve", bytes.NewReader(body))
		req.Header.Set("Content-Type", "application/json")
		req.Header.Set("X-Mintkey-Service-Token", serviceToken)
		w := httptest.NewRecorder()
		h.ServeHTTP(w, req)

		if w.Code != http.StatusUnauthorized {
			t.Fatalf("call %d: status = %d, want 401; body: %s", iteration, w.Code, w.Body.String())
		}
		var resp map[string]any
		if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
			t.Fatalf("call %d: unmarshal response: %v", iteration, err)
		}
		if resp["mintkey:code"] != "api_key_invalid" {
			t.Fatalf("call %d: mintkey:code = %v, want api_key_invalid", iteration, resp["mintkey:code"])
		}
	}

	before := totalAlloc()
	call(1)
	afterFirst := totalAlloc()
	call(2)
	afterSecond := totalAlloc()

	// The first unknown-fingerprint request computes the dummy hash (an
	// Argon2id derivation of 64 MiB) and later requests reuse it, so the first
	// call allocates about 64 MiB more than the second. Half of that separates
	// the two implementations.
	firstGrew := afterFirst - before
	secondGrew := afterSecond - afterFirst
	if firstGrew < secondGrew+33554432 {
		t.Fatalf("first unknown-fingerprint call allocated %d bytes, second %d: the dummy hash was not computed on first use and reused afterwards",
			firstGrew, secondGrew)
	}
}
