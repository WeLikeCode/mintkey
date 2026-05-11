// Package server provides the gRPC server and vault business logic for the
// Vault Adapter.
//
// VaultService implements credential storage (PutCredential, GetCredential,
// RevokeCredential, ListVersions) using AES-256-GCM envelope encryption via
// the crypto package and SQLite persistence via the store package.
//
// ValidateServiceIdentity verifies per-service boot secrets using Argon2id
// (ADR-0014.2).  Service identities and their pre-hashed tokens are
// bootstrapped into an in-memory map; there is no persistent identity store
// in Phase 1.
//
// Source: T-1.3.1 session 2; vault.proto; ADR-0003; ADR-0014.2.
package server

import (
	"context"
	"crypto/rand"
	"crypto/subtle"
	"database/sql"
	"encoding/base32"
	"errors"
	"fmt"
	"strings"
	"sync"
	"time"

	"github.com/mintkey/mintkey/services/vault-adapter/internal/cache"
	"github.com/mintkey/mintkey/services/vault-adapter/internal/crypto"
	"github.com/mintkey/mintkey/services/vault-adapter/internal/store"
	"golang.org/x/crypto/argon2"
)

// -----------------------------------------------------------------------
// Request / response types
// -----------------------------------------------------------------------

// PutCredentialArgs holds the input for PutCredential.
type PutCredentialArgs struct {
	TenantID      string
	ServiceID     string
	AuthScheme    int32
	Plaintext     []byte
	CallerActorID string
}

// PutCredentialResult is returned by PutCredential.
type PutCredentialResult struct {
	KeyVersion uint32
	CreatedAt  time.Time
}

// GetCredentialArgs holds the input for GetCredential.
type GetCredentialArgs struct {
	TenantID      string
	ServiceID     string
	KeyVersion    uint32 // 0 = current
	CallerActorID string
}

// GetCredentialResult is returned by GetCredential.
type GetCredentialResult struct {
	AuthScheme         int32
	Plaintext          []byte
	ReturnedKeyVersion uint32
	CurrentKeyVersion  uint32
}

// RevokeCredentialArgs holds the input for RevokeCredential.
type RevokeCredentialArgs struct {
	TenantID      string
	ServiceID     string
	KeyVersion    uint32
	Reason        string
	CallerActorID string
}

// ListVersionsArgs holds the input for ListVersions.
type ListVersionsArgs struct {
	TenantID         string
	ServiceID        string
	AfterKeyVersion  uint32
	Limit            uint32
	CallerActorID    string
}

// VersionDescriptor is a metadata-only view of one credential version.
// Plaintext is never included.
type VersionDescriptor struct {
	CredentialID string
	KeyVersion   uint32
	IsCurrent    bool
	IsRevoked    bool
	AuthScheme   int32
	CreatedAt    time.Time
}

// ListVersionsResult is returned by ListVersions.
type ListVersionsResult struct {
	Versions             []VersionDescriptor
	NextAfterKeyVersion  uint32
	CurrentKeyVersion    uint32
}

// RotateCredentialArgs is input for RotateCredential.
type RotateCredentialArgs struct {
	TenantID      string
	ServiceID     string
	AuthScheme    int32
	Plaintext     []byte
	CallerActorID string
}

// RotateCredential stores a new credential version (key_version + 1) while
// keeping old versions readable. Delegates to PutCredential since the
// store's Put already handles atomic version increment: it marks all previous
// versions is_current=0 and inserts the new version as is_current=1 within
// a single transaction, so there is no window where neither version is current.
// Returns the new PutCredentialResult with the incremented key_version.
func (v *VaultService) RotateCredential(ctx context.Context, args RotateCredentialArgs) (*PutCredentialResult, error) {
	return v.PutCredential(ctx, PutCredentialArgs{
		TenantID:      args.TenantID,
		ServiceID:     args.ServiceID,
		AuthScheme:    args.AuthScheme,
		Plaintext:     args.Plaintext,
		CallerActorID: args.CallerActorID,
	})
}

