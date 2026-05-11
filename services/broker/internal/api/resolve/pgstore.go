// pgstore.go — production Store backed by a pgx connection pool.
//
// Uses bound parameters only (ADR-0008; T-1.0.15 SQL injection rule).
// Sets app.current_tenant via set_config before every query so RLS fires.
package resolve

import (
	"context"
	"fmt"
	"strings"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"
)

// PgStore implements Store against a live PostgreSQL database.
type PgStore struct {
	pool *pgxpool.Pool
}

// NewPgStore constructs a PgStore from an existing pool.
func NewPgStore(pool *pgxpool.Pool) *PgStore {
	return &PgStore{pool: pool}
}

// LookupByFingerprint fetches a key row with RLS applied.
// Bound parameters only — no f-string SQL (T-1.0.15).
func (s *PgStore) LookupByFingerprint(ctx context.Context, tenantID, fingerprint string) (*KeyRow, error) {
	conn, err := s.pool.Acquire(ctx)
	if err != nil {
		return nil, fmt.Errorf("pgstore: acquire: %w", err)
	}
	defer conn.Release()

	// SET app.current_tenant so RLS fires for this transaction.
	if _, err := conn.Exec(ctx,
		"SELECT set_config('app.current_tenant', $1, true)",
		tenantID,
	); err != nil {
		return nil, fmt.Errorf("pgstore: set_config: %w", err)
	}

	const q = `
		SELECT id, agent_id, service_id, key_hash,
		       allowed_actions, constraints, expires_at, revoked_at
		FROM service_api_keys
		WHERE key_fingerprint = $1
		LIMIT 1`

	row := conn.QueryRow(ctx, q, fingerprint)

	var (
		kr          KeyRow
		allowedRaw  []string
		constraintsB []byte
		expiresAt   *time.Time
		revokedAt   *time.Time
	)
	err = row.Scan(&kr.ID, &kr.AgentID, &kr.ServiceID, &kr.KeyHash,
		&allowedRaw, &constraintsB, &expiresAt, &revokedAt)
	if err != nil {
		if strings.Contains(err.Error(), "no rows") {
			return nil, nil
		}
		return nil, fmt.Errorf("pgstore: scan: %w", err)
	}

	kr.AllowedActions = allowedRaw
	kr.ExpiresAt = expiresAt
	kr.RevokedAt = revokedAt
	return &kr, nil
}

// AgentActive returns true iff the agent's status is "active".
func (s *PgStore) AgentActive(ctx context.Context, tenantID, agentID string) (bool, error) {
	conn, err := s.pool.Acquire(ctx)
	if err != nil {
		return false, fmt.Errorf("pgstore: acquire: %w", err)
	}
	defer conn.Release()

	if _, err := conn.Exec(ctx,
		"SELECT set_config('app.current_tenant', $1, true)",
		tenantID,
	); err != nil {
		return false, fmt.Errorf("pgstore: set_config: %w", err)
	}

	const q = `SELECT status FROM agents WHERE id = $1 LIMIT 1`
	var status string
	err = conn.QueryRow(ctx, q, agentID).Scan(&status)
	if err != nil {
		if strings.Contains(err.Error(), "no rows") {
			return false, nil
		}
		return false, fmt.Errorf("pgstore: agent scan: %w", err)
	}
	return status == "active", nil
}
