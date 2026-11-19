// Package server provides the gRPC server and vault business logic for the
// Vault Adapter.
//
// VaultService implements credential storage (PutCredential, GetCredential,
// RevokeCredential, ListVersions) using AES-256-GCM envelope encryption via
// the crypto package and SQLite persistence via the store package.
//
// ValidateServiceIdentity verifies per-service boot secrets using HMAC-SHA-256
// under a per-process key.  Service identities and their token MACs are
// bootstrapped into an in-memory map; there is no persistent identity store
// in Phase 1.
//
// Source: T-1.3.1 session 2; vault.proto; ADR-0003; ADR-0014.2.
package server

import (
	"context"
	"crypto/hmac"
	"crypto/rand"
	"crypto/sha256"
	"database/sql"
	"encoding/base32"
	"errors"
	"fmt"
	"slices"
	"strings"
	"sync"
	"time"

	"github.com/mintkey/mintkey/services/vault-adapter/internal/cache"
	"github.com/mintkey/mintkey/services/vault-adapter/internal/crypto"
	"github.com/mintkey/mintkey/services/vault-adapter/internal/store"
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
	TargetURL     string
	HeaderName    string // injection hint for api_key_header scheme — UX-C6
	QueryParam    string // injection hint for api_key_query scheme — UX-C6
	TargetAddress string // SSH-only: "host:port" of the backend SSH server — ADR-0021
	SSHUser       string // SSH-only: SSH username to authenticate as — ADR-0021
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
	AuthScheme            int32
	Plaintext             []byte
	ReturnedKeyVersion    uint32
	CurrentKeyVersion     uint32
	TargetURL             string
	HeaderName            string // injection hint for api_key_header scheme — UX-C6
	QueryParam            string // injection hint for api_key_query scheme — UX-C6
	TargetAddress         string // SSH-only: "host:port" of the backend SSH server — ADR-0021
	SSHUser               string // SSH-only: SSH username to authenticate as — ADR-0021
	BaseUrl               string // Canonical upstream address from services.base_url — ADR-0023 Phase 3
	TlsInsecureSkipVerify bool   // email-only: skip TLS cert verification — ADR-0024
	// Email-only: per-service SMTP/IMAP routing metadata — ADR-0024 (Phase 2).
	SMTPHost string
	SMTPPort int32
	IMAPHost string
	IMAPPort int32
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
	TenantID        string
	ServiceID       string
	AfterKeyVersion uint32
	Limit           uint32
	CallerActorID   string
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
	Versions            []VersionDescriptor
	NextAfterKeyVersion uint32
	CurrentKeyVersion   uint32
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

// serviceIdentity holds the HMAC-SHA-256 MAC + scopes for one service.
type serviceIdentity struct {
	tokenMAC []byte   // HMAC-SHA-256(VaultService.identityKey, token)
	scopes   []string // a copy of the registered scopes
}

// -----------------------------------------------------------------------
// VaultService
// -----------------------------------------------------------------------

// VaultService implements credential storage and service-identity validation.
type VaultService struct {
	kek         []byte
	store       store.Backend
	cache       *cache.DEKCache // encrypted-DEK cache (ADR-0014.4)
	identityKey []byte          // 32 random bytes; never logged or returned
	identityMu  sync.RWMutex
	identities  map[string]*serviceIdentity // keyed by service_identity_id
}

// NewVaultService creates a VaultService with the given KEK and store.
// s must implement store.Backend; both *store.Store (SQLite) and
// *store.PostgresStore satisfy it.
// If dekCache is nil, a default 5-minute TTL cache is allocated internally.
// Pass a non-nil cache to share a single DEKCache instance with the
// changes.Subscriber (so both the subscriber invalidations and the metrics
// counters reflect the same cache).
func NewVaultService(kek []byte, s store.Backend, dekCache ...*cache.DEKCache) *VaultService {
	var c *cache.DEKCache
	if len(dekCache) > 0 && dekCache[0] != nil {
		c = dekCache[0]
	} else {
		c = cache.New(5 * time.Minute)
	}
	identityKey := make([]byte, 32)
	if _, err := rand.Read(identityKey); err != nil {
		panic(fmt.Sprintf("vault: NewVaultService: identity key: %v", err))
	}
	return &VaultService{
		kek:         kek,
		store:       s,
		cache:       c,
		identityKey: identityKey,
		identities:  make(map[string]*serviceIdentity),
	}
}

// tokenMAC returns HMAC-SHA-256(v.identityKey, token).
func (v *VaultService) tokenMAC(token []byte) []byte {
	mac := hmac.New(sha256.New, v.identityKey)
	mac.Write(token)
	return mac.Sum(nil)
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
		CredentialID:  newCredentialID(),
		TenantID:      args.TenantID,
		ServiceID:     args.ServiceID,
		AuthScheme:    args.AuthScheme,
		WrappedDEK:    wrappedDEK,
		EncPayload:    encPayload,
		CreatedAt:     now.UnixNano(),
		TargetURL:     args.TargetURL,
		HeaderName:    args.HeaderName,
		QueryParam:    args.QueryParam,
		TargetAddress: args.TargetAddress,
		SSHUser:       args.SSHUser,
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
				AuthScheme:            e.AuthScheme,
				Plaintext:             plaintext,
				ReturnedKeyVersion:    args.KeyVersion,
				CurrentKeyVersion:     currentKeyVer,
				TargetURL:             e.TargetURL,
				HeaderName:            e.HeaderName,
				QueryParam:            e.QueryParam,
				TargetAddress:         e.TargetAddress,
				SSHUser:               e.SSHUser,
				BaseUrl:               e.ServiceBaseUrl,
				TlsInsecureSkipVerify: e.TlsInsecureSkipVerify,
				SMTPHost:              e.SMTPHost,
				SMTPPort:              e.SMTPPort,
				IMAPHost:              e.IMAPHost,
				IMAPPort:              e.IMAPPort,
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
	v.cache.Put(args.TenantID, args.ServiceID, rec.KeyVersion, rec.WrappedDEK, rec.EncPayload, rec.AuthScheme, rec.IsRevoked, rec.TargetURL, rec.HeaderName, rec.QueryParam, rec.TargetAddress, rec.SSHUser, rec.ServiceBaseUrl, rec.TlsInsecureSkipVerify, rec.SMTPHost, rec.SMTPPort, rec.IMAPHost, rec.IMAPPort)

	// Determine current key version if caller asked for a specific version.
	currentKeyVer := rec.KeyVersion
	if args.KeyVersion != 0 {
		curr, err := v.store.Get(ctx, args.TenantID, args.ServiceID, 0)
		if err == nil {
			currentKeyVer = curr.KeyVersion
		}
	}

	return &GetCredentialResult{
		AuthScheme:            rec.AuthScheme,
		Plaintext:             plaintext,
		ReturnedKeyVersion:    rec.KeyVersion,
		CurrentKeyVersion:     currentKeyVer,
		TargetURL:             rec.TargetURL,
		HeaderName:            rec.HeaderName,
		QueryParam:            rec.QueryParam,
		TargetAddress:         rec.TargetAddress,
		SSHUser:               rec.SSHUser,
		BaseUrl:               rec.ServiceBaseUrl,
		TlsInsecureSkipVerify: rec.TlsInsecureSkipVerify,
		SMTPHost:              rec.SMTPHost,
		SMTPPort:              rec.SMTPPort,
		IMAPHost:              rec.IMAPHost,
		IMAPPort:              rec.IMAPPort,
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

// RegisterServiceIdentity stores an HMAC-SHA-256 MAC of token under
// identityID.  Call this during bootstrap before accepting requests.
func (v *VaultService) RegisterServiceIdentity(identityID string, token []byte, scopes []string) error {
	if identityID == "" {
		return fmt.Errorf("RegisterServiceIdentity: empty identity id")
	}
	if len(token) == 0 {
		return fmt.Errorf("RegisterServiceIdentity(%s): empty token", identityID)
	}

	v.identityMu.Lock()
	defer v.identityMu.Unlock()
	v.identities[identityID] = &serviceIdentity{
		tokenMAC: v.tokenMAC(token),
		scopes:   slices.Clone(scopes),
	}
	return nil
}

// ValidateServiceIdentity verifies a service boot secret using an
// HMAC-SHA-256 constant-time comparison.  Returns the granted scopes and
// ok=true on success; empty scopes and ok=false on any failure.
func (v *VaultService) ValidateServiceIdentity(ctx context.Context, identityID string, token []byte) (scopes []string, ok bool) {
	candidate := v.tokenMAC(token)

	v.identityMu.RLock()
	identity, found := v.identities[identityID]
	v.identityMu.RUnlock()

	if !found {
		// Compare against an all-zero MAC so both paths do the same work and
		// do not leak identity existence by timing.
		_ = hmac.Equal(candidate, make([]byte, sha256.Size))
		return nil, false
	}

	if !hmac.Equal(candidate, identity.tokenMAC) {
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
