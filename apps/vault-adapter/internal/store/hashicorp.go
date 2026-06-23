// hashicorp.go — HashiCorp Vault KV v2 backend implementing the store.Backend
// interface. Credentials are stored as envelope-encrypted blobs (wrapped_dek +
// enc_payload) in a per-(tenant, service) KV v2 namespace; a small _index doc
// tracks the current and max versions so that full mount scans are avoided.
//
// Source: design §3, §4, §5; ADR-0025.
package store

import (
	"context"
	"database/sql"
	"errors"
	"fmt"
	"log/slog"
	"os"
	"sort"
	"sync"
	"time"

	vaultapi "github.com/hashicorp/vault/api"
)

// Compile-time assertion: *HashiCorpStore must implement Backend.
var _ Backend = (*HashiCorpStore)(nil)

// HashiCorpConfig holds the configuration needed to connect to a HashiCorp
// Vault instance and authenticate via AppRole.
type HashiCorpConfig struct {
	Addr      string // e.g. "http://hashicorp-vault:8201"
	Namespace string // optional, Vault Enterprise
	CACert    string // optional path to CA cert for TLS
	Mount     string // KV v2 mount, e.g. "secret"
	Prefix    string // path prefix, e.g. "mintkey"
	RoleID    string
	SecretID  string
	// Logger overrides slog.Default() when set. Used in tests to capture log output.
	Logger *slog.Logger
}

// HashiCorpStore is a Backend backed by HashiCorp Vault KV v2.
type HashiCorpStore struct {
	client *vaultapi.Client
	kv     *vaultapi.KVv2
	mount  string
	prefix string
	auth   *appRoleAuth
	mu     *keyedMutex
	log    *slog.Logger
}

// keyedMutex provides per-key mutual exclusion backed by a sync.Map of
// *sync.Mutex values. Used to serialise concurrent Put calls for the same
// (tenant, service) pair (design §4 FR-9).
type keyedMutex struct {
	m sync.Map // key string -> *sync.Mutex
}

func newKeyedMutex() *keyedMutex { return &keyedMutex{} }

func (km *keyedMutex) lock(key string) {
	mu, _ := km.m.LoadOrStore(key, &sync.Mutex{})
	mu.(*sync.Mutex).Lock()
}

func (km *keyedMutex) unlock(key string) {
	if v, ok := km.m.Load(key); ok {
		v.(*sync.Mutex).Unlock()
	}
}

// NewHashiCorp constructs a HashiCorpStore, performs the AppRole login, and
// starts the background token renewal goroutine.
func NewHashiCorp(ctx context.Context, cfg HashiCorpConfig) (*HashiCorpStore, error) {
	vcfg := vaultapi.DefaultConfig()
	vcfg.Address = cfg.Addr

	if cfg.CACert != "" {
		tlsCfg := &vaultapi.TLSConfig{CACert: cfg.CACert}
		if err := vcfg.ConfigureTLS(tlsCfg); err != nil {
			return nil, fmt.Errorf("vault hashicorp: TLS config: %w", err)
		}
	}

	client, err := vaultapi.NewClient(vcfg)
	if err != nil {
		return nil, fmt.Errorf("vault hashicorp: new client: %w", err)
	}

	if cfg.Namespace != "" {
		client.SetNamespace(cfg.Namespace)
	}

	log := cfg.Logger
	if log == nil {
		log = slog.Default()
	}
	auth, err := newAppRoleAuth(ctx, client, cfg.RoleID, cfg.SecretID, log)
	if err != nil {
		return nil, fmt.Errorf("vault hashicorp: approle login: %w", err)
	}

	return &HashiCorpStore{
		client: client,
		kv:     client.KVv2(cfg.Mount),
		mount:  cfg.Mount,
		prefix: cfg.Prefix,
		auth:   auth,
		mu:     newKeyedMutex(),
		log:    log,
	}, nil
}

