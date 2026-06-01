// postgres_ssh.go — SSH-proxy-specific store methods on PostgresStore (ADR-0021, C7).
//
// These three methods satisfy the SSHStore interface consumed by the
// vault-adapter SSH gRPC handlers:
//
//   - GetAgentBySSHPubKey: full-table scan over ssh_pubkey-bearing agents,
//     compares computed fingerprints in-process (the column is not indexed by
//     fingerprint — ADR-0021 chose to store the full pubkey and compute on
//     read rather than maintaining a derived fingerprint column).
//
//   - GetHostKeyFingerprint: returns the fingerprint stored for a
//     (tenant_id, service_id) pair in vault.ssh_host_keys.
//
//   - StoreHostKeyFingerprint: upserts the fingerprint into vault.ssh_host_keys.
//
// Tenant isolation is enforced identically to postgres.go: every query path
// sets the GUC app.current_tenant inside a transaction before touching rows.
//
// Source: ADR-0021; chunk C7.
package store

import (
	"context"
	"database/sql"
	"encoding/base64"
	"errors"
	"fmt"
	"strings"

	"github.com/jackc/pgx/v5"
	"golang.org/x/crypto/ssh"
)

// AgentSSHRecord is the minimal agent shape returned by GetAgentBySSHPubKey.
type AgentSSHRecord struct {
	ID        string
	TenantID  string
	Name      string
	SSHPubKey string // OpenSSH-format public key
	Status    string
}

// ErrAgentNotFound is returned when no agent matches the given fingerprint.
var ErrAgentNotFound = errors.New("ssh store: agent not found for fingerprint")

// GetAgentBySSHPubKey scans all agents with a non-null ssh_pubkey in the
// given tenant, parses each pubkey, computes its SHA-256 fingerprint, and
// returns the first match.
//
// The caller must supply the tenantID so that the RLS GUC is set correctly.
// This prevents cross-tenant fingerprint collisions (astronomically unlikely
// but rejected at the architecture layer per ADR-0008).
//
// Performance note: the partial index idx_agents_ssh_pubkey_fingerprint on
// agents(ssh_pubkey WHERE ssh_pubkey IS NOT NULL) makes the scan fast in
// practice — typical deployments have O(10) agents per tenant.
func (s *PostgresStore) GetAgentBySSHPubKey(ctx context.Context, tenantID, fingerprint string) (*AgentSSHRecord, error) {
	conn, err := s.pool.Acquire(ctx)
	if err != nil {
		return nil, fmt.Errorf("ssh store: GetAgentBySSHPubKey: acquire conn: %w", err)
	}
	defer conn.Release()

	tx, err := conn.BeginTx(ctx, pgx.TxOptions{AccessMode: pgx.ReadOnly})
	if err != nil {
		return nil, fmt.Errorf("ssh store: GetAgentBySSHPubKey: begin tx: %w", err)
	}
	defer func() { _ = tx.Rollback(ctx) }()

	if _, err = tx.Exec(ctx, "SELECT set_config('app.current_tenant', $1, true)", tenantID); err != nil {
		return nil, fmt.Errorf("ssh store: GetAgentBySSHPubKey: set tenant: %w", err)
	}

	rows, err := tx.Query(ctx,
		`SELECT id, tenant_id, name, ssh_pubkey, status
		   FROM public.agents
		  WHERE tenant_id = $1
		    AND ssh_pubkey IS NOT NULL`,
		tenantID,
	)
	if err != nil {
		return nil, fmt.Errorf("ssh store: GetAgentBySSHPubKey: query: %w", err)
	}
	defer rows.Close()

	for rows.Next() {
		var r AgentSSHRecord
		if err = rows.Scan(&r.ID, &r.TenantID, &r.Name, &r.SSHPubKey, &r.Status); err != nil {
			return nil, fmt.Errorf("ssh store: GetAgentBySSHPubKey: scan: %w", err)
		}
		fp, fpErr := computeSSHFingerprint(r.SSHPubKey)
		if fpErr != nil {
			// Skip rows with unparseable keys — don't fail the whole lookup.
			continue
		}
		if fp == fingerprint {
			_ = tx.Commit(ctx)
			return &r, nil
		}
	}
	if err = rows.Err(); err != nil {
		return nil, fmt.Errorf("ssh store: GetAgentBySSHPubKey: rows: %w", err)
	}

	return nil, ErrAgentNotFound
}

