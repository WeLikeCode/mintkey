//go:build integration

package store

import (
	"bytes"
	"context"
	"database/sql"
	"errors"
	"log/slog"
	"strings"
	"testing"
)

// TestHashiCorp_TokenNotLogged verifies that neither the secret_id nor the
// Vault client token (recognised by the "hvs." prefix) appear in log output
// produced during NewHashiCorp (AppRole login) and a Get call.
func TestHashiCorp_TokenNotLogged(t *testing.T) {
	addr, cleanup := startVaultContainer(t)
	defer cleanup()

	roleID, secretID := setupAppRole(t, addr)

	// Capture all slog output to a bytes.Buffer.
	var buf bytes.Buffer
	logger := slog.New(slog.NewTextHandler(&buf, &slog.HandlerOptions{
		Level: slog.LevelDebug,
	}))

	ctx := context.Background()
	st, err := NewHashiCorp(ctx, HashiCorpConfig{
		Addr:     addr,
		Mount:    "secret",
		Prefix:   "mintkey",
		RoleID:   roleID,
		SecretID: secretID,
		Logger:   logger,
	})
	if err != nil {
		t.Fatalf("NewHashiCorp: %v", err)
	}
	defer st.Close()

	// Execute a Get call that returns not-found (no data written yet for this key).
	_, getErr := st.Get(ctx, "tenant-noleak", "svc-noleak", 0)
	// not-found is expected; any other error is a test failure.
	if getErr != nil && !errors.Is(getErr, sql.ErrNoRows) {
		// Also tolerate "not found" message wrapping ErrNoRows.
		if !strings.Contains(getErr.Error(), "no rows") && !strings.Contains(getErr.Error(), "not found") {
			t.Fatalf("Get: unexpected error %v", getErr)
		}
	}

	logOutput := buf.String()
	t.Logf("captured log output:\n%s", logOutput)

	// Assert secret_id is not present in logs.
	if strings.Contains(logOutput, secretID) {
		t.Errorf("secret_id value found in log output — security constraint NFR-1 violated")
	}

	// Assert no Vault service token (identified by "hvs." prefix) in logs.
	if strings.Contains(logOutput, "hvs.") {
		t.Errorf("vault client token (hvs. prefix) found in log output — security constraint NFR-1 violated")
	}
}