// Put inserts a new credential version.
//
// Atomicity is enforced by the in-process per-(tenant,service) mutex (primary)
// and a KV v2 CAS write on the index doc (secondary).
//
// Steps:
//  1. Lock the keyed mutex for this (tenant, service).
//  2. Read _index (or start fresh).
//  3. Compute next = Max + 1.
//  4. Flip the old current version's is_current to false.
//  5. Write v<next> as is_current=true.
//  6. Write _index with updated Current/Max/Versions.
//  7. Unlock.
func (s *HashiCorpStore) Put(ctx context.Context, rec CredentialRecord) (uint32, error) {
	key := rec.TenantID + "/" + rec.ServiceID
	s.mu.lock(key)
	defer s.mu.unlock(key)

	// Read existing index, or start fresh.
	idx, cas, err := s.readIndex(ctx, rec.TenantID, rec.ServiceID)
	if err != nil {
		return 0, fmt.Errorf("vault hashicorp: Put: read index: %w", err)
	}

	next := idx.Max + 1

	// Demote the previous current version (if any).
	if idx.Current > 0 {
		prev, err := s.readVersion(ctx, rec.TenantID, rec.ServiceID, idx.Current)
		if err != nil && !isNotFound(err) {
			return 0, fmt.Errorf("vault hashicorp: Put: read prev current: %w", err)
		}
		if prev != nil {
			prev.IsCurrent = false
			m, err := marshalVersionDoc(*prev)
			if err != nil {
				return 0, fmt.Errorf("vault hashicorp: Put: marshal prev: %w", err)
			}
			dp := dataPath(s.prefix, rec.TenantID, rec.ServiceID, idx.Current)
			if _, err = s.kv.Put(ctx, dp, m); err != nil {
				return 0, fmt.Errorf("vault hashicorp: Put: write prev: %w", err)
			}
		}
	}

	// Set timestamps.
	if rec.CreatedAt == 0 {
		rec.CreatedAt = time.Now().UnixNano()
	}
	rec.KeyVersion = next
	rec.IsCurrent = true
	rec.IsRevoked = false

	// Write the new version doc.
	m, err := marshalVersionDoc(rec)
	if err != nil {
		return 0, fmt.Errorf("vault hashicorp: Put: marshal: %w", err)
	}
	dp := dataPath(s.prefix, rec.TenantID, rec.ServiceID, next)
	if _, err = s.kv.Put(ctx, dp, m); err != nil {
		return 0, fmt.Errorf("vault hashicorp: Put: write version: %w", err)
	}

	// Update and write the index.
	idx.Current = next
	idx.Max = next
	idx.Versions = append(idx.Versions, next)

	im := marshalIndex(idx)
	ip := indexPath(s.prefix, rec.TenantID, rec.ServiceID)
	if _, err = s.kv.Put(ctx, ip, im, vaultapi.WithCheckAndSet(cas)); err != nil {
		return 0, fmt.Errorf("vault hashicorp: Put: write index: %w", err)
	}

	return next, nil
}

// Get retrieves a credential record by version.
// Pass keyVersion=0 to get the current version.
// Returns (nil, wrapped sql.ErrNoRows) when not found.
func (s *HashiCorpStore) Get(ctx context.Context, tenantID, serviceID string, keyVersion uint32) (*CredentialRecord, error) {
	if keyVersion == 0 {
		// Read the index to find the current version number.
		idx, _, err := s.readIndex(ctx, tenantID, serviceID)
		if err != nil {
			return nil, fmt.Errorf("vault hashicorp: Get: read index: %w", err)
		}
		if idx.Current == 0 {
			return nil, fmt.Errorf("vault hashicorp: Get: %w", sql.ErrNoRows)
		}
		keyVersion = idx.Current
	}

	rec, err := s.readVersion(ctx, tenantID, serviceID, keyVersion)
	if err != nil {
		if isNotFound(err) {
			return nil, fmt.Errorf("vault hashicorp: Get: %w", sql.ErrNoRows)
		}
		return nil, fmt.Errorf("vault hashicorp: Get: %w", err)
	}
	if rec == nil {
		return nil, fmt.Errorf("vault hashicorp: Get: %w", sql.ErrNoRows)
	}
	return rec, nil
}

// Revoke soft-deletes a non-current credential version (is_revoked=true).
// Returns ErrRevokeCurrent when the target is the active version.
// Returns a wrapped sql.ErrNoRows when keyVersion does not exist.
func (s *HashiCorpStore) Revoke(ctx context.Context, tenantID, serviceID string, keyVersion uint32) error {
	rec, err := s.readVersion(ctx, tenantID, serviceID, keyVersion)
	if err != nil {
		if isNotFound(err) {
			return fmt.Errorf("vault hashicorp: Revoke: version %d not found: %w", keyVersion, sql.ErrNoRows)
		}
		return fmt.Errorf("vault hashicorp: Revoke: read: %w", err)
	}
	if rec == nil {
		return fmt.Errorf("vault hashicorp: Revoke: version %d not found: %w", keyVersion, sql.ErrNoRows)
	}

	if rec.IsCurrent {
		return ErrRevokeCurrent
	}

	rec.IsRevoked = true
	m, err := marshalVersionDoc(*rec)
	if err != nil {
		return fmt.Errorf("vault hashicorp: Revoke: marshal: %w", err)
	}
	dp := dataPath(s.prefix, tenantID, serviceID, keyVersion)
	if _, err = s.kv.Put(ctx, dp, m); err != nil {
		return fmt.Errorf("vault hashicorp: Revoke: write: %w", err)
	}
	return nil
}

// ListVersions returns metadata-only records (WrappedDEK and EncPayload are
// nil) for versions > afterKeyVersion, up to clampLimit(limit) results,
// sorted ascending by KeyVersion.
func (s *HashiCorpStore) ListVersions(ctx context.Context, tenantID, serviceID string, afterKeyVersion, limit uint32) ([]CredentialRecord, error) {
	limit = clampLimit(limit)

	idx, _, err := s.readIndex(ctx, tenantID, serviceID)
	if err != nil {
		return nil, fmt.Errorf("vault hashicorp: ListVersions: read index: %w", err)
	}

	// Filter versions > afterKeyVersion.
	var filtered []uint32
	for _, v := range idx.Versions {
		if v > afterKeyVersion {
			filtered = append(filtered, v)
		}
	}
	// Sort ascending.
	sort.Slice(filtered, func(i, j int) bool { return filtered[i] < filtered[j] })
	// Apply limit.
	if uint32(len(filtered)) > limit {
		filtered = filtered[:limit]
	}

	result := make([]CredentialRecord, 0, len(filtered))
	for _, ver := range filtered {
		rec, err := s.readVersion(ctx, tenantID, serviceID, ver)
		if err != nil || rec == nil {
			// Skip missing docs (defensive; shouldn't happen in normal operation).
			continue
		}
		// Strip payload bytes — metadata only, matching sqlite/postgres behaviour.
		rec.WrappedDEK = nil
		rec.EncPayload = nil
		result = append(result, *rec)
	}

	return result, nil
}

