//go:build integration

package store

import (
	"bytes"
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"sync"
	"testing"
	"time"

	"github.com/testcontainers/testcontainers-go"
	"github.com/testcontainers/testcontainers-go/wait"
)

const (
	vaultImage     = "hashicorp/vault:1.18"
	vaultDevToken  = "test-root-token"
	vaultDevPort   = "8200"
)

// startVaultContainer spins up a HashiCorp Vault dev container and returns
// the HTTP address (http://host:port) reachable from the test process.
func startVaultContainer(t *testing.T) (string, func()) {
	t.Helper()

	ctx := context.Background()
	req := testcontainers.ContainerRequest{
		Image:        vaultImage,
		ExposedPorts: []string{vaultDevPort + "/tcp"},
		Env: map[string]string{
			"VAULT_DEV_ROOT_TOKEN_ID":  vaultDevToken,
			"VAULT_DEV_LISTEN_ADDRESS": "0.0.0.0:" + vaultDevPort,
		},
		Cmd: []string{"server", "-dev", "-dev-listen-address=0.0.0.0:" + vaultDevPort},
		WaitingFor: wait.ForHTTP("/v1/sys/health").
			WithPort(vaultDevPort + "/tcp").
			WithStartupTimeout(60 * time.Second),
	}

	ctr, err := testcontainers.GenericContainer(ctx, testcontainers.GenericContainerRequest{
		ContainerRequest: req,
		Started:          true,
	})
	if err != nil {
		t.Fatalf("start vault container: %v", err)
	}

	mappedPort, err := ctr.MappedPort(ctx, vaultDevPort)
	if err != nil {
		_ = ctr.Terminate(ctx)
		t.Fatalf("get mapped port: %v", err)
	}

	host, err := ctr.Host(ctx)
	if err != nil {
		_ = ctr.Terminate(ctx)
		t.Fatalf("get host: %v", err)
	}

	addr := fmt.Sprintf("http://%s:%s", host, mappedPort.Port())
	cleanup := func() { _ = ctr.Terminate(context.Background()) }
	return addr, cleanup
}

// vaultHTTP is a minimal helper that calls the Vault HTTP API with the dev root token.
func vaultHTTP(t *testing.T, addr, method, path string, body any) map[string]any {
	t.Helper()
	var bodyReader io.Reader
	if body != nil {
		b, err := json.Marshal(body)
		if err != nil {
			t.Fatalf("marshal body: %v", err)
		}
		bodyReader = bytes.NewReader(b)
	}
	req, err := http.NewRequestWithContext(context.Background(), method, addr+path, bodyReader)
	if err != nil {
		t.Fatalf("new request: %v", err)
	}
	req.Header.Set("X-Vault-Token", vaultDevToken)
	if body != nil {
		req.Header.Set("Content-Type", "application/json")
	}
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		t.Fatalf("vault HTTP %s %s: %v", method, path, err)
	}
	defer resp.Body.Close()
	data, _ := io.ReadAll(resp.Body)
	if resp.StatusCode >= 400 {
		// Some calls return 204; that's fine.
		t.Fatalf("vault HTTP %s %s: status %d body %s", method, path, resp.StatusCode, data)
	}
	var result map[string]any
	if len(data) > 0 {
		_ = json.Unmarshal(data, &result)
	}
	return result
}

// setupAppRole configures AppRole in the Vault dev container and returns
// (roleID, secretID).
func setupAppRole(t *testing.T, addr string) (string, string) {
	t.Helper()

	// Enable AppRole auth.
	vaultHTTP(t, addr, http.MethodPost, "/v1/sys/auth/approle", map[string]any{"type": "approle"})

	// Write policy.
	policyHCL := `path "secret/data/mintkey/*" { capabilities = ["create","read","update","delete","list"] }
path "secret/metadata/mintkey/*" { capabilities = ["read","list","delete"] }`
	vaultHTTP(t, addr, http.MethodPost, "/v1/sys/policies/acl/mintkey", map[string]any{"policy": policyHCL})

	// Create role.
	vaultHTTP(t, addr, http.MethodPost, "/v1/auth/approle/role/mintkey", map[string]any{
		"token_ttl":     "20m",
		"token_max_ttl": "1h",
		"policies":      []string{"mintkey"},
	})

	// Read role_id.
	result := vaultHTTP(t, addr, http.MethodGet, "/v1/auth/approle/role/mintkey/role-id", nil)
	roleID, _ := result["data"].(map[string]any)["role_id"].(string)
	if roleID == "" {
		t.Fatal("empty role_id from Vault")
	}

	// Generate secret_id.
	result = vaultHTTP(t, addr, http.MethodPost, "/v1/auth/approle/role/mintkey/secret-id", nil)
	secretID, _ := result["data"].(map[string]any)["secret_id"].(string)
	if secretID == "" {
		t.Fatal("empty secret_id from Vault")
	}

	return roleID, secretID
}