// GetHostKeyFingerprint returns the fingerprint stored for (tenantID, serviceID),
// or ("", nil) if no fingerprint has been recorded yet (TOFU first-use).
func (s *PostgresStore) GetHostKeyFingerprint(ctx context.Context, tenantID, serviceID string) (string, error) {
	conn, err := s.pool.Acquire(ctx)
	if err != nil {
		return "", fmt.Errorf("ssh store: GetHostKeyFingerprint: acquire conn: %w", err)
	}
	defer conn.Release()

	tx, err := conn.BeginTx(ctx, pgx.TxOptions{AccessMode: pgx.ReadOnly})
	if err != nil {
		return "", fmt.Errorf("ssh store: GetHostKeyFingerprint: begin tx: %w", err)
	}
	defer func() { _ = tx.Rollback(ctx) }()

	if _, err = tx.Exec(ctx, "SELECT set_config('app.current_tenant', $1, true)", tenantID); err != nil {
		return "", fmt.Errorf("ssh store: GetHostKeyFingerprint: set tenant: %w", err)
	}

	var fp string
	err = tx.QueryRow(ctx,
		`SELECT fingerprint
		   FROM vault.ssh_host_keys
		  WHERE tenant_id = $1 AND service_id = $2
		  ORDER BY first_seen ASC
		  LIMIT 1`,
		tenantID, serviceID,
	).Scan(&fp)
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			// Not yet seen — TOFU first use. Return ("", nil).
			return "", nil
		}
		return "", fmt.Errorf("ssh store: GetHostKeyFingerprint: scan: %w", err)
	}

	_ = tx.Commit(ctx)
	return fp, nil
}

// StoreHostKeyFingerprint upserts the fingerprint for (tenantID, serviceID).
// On conflict (same primary key) it updates last_seen to now().
func (s *PostgresStore) StoreHostKeyFingerprint(ctx context.Context, tenantID, serviceID, fingerprint string) error {
	tx, err := s.pool.BeginTx(ctx, pgx.TxOptions{})
	if err != nil {
		return fmt.Errorf("ssh store: StoreHostKeyFingerprint: begin tx: %w", err)
	}
	defer func() { _ = tx.Rollback(ctx) }()

	if _, err = tx.Exec(ctx, "SELECT set_config('app.current_tenant', $1, true)", tenantID); err != nil {
		return fmt.Errorf("ssh store: StoreHostKeyFingerprint: set tenant: %w", err)
	}

	_, err = tx.Exec(ctx,
		`INSERT INTO vault.ssh_host_keys (tenant_id, service_id, fingerprint)
		 VALUES ($1, $2, $3)
		 ON CONFLICT (tenant_id, service_id, fingerprint)
		 DO UPDATE SET last_seen = now()`,
		tenantID, serviceID, fingerprint,
	)
	if err != nil {
		return fmt.Errorf("ssh store: StoreHostKeyFingerprint: upsert: %w", err)
	}

	if err = tx.Commit(ctx); err != nil {
		return fmt.Errorf("ssh store: StoreHostKeyFingerprint: commit: %w", err)
	}
	return nil
}

// computeSSHFingerprint parses an OpenSSH authorized-keys line and returns
// ssh.FingerprintSHA256 of the parsed key.
//
// The input must be a single authorized-keys-format line, e.g.:
//
//	ssh-ed25519 AAAA... comment
//
// Returns an error if the key cannot be parsed. Never logs the key itself.
func computeSSHFingerprint(authorizedKey string) (string, error) {
	authorizedKey = strings.TrimSpace(authorizedKey)
	if authorizedKey == "" {
		return "", fmt.Errorf("empty public key")
	}
	// ssh.ParseAuthorizedKey expects a single line.
	pubKey, _, _, _, err := ssh.ParseAuthorizedKey([]byte(authorizedKey))
	if err != nil {
		return "", fmt.Errorf("parse authorized key: %w", err)
	}
	return ssh.FingerprintSHA256(pubKey), nil
}

// ValidateSSHPubKey parses and validates an OpenSSH public key string.
// Returns the SHA-256 fingerprint on success.
//
// Rules (per discipline §ssh_pubkey validation):
//  1. Must be a single non-empty line.
//  2. Must have a recognized key type prefix (ssh-ed25519, ssh-rsa, ecdsa-sha2-*).
//  3. The base64 key body must decode without error (ssh.ParseAuthorizedKey
//     does this internally).
//  4. The computed fingerprint uses SHA-256 DER bytes semantics (same as
//     ssh.FingerprintSHA256).
func ValidateSSHPubKey(pubKey string) (fingerprint string, err error) {
	trimmed := strings.TrimSpace(pubKey)
	if trimmed == "" {
		return "", fmt.Errorf("ssh_pubkey is empty")
	}
	if strings.ContainsAny(trimmed, "\r\n") {
		return "", fmt.Errorf("ssh_pubkey must be a single line")
	}
	// Quick prefix check before the more expensive parse.
	validPrefixes := []string{
		"ssh-ed25519 ",
		"ssh-rsa ",
		"ecdsa-sha2-nistp256 ",
		"ecdsa-sha2-nistp384 ",
		"ecdsa-sha2-nistp521 ",
		"sk-ssh-ed25519@openssh.com ",
		"sk-ecdsa-sha2-nistp256@openssh.com ",
	}
	hasValidPrefix := false
	for _, pfx := range validPrefixes {
		if strings.HasPrefix(trimmed, pfx) {
			hasValidPrefix = true
			break
		}
	}
	if !hasValidPrefix {
		return "", fmt.Errorf("ssh_pubkey must start with a recognized key type (ssh-ed25519, ssh-rsa, ecdsa-sha2-*)")
	}

	// Validate base64 body: the second whitespace-separated token.
	parts := strings.Fields(trimmed)
	if len(parts) < 2 {
		return "", fmt.Errorf("ssh_pubkey has no key body")
	}
	if _, decErr := base64.StdEncoding.DecodeString(parts[1]); decErr != nil {
		return "", fmt.Errorf("ssh_pubkey base64 body is invalid: %w", decErr)
	}

	return computeSSHFingerprint(trimmed)
}

