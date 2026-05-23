// Package audit is the single audit chokepoint for Mintkey.
//
// Every state-change handler MUST call audit.Emit (or audit.EmitWithStore in
// tests). The architecture test in T-1.7.3 asserts no state-change handler
// bypasses this package.
//
// Hash chain: ADR-0014.7 mandates a per-tenant tamper-evident hash chain.
//
//	hash = sha256(canonical_json(event_fields_except_hash) || prev_hash)
//
// Genesis prev_hash = sha256("mintkey-audit-genesis-v1:" || tenant_id),
// inserted by the seed job into audit_chain_state (design §3).
//
// Full pgx/SQL wiring (advisory lock + chain-state read/write) is added in
// T-1.7.x. This package exposes the pure ComputeHash function and the
// injectable EmitWithStore so the hash logic can be unit-tested without a DB.
package audit

import (
	"context"
	"crypto/sha256"
	"encoding/json"
	"errors"
	"time"
)

// Event is the audit record emitted for every state change.
// PrevHash and Hash are computed by Emit / EmitWithStore; callers must not
// set them — they are ignored on input and always overwritten.
type Event struct {
	ID         string         // ULID with "audit_" prefix (internal/ulid.New("audit_"))
	TenantID   string         // tenant ULID
	EventType  string         // e.g. "service.registered", "agent.created"
	ActorID    string         // operator or agent ULID
	ActorType  string         // "operator" | "agent" | "system_seed"
	TargetID   string         // resource ULID
	TargetType string         // "service" | "agent" | "credential" | etc.
	Payload    map[string]any // arbitrary event data; MUST NOT contain plaintext credentials
	At         time.Time      // event timestamp (default: time.Now())
}

// StoreFn is the injectable storage function used by EmitWithStore.
// It receives the event and the prevHash read from audit_chain_state, and
// must:
//  1. Compute hash = ComputeHash(event, prevHash).
//  2. INSERT the event + prevHash + hash into audit_events.
//  3. UPDATE audit_chain_state.head_hash = hash, head_event_id = event.ID.
//  4. Return the hash on success.
//
// The default StoreFn (wired in T-1.7.x) uses pgx inside the caller's
// transaction with a per-tenant Postgres advisory lock.
type StoreFn func(ctx context.Context, event Event, prevHash []byte) (hash []byte, err error)

// ComputeHash computes sha256(canonical_json(event) || prevHash).
//
// "Canonical JSON" here means encoding/json.Marshal on the Event struct,
// which sorts struct fields by declaration order (deterministic for a fixed
// type). Callers must pass the event with PrevHash and Hash zero — this
// function does not read those fields because Event has no hash fields;
// callers must not embed computed values into the input event.
//
// prevHash may be nil for the genesis event (the seed job inserts
// sha256("mintkey-audit-genesis-v1:" || tenant_id) as the genesis state).
func ComputeHash(event Event, prevHash []byte) []byte {
	b, err := json.Marshal(event)
	if err != nil {
		// json.Marshal on a struct with only basic types and map[string]any
		// should never fail in practice; panic to surface the bug immediately.
		panic("audit: json.Marshal failed: " + err.Error())
	}
	input := append(b, prevHash...) //nolint:gocritic // extending b is safe here
	sum := sha256.Sum256(input)
	return sum[:]
}

// EmitWithStore validates the event and delegates persistence to store.
// Tests inject a fake StoreFn; production code uses the pgx StoreFn wired in
// T-1.7.x.
//
// Validation rules (required non-empty fields per design §1 / ADR-0014.7):
//   - TenantID — every audit row is tenant-scoped
//   - EventType — identifies the state change
//   - ActorType — "operator" | "agent" | "system_seed"
func EmitWithStore(ctx context.Context, store StoreFn, event Event) error {
	if store == nil {
		return errors.New("audit: store is required")
	}
	if event.TenantID == "" {
		return errors.New("audit: event.TenantID is required")
	}
	if event.EventType == "" {
		return errors.New("audit: event.EventType is required")
	}
	if event.ActorType == "" {
		return errors.New("audit: event.ActorType is required")
	}
	if event.At.IsZero() {
		event.At = time.Now().UTC()
	}

	// store is responsible for reading prevHash from audit_chain_state,
	// computing the hash via ComputeHash, and persisting both.
	_, err := store(ctx, event, nil)
	return err
}

// Emit is the production entry point. It requires a non-nil transaction.
//
// Full implementation (advisory lock + chain-state read/write via pgx) is
// added in T-1.7.x. This stub rejects nil tx so callers are forced to
// provide a transaction, matching the design §1 contract.
func Emit(ctx context.Context, tx interface{}, event Event) error {
	if tx == nil {
		return errors.New("audit: transaction is required; Emit must be called inside a DB transaction")
	}
	// T-1.7.x wires the real pgx StoreFn here.
	// For now, return a clear "not yet wired" error so integration tests catch
	// any premature call to Emit before T-1.7.x is complete.
	return errors.New("audit: pgx store not yet wired (implement in T-1.7.x)")
}