// newTestHashiCorp creates a HashiCorpStore pointed at a running test Vault.
func newTestHashiCorp(t *testing.T, addr, roleID, secretID string) *HashiCorpStore {
	t.Helper()
	ctx := context.Background()
	st, err := NewHashiCorp(ctx, HashiCorpConfig{
		Addr:     addr,
		Mount:    "secret",
		Prefix:   "mintkey",
		RoleID:   roleID,
		SecretID: secretID,
	})
	if err != nil {
		t.Fatalf("NewHashiCorp: %v", err)
	}
	return st
}

func TestHashiCorp_Conformance(t *testing.T) {
	addr, cleanup := startVaultContainer(t)
	defer cleanup()

	roleID, secretID := setupAppRole(t, addr)

	ctx := context.Background()
	st := newTestHashiCorp(t, addr, roleID, secretID)
	defer st.Close()

	const (
		tenant = "tenant-conformance"
		svc    = "svc-conformance"
	)

	baseRec := CredentialRecord{
		CredentialID:  "cred_test_01",
		TenantID:      tenant,
		ServiceID:     svc,
		AuthScheme:    1,
		WrappedDEK:    []byte("wrappeddek-data-1"),
		EncPayload:    []byte("encpayload-data-1"),
		TargetURL:     "https://api.example.com",
		HeaderName:    "X-API-Key",
		QueryParam:    "",
		TargetAddress: "",
		SSHUser:       "",
		CreatedAt:     time.Now().UnixNano(),
	}

	// (a) Put v1 — assert keyVersion == 1
	t.Run("a_put_v1", func(t *testing.T) {
		kv, err := st.Put(ctx, baseRec)
		if err != nil {
			t.Fatalf("Put: %v", err)
		}
		if kv != 1 {
			t.Errorf("keyVersion: got %d, want 1", kv)
		}
	})

	// (b) Get(0) — is_current=true, bytes match
	t.Run("b_get_current", func(t *testing.T) {
		got, err := st.Get(ctx, tenant, svc, 0)
		if err != nil {
			t.Fatalf("Get(0): %v", err)
		}
		if !got.IsCurrent {
			t.Errorf("IsCurrent: got false, want true")
		}
		if !bytes.Equal(got.WrappedDEK, baseRec.WrappedDEK) {
			t.Errorf("WrappedDEK mismatch")
		}
		if !bytes.Equal(got.EncPayload, baseRec.EncPayload) {
			t.Errorf("EncPayload mismatch")
		}
	})

	// (c) Get(1) — same as current
	t.Run("c_get_v1", func(t *testing.T) {
		got, err := st.Get(ctx, tenant, svc, 1)
		if err != nil {
			t.Fatalf("Get(1): %v", err)
		}
		if !bytes.Equal(got.WrappedDEK, baseRec.WrappedDEK) {
			t.Errorf("WrappedDEK mismatch")
		}
		if !bytes.Equal(got.EncPayload, baseRec.EncPayload) {
			t.Errorf("EncPayload mismatch")
		}
	})

	// (d) Put v2 — assert keyVersion == 2
	rec2 := baseRec
	rec2.CredentialID = "cred_test_02"
	rec2.WrappedDEK = []byte("wrappeddek-data-2")
	rec2.EncPayload = []byte("encpayload-data-2")
	t.Run("d_put_v2", func(t *testing.T) {
		kv, err := st.Put(ctx, rec2)
		if err != nil {
			t.Fatalf("Put v2: %v", err)
		}
		if kv != 2 {
			t.Errorf("keyVersion: got %d, want 2", kv)
		}
	})

	// (e) Get(0) after v2 — should return v2 with IsCurrent=true
	t.Run("e_get_current_after_v2", func(t *testing.T) {
		got, err := st.Get(ctx, tenant, svc, 0)
		if err != nil {
			t.Fatalf("Get(0): %v", err)
		}
		if got.KeyVersion != 2 {
			t.Errorf("KeyVersion: got %d, want 2", got.KeyVersion)
		}
		if !got.IsCurrent {
			t.Errorf("IsCurrent: got false, want true")
		}
	})

	// (f) Get(1) — should have IsCurrent=false (demoted by v2 put)
	t.Run("f_get_v1_demoted", func(t *testing.T) {
		got, err := st.Get(ctx, tenant, svc, 1)
		if err != nil {
			t.Fatalf("Get(1): %v", err)
		}
		if got.IsCurrent {
			t.Errorf("IsCurrent: got true, want false (v1 should be demoted)")
		}
	})

	// (g) Revoke(1) — non-current, should succeed
	t.Run("g_revoke_v1", func(t *testing.T) {
		if err := st.Revoke(ctx, tenant, svc, 1); err != nil {
			t.Fatalf("Revoke(1): %v", err)
		}
	})

	// (h) Revoke(2) — current version, should return ErrRevokeCurrent
	t.Run("h_revoke_current_err", func(t *testing.T) {
		err := st.Revoke(ctx, tenant, svc, 2)
		if !errors.Is(err, ErrRevokeCurrent) {
			t.Errorf("Revoke(2): got %v, want ErrRevokeCurrent", err)
		}
	})

	// (i) Get(999) — not found -> sql.ErrNoRows
	t.Run("i_get_notfound", func(t *testing.T) {
		_, err := st.Get(ctx, tenant, svc, 999)
		if err == nil {
			t.Fatal("Get(999): expected error, got nil")
		}
		if !errors.Is(err, sql.ErrNoRows) {
			t.Errorf("Get(999): got %v, want errors.Is(err, sql.ErrNoRows)", err)
		}
	})

	// (j) ListVersions — should return 2 versions (v1 revoked, v2 current), DEK/payload empty
	t.Run("j_list_versions", func(t *testing.T) {
		vers, err := st.ListVersions(ctx, tenant, svc, 0, 50)
		if err != nil {
			t.Fatalf("ListVersions: %v", err)
		}
		if len(vers) != 2 {
			t.Fatalf("ListVersions: got %d, want 2", len(vers))
		}
		// Versions must be ascending.
		if vers[0].KeyVersion != 1 || vers[1].KeyVersion != 2 {
			t.Errorf("versions: got [%d,%d], want [1,2]", vers[0].KeyVersion, vers[1].KeyVersion)
		}
		// WrappedDEK and EncPayload must be empty in list results.
		for _, v := range vers {
			if len(v.WrappedDEK) > 0 {
				t.Errorf("v%d: WrappedDEK should be empty in ListVersions", v.KeyVersion)
			}
			if len(v.EncPayload) > 0 {
				t.Errorf("v%d: EncPayload should be empty in ListVersions", v.KeyVersion)
			}
		}
	})

	// (k) Concurrent Put — 5 goroutines, all for a DIFFERENT (tenant,svc) pair to avoid
	// conflicts with the conformance pair above, assert 5 distinct key_versions.
	t.Run("k_concurrent_put", func(t *testing.T) {
		const conTenant = "tenant-concurrent"
		const conSvc = "svc-concurrent"
		const n = 5

		var mu sync.Mutex
		versions := make(map[uint32]bool)
		var wg sync.WaitGroup
		errs := make([]error, n)

		for i := 0; i < n; i++ {
			wg.Add(1)
			go func(idx int) {
				defer wg.Done()
				rec := CredentialRecord{
					CredentialID:  fmt.Sprintf("cred_con_%02d", idx),
					TenantID:      conTenant,
					ServiceID:     conSvc,
					AuthScheme:    1,
					WrappedDEK:    []byte(fmt.Sprintf("dek-%d", idx)),
					EncPayload:    []byte(fmt.Sprintf("payload-%d", idx)),
					CreatedAt:     time.Now().UnixNano(),
				}
				kv, err := st.Put(context.Background(), rec)
				if err != nil {
					errs[idx] = err
					return
				}
				mu.Lock()
				versions[kv] = true
				mu.Unlock()
			}(i)
		}
		wg.Wait()

		for i, e := range errs {
			if e != nil {
				t.Errorf("goroutine %d error: %v", i, e)
			}
		}
		if len(versions) != n {
			t.Errorf("concurrent Put: got %d distinct versions, want %d (versions: %v)", len(versions), n, versions)
		}
	})
}