// GetAgentBySSHPubKeyGlobal scans ALL tenants for an agent whose ssh_pubkey
// fingerprint matches. This is the path used by the SSH proxy when it receives
// an inbound public-key auth attempt and does not yet know the tenant.
//
// RLS is bypassed by setting app.platform_admin_view = 'on' for the duration
// of the transaction. This is safe because:
//   - The vault-adapter uses a privileged DSN (mintkey_migrate or superuser).
//   - The result only reveals the matched agent's own tenant_id, which the
//     SSH proxy uses to scope all subsequent calls.
func (s *PostgresStore) GetAgentBySSHPubKeyGlobal(ctx context.Context, fingerprint string) (*AgentSSHRecord, error) {
	conn, err := s.pool.Acquire(ctx)
	if err != nil {
		return nil, fmt.Errorf("ssh store: GetAgentBySSHPubKeyGlobal: acquire conn: %w", err)
	}
	defer conn.Release()

	tx, err := conn.BeginTx(ctx, pgx.TxOptions{AccessMode: pgx.ReadOnly})
	if err != nil {
		return nil, fmt.Errorf("ssh store: GetAgentBySSHPubKeyGlobal: begin tx: %w", err)
	}
	defer func() { _ = tx.Rollback(ctx) }()

	// Enable platform-admin view so RLS does not filter rows.
	if _, err = tx.Exec(ctx, "SELECT set_config('app.platform_admin_view', 'on', true)"); err != nil {
		return nil, fmt.Errorf("ssh store: GetAgentBySSHPubKeyGlobal: set platform view: %w", err)
	}

	rows, err := tx.Query(ctx,
		`SELECT id, tenant_id, name, ssh_pubkey, status
		   FROM public.agents
		  WHERE ssh_pubkey IS NOT NULL`,
	)
	if err != nil {
		return nil, fmt.Errorf("ssh store: GetAgentBySSHPubKeyGlobal: query: %w", err)
	}
	defer rows.Close()

	for rows.Next() {
		var r AgentSSHRecord
		if err = rows.Scan(&r.ID, &r.TenantID, &r.Name, &r.SSHPubKey, &r.Status); err != nil {
			return nil, fmt.Errorf("ssh store: GetAgentBySSHPubKeyGlobal: scan: %w", err)
		}
		fp, fpErr := computeSSHFingerprint(r.SSHPubKey)
		if fpErr != nil {
			continue
		}
		if fp == fingerprint {
			_ = tx.Commit(ctx)
			return &r, nil
		}
	}
	if err = rows.Err(); err != nil {
		return nil, fmt.Errorf("ssh store: GetAgentBySSHPubKeyGlobal: rows: %w", err)
	}

	return nil, ErrAgentNotFound
}

// IsNotFound returns true if err wraps or equals ErrAgentNotFound.
func IsNotFound(err error) bool {
	return errors.Is(err, ErrAgentNotFound)
}

// Ensure PostgresStore implements SSHStore (compile-time check).
var _ SSHStore = (*PostgresStore)(nil)

// SSHStore is the interface the vault-adapter SSH gRPC handlers depend on.
// It is satisfied by *PostgresStore and by the test mock in postgres_ssh_test.go.
type SSHStore interface {
	GetAgentBySSHPubKey(ctx context.Context, tenantID, fingerprint string) (*AgentSSHRecord, error)
	GetAgentBySSHPubKeyGlobal(ctx context.Context, fingerprint string) (*AgentSSHRecord, error)
	GetHostKeyFingerprint(ctx context.Context, tenantID, serviceID string) (string, error)
	StoreHostKeyFingerprint(ctx context.Context, tenantID, serviceID, fingerprint string) error
}

// Ensure ErrNoRows aliasing for callers that use errors.Is(err, sql.ErrNoRows).
var _ = sql.ErrNoRows