// -----------------------------------------------------------------------
// Service identity types
// -----------------------------------------------------------------------

// argon2Params holds the Argon2id tuning parameters.  The values follow the
// OWASP minimum recommendation for interactive logins; boot-time validation
// is not latency-critical so this is deliberately conservative.
type argon2Params struct {
	time    uint32
	memory  uint32
	threads uint8
	keyLen  uint32
}

var defaultArgon2Params = argon2Params{
	time:    1,
	memory:  64 * 1024, // 64 MiB
	threads: 4,
	keyLen:  32,
}

// serviceIdentity holds the Argon2id hash + scopes for one service.
type serviceIdentity struct {
	tokenHash []byte   // Argon2id(token, salt, params)
	salt      []byte   // stored alongside hash
	scopes    []string
}

// -----------------------------------------------------------------------
// VaultService
// -----------------------------------------------------------------------

// VaultService implements credential storage and service-identity validation.
type VaultService struct {
	kek        []byte
	store      *store.Store
	cache      *cache.DEKCache // encrypted-DEK cache (ADR-0014.4)
	identityMu sync.RWMutex
	identities map[string]*serviceIdentity // keyed by service_identity_id
}

// NewVaultService creates a VaultService with the given KEK and store.
func NewVaultService(kek []byte, s *store.Store) *VaultService {
	return &VaultService{
		kek:        kek,
		store:      s,
		cache:      cache.New(5 * time.Minute),
		identities: make(map[string]*serviceIdentity),
	}
}

// -----------------------------------------------------------------------
// Credential operations
// -----------------------------------------------------------------------

// PutCredential seals plaintext with a fresh DEK and stores it.
// Returns the newly assigned key_version and the server-side creation time.
func (v *VaultService) PutCredential(ctx context.Context, args PutCredentialArgs) (*PutCredentialResult, error) {
	if args.TenantID == "" || args.ServiceID == "" {
		return nil, fmt.Errorf("PutCredential: tenant_id and service_id are required")
	}
	if len(args.Plaintext) == 0 {
		return nil, fmt.Errorf("PutCredential: plaintext must not be empty")
	}
	if len(args.Plaintext) > 64*1024 {
		return nil, fmt.Errorf("PutCredential: plaintext exceeds 64 KiB limit")
	}

	wrappedDEK, encPayload, err := crypto.Seal(v.kek, args.Plaintext)
	if err != nil {
		return nil, fmt.Errorf("PutCredential: seal: %w", err)
	}

	now := time.Now().UTC()
	rec := store.CredentialRecord{
		CredentialID: newCredentialID(),
		TenantID:     args.TenantID,
		ServiceID:    args.ServiceID,
		AuthScheme:   args.AuthScheme,
		WrappedDEK:   wrappedDEK,
		EncPayload:   encPayload,
		CreatedAt:    now.UnixNano(),
	}

	keyVer, err := v.store.Put(ctx, rec)
	if err != nil {
		return nil, fmt.Errorf("PutCredential: store: %w", err)
	}

	return &PutCredentialResult{
		KeyVersion: keyVer,
		CreatedAt:  now,
	}, nil
}