// Close stops the background token renewal goroutine.
func (s *HashiCorpStore) Close() error {
	s.auth.stop()
	return nil
}

// ---- internal helpers ----

// readIndex reads the _index doc for (tenantID, serviceID).
// Returns a zero-value versionIndex and CAS 0 when the path does not exist.
// Returns a non-nil error for any other failure (network, 403, timeout, etc.).
// The returned int is the KV v2 metadata version for use as a CAS value on the
// next Put of the index doc (0 = "key must not exist yet").
func (s *HashiCorpStore) readIndex(ctx context.Context, tenantID, serviceID string) (versionIndex, int, error) {
	ip := indexPath(s.prefix, tenantID, serviceID)
	secret, err := s.kv.Get(ctx, ip)
	if err != nil {
		if isNotFound(err) {
			// First Put for this (tenant, service) — fresh start.
			return versionIndex{Versions: []uint32{}}, 0, nil
		}
		return versionIndex{}, 0, fmt.Errorf("vault hashicorp: read index %s: %w", ip, err)
	}
	if secret == nil || secret.Data == nil {
		return versionIndex{Versions: []uint32{}}, 0, nil
	}
	idx, err := unmarshalIndex(secret.Data)
	if err != nil {
		return versionIndex{}, 0, err
	}
	// Extract the KV v2 metadata version for CAS on the next index write.
	cas := 0
	if secret.VersionMetadata != nil {
		cas = secret.VersionMetadata.Version
	}
	return idx, cas, nil
}

// readVersion reads a single version doc for (tenantID, serviceID, ver).
// Returns (nil, nil) when the doc is absent (not-found is not an error here).
func (s *HashiCorpStore) readVersion(ctx context.Context, tenantID, serviceID string, ver uint32) (*CredentialRecord, error) {
	dp := dataPath(s.prefix, tenantID, serviceID, ver)
	secret, err := s.kv.Get(ctx, dp)
	if err != nil {
		return nil, err
	}
	if secret == nil || secret.Data == nil {
		return nil, nil
	}
	rec, err := unmarshalVersionDoc(secret.Data)
	if err != nil {
		return nil, err
	}
	return &rec, nil
}

// isNotFound returns true when the HashiCorp Vault SDK signals that a KV path
// does not exist. The KVv2.Get wrapper wraps ErrSecretNotFound via %w when
// the HTTP response body is nil (path absent).
func isNotFound(err error) bool {
	return err != nil && errors.Is(err, vaultapi.ErrSecretNotFound)
}

// hashiCorpConfigFromEnv builds a HashiCorpConfig from environment variables.
// All required variables produce descriptive errors when absent.
func hashiCorpConfigFromEnv() (HashiCorpConfig, error) {
	addr := os.Getenv("MINTKEY_VAULT_HASHICORP_ADDR")
	if addr == "" {
		return HashiCorpConfig{}, fmt.Errorf("MINTKEY_VAULT_BACKEND=hashicorp requires MINTKEY_VAULT_HASHICORP_ADDR")
	}
	roleID := os.Getenv("MINTKEY_VAULT_HASHICORP_ROLE_ID")
	if roleID == "" {
		return HashiCorpConfig{}, fmt.Errorf("MINTKEY_VAULT_BACKEND=hashicorp requires MINTKEY_VAULT_HASHICORP_ROLE_ID")
	}
	secretID := os.Getenv("MINTKEY_VAULT_HASHICORP_SECRET_ID")
	if secretID == "" {
		return HashiCorpConfig{}, fmt.Errorf("MINTKEY_VAULT_BACKEND=hashicorp requires MINTKEY_VAULT_HASHICORP_SECRET_ID")
	}
	mount := os.Getenv("MINTKEY_VAULT_HASHICORP_MOUNT")
	if mount == "" {
		mount = "secret"
	}
	prefix := os.Getenv("MINTKEY_VAULT_HASHICORP_PREFIX")
	if prefix == "" {
		prefix = "mintkey"
	}
	return HashiCorpConfig{
		Addr:      addr,
		Namespace: os.Getenv("MINTKEY_VAULT_HASHICORP_NAMESPACE"),
		CACert:    os.Getenv("MINTKEY_VAULT_HASHICORP_CACERT"),
		Mount:     mount,
		Prefix:    prefix,
		RoleID:    roleID,
		SecretID:  secretID,
	}, nil
}