// GetCredential retrieves and decrypts a credential.
// Pass KeyVersion=0 to retrieve the current version.
//
// Cache behaviour (ADR-0014.4): for specific (non-zero) key_versions, the
// encrypted (wrappedDEK, encPayload) pair is cached by
// (tenant_id, service_id, key_version).  A cache hit skips the SQLite read.
// key_version=0 ("current") always reads SQLite so that rotation is reflected
// immediately; the resolved version is then cached under its concrete version
// number.
func (v *VaultService) GetCredential(ctx context.Context, args GetCredentialArgs) (*GetCredentialResult, error) {
	if args.TenantID == "" || args.ServiceID == "" {
		return nil, fmt.Errorf("GetCredential: tenant_id and service_id are required")
	}

	// For specific key versions, check the cache before hitting SQLite.
	if args.KeyVersion != 0 {
		if e, ok := v.cache.Get(args.TenantID, args.ServiceID, args.KeyVersion); ok {
			if e.IsRevoked {
				return nil, fmt.Errorf("GetCredential: credential is revoked")
			}
			plaintext, err := crypto.Open(v.kek, e.WrappedDEK, e.EncPayload)
			if err != nil {
				return nil, fmt.Errorf("GetCredential: open (cache): %w", err)
			}
			// Determine the current version for the response metadata.
			currentKeyVer := args.KeyVersion
			curr, err := v.store.Get(ctx, args.TenantID, args.ServiceID, 0)
			if err == nil {
				currentKeyVer = curr.KeyVersion
			}
			return &GetCredentialResult{
				AuthScheme:         e.AuthScheme,
				Plaintext:          plaintext,
				ReturnedKeyVersion: args.KeyVersion,
				CurrentKeyVersion:  currentKeyVer,
			}, nil
		}
	}

	rec, err := v.store.Get(ctx, args.TenantID, args.ServiceID, args.KeyVersion)
	if err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			return nil, fmt.Errorf("GetCredential: not found")
		}
		return nil, fmt.Errorf("GetCredential: store: %w", err)
	}

	if rec.IsRevoked {
		return nil, fmt.Errorf("GetCredential: credential is revoked")
	}

	plaintext, err := crypto.Open(v.kek, rec.WrappedDEK, rec.EncPayload)
	if err != nil {
		return nil, fmt.Errorf("GetCredential: open: %w", err)
	}

	// Populate the cache for the concrete key version (encrypted blobs only).
	v.cache.Put(args.TenantID, args.ServiceID, rec.KeyVersion, rec.WrappedDEK, rec.EncPayload, rec.AuthScheme, rec.IsRevoked)

	// Determine current key version if caller asked for a specific version.
	currentKeyVer := rec.KeyVersion
	if args.KeyVersion != 0 {
		curr, err := v.store.Get(ctx, args.TenantID, args.ServiceID, 0)
		if err == nil {
			currentKeyVer = curr.KeyVersion
		}
	}

	return &GetCredentialResult{
		AuthScheme:         rec.AuthScheme,
		Plaintext:          plaintext,
		ReturnedKeyVersion: rec.KeyVersion,
		CurrentKeyVersion:  currentKeyVer,
	}, nil
}

// RevokeCredential soft-deletes a non-current credential version.
// Returns an error if the version is current (caller must rotate first).
func (v *VaultService) RevokeCredential(ctx context.Context, args RevokeCredentialArgs) error {
	if args.TenantID == "" || args.ServiceID == "" {
		return fmt.Errorf("RevokeCredential: tenant_id and service_id are required")
	}
	if args.KeyVersion == 0 {
		return fmt.Errorf("RevokeCredential: key_version must be non-zero")
	}

	err := v.store.Revoke(ctx, args.TenantID, args.ServiceID, args.KeyVersion)
	if errors.Is(err, store.ErrRevokeCurrent) {
		return fmt.Errorf("RevokeCredential: %w", store.ErrRevokeCurrent)
	}
	if err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			return fmt.Errorf("RevokeCredential: version %d not found", args.KeyVersion)
		}
		return fmt.Errorf("RevokeCredential: %w", err)
	}
	return nil
}

// ListVersions returns metadata-only descriptors for all versions of
// (TenantID, ServiceID).  Plaintext is never included.
func (v *VaultService) ListVersions(ctx context.Context, args ListVersionsArgs) (*ListVersionsResult, error) {
	if args.TenantID == "" || args.ServiceID == "" {
		return nil, fmt.Errorf("ListVersions: tenant_id and service_id are required")
	}

	limit := args.Limit
	if limit == 0 || limit > 200 {
		limit = 50
	}

	recs, err := v.store.ListVersions(ctx, args.TenantID, args.ServiceID, args.AfterKeyVersion, limit)
	if err != nil {
		return nil, fmt.Errorf("ListVersions: store: %w", err)
	}

	descs := make([]VersionDescriptor, 0, len(recs))
	var maxVer uint32
	var currentVer uint32
	for _, r := range recs {
		descs = append(descs, VersionDescriptor{
			CredentialID: r.CredentialID,
			KeyVersion:   r.KeyVersion,
			IsCurrent:    r.IsCurrent,
			IsRevoked:    r.IsRevoked,
			AuthScheme:   r.AuthScheme,
			CreatedAt:    time.Unix(0, r.CreatedAt).UTC(),
		})
		if r.KeyVersion > maxVer {
			maxVer = r.KeyVersion
		}
		if r.IsCurrent {
			currentVer = r.KeyVersion
		}
	}

	var nextCursor uint32
	if uint32(len(recs)) == limit {
		nextCursor = maxVer
	}

	return &ListVersionsResult{
		Versions:            descs,
		NextAfterKeyVersion: nextCursor,
		CurrentKeyVersion:   currentVer,
	}, nil
}

// -----------------------------------------------------------------------
// Service identity validation
// -----------------------------------------------------------------------

// RegisterServiceIdentity hashes token with Argon2id and stores the result
// under identityID.  Call this during bootstrap before accepting requests.
func (v *VaultService) RegisterServiceIdentity(identityID string, token []byte, scopes []string) error {
	salt := make([]byte, 16)
	if _, err := rand.Read(salt); err != nil {
		return fmt.Errorf("RegisterServiceIdentity: generate salt: %w", err)
	}
	p := defaultArgon2Params
	hash := argon2.IDKey(token, salt, p.time, p.memory, p.threads, p.keyLen)

	v.identityMu.Lock()
	defer v.identityMu.Unlock()
	v.identities[identityID] = &serviceIdentity{
		tokenHash: hash,
		salt:      salt,
		scopes:    scopes,
	}
	return nil
}

// ValidateServiceIdentity verifies a service boot secret using Argon2id
// constant-time comparison.  Returns the granted scopes and ok=true on
// success; empty scopes and ok=false on any failure.
func (v *VaultService) ValidateServiceIdentity(ctx context.Context, identityID string, token []byte) (scopes []string, ok bool) {
	v.identityMu.RLock()
	identity, found := v.identities[identityID]
	v.identityMu.RUnlock()

	if !found {
		// Still perform a dummy hash to avoid timing-based identity enumeration.
		dummySalt := make([]byte, 16)
		p := defaultArgon2Params
		argon2.IDKey(token, dummySalt, p.time, p.memory, p.threads, p.keyLen)
		return nil, false
	}

	p := defaultArgon2Params
	candidate := argon2.IDKey(token, identity.salt, p.time, p.memory, p.threads, p.keyLen)
	if subtle.ConstantTimeCompare(candidate, identity.tokenHash) != 1 {
		return nil, false
	}
	return identity.scopes, true
}

// -----------------------------------------------------------------------
// Helpers
// -----------------------------------------------------------------------

// newCredentialID generates a cred_<26-char ULID-alphabet random> ID.
// A lightweight approximation: random 16 bytes encoded in Crockford base32
// (no time component; uniqueness guaranteed by random entropy).
func newCredentialID() string {
	b := make([]byte, 16)
	if _, err := rand.Read(b); err != nil {
		panic(fmt.Sprintf("vault: newCredentialID: %v", err))
	}
	enc := base32.NewEncoding("0123456789ABCDEFGHJKMNPQRSTVWXYZ").WithPadding(base32.NoPadding)
	return "cred_" + strings.ToUpper(enc.EncodeToString(b))
}
