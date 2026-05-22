// Package cache provides an in-process encrypted-DEK cache for the Vault Adapter.
//
// The cache stores (wrappedDEK, encPayload) pairs keyed by
// (tenant_id, service_id, key_version) with a configurable TTL (default 5 min,
// max 10 min).  Only the WRAPPED DEK is stored — never the plaintext DEK or
// plaintext credential.  This satisfies ADR-0014.4 (cache lives in the vault
// adapter, not the egress proxy plugin).
//
// Invalidation is triggered on credential.rotated events for a
// (tenant_id, service_id) pair; see InvalidateByService.
//
// Prometheus counters mintkey_vault_dek_cache_hit_total /
// mintkey_vault_dek_cache_miss_total are tracked in-process; the caller is
// responsible for exporting them.
//
// Source: T-1.3.5; ADR-0014.4.
package cache

import (
	"sync"
	"sync/atomic"
	"time"
)

// maxTTL caps the caller-supplied TTL at 10 minutes (per task spec).
const maxTTL = 10 * time.Minute

// cacheKey uniquely identifies one credential version.
type cacheKey struct {
	tenantID   string
	serviceID  string
	keyVersion uint32
}

// cacheEntry holds the encrypted blob pair, associated metadata, and the
// expiry wall-clock time.  Both DEK fields are ENCRYPTED — wrappedDEK is the
// DEK sealed by the KEK; encPayload is the ciphertext produced by
// AES-256-GCM.  Plaintext never enters this struct.
type cacheEntry struct {
	wrappedDEK []byte
	encPayload []byte
	authScheme int32
	isRevoked  bool
	targetURL  string
	headerName string // injection hint — UX-C6
	queryParam string // injection hint — UX-C6
	expiresAt  time.Time
}

// DEKCache caches encrypted DEKs per (tenant_id, service_id, key_version).
// Safe for concurrent use.
type DEKCache struct {
	mu      sync.RWMutex
	entries map[cacheKey]*cacheEntry
	ttl     time.Duration
	hits    atomic.Int64
	misses  atomic.Int64
}

// New creates a DEKCache with the given TTL.  Values above maxTTL (10 min)
// are clamped; values of zero or below are set to 5 minutes.
func New(ttl time.Duration) *DEKCache {
	if ttl <= 0 {
		ttl = 5 * time.Minute
	}
	if ttl > maxTTL {
		ttl = maxTTL
	}
	return &DEKCache{
		entries: make(map[cacheKey]*cacheEntry),
		ttl:     ttl,
	}
}

// Entry is the value returned by a cache hit.
type Entry struct {
	WrappedDEK []byte
	EncPayload []byte
	AuthScheme int32
	IsRevoked  bool
	TargetURL  string
	HeaderName string // injection hint — UX-C6
	QueryParam string // injection hint — UX-C6
}

// Put stores a cache entry for the given key with the configured TTL.
// wrappedDEK and encPayload must be ENCRYPTED blobs — callers must never pass
// plaintext.
func (c *DEKCache) Put(tenantID, serviceID string, keyVersion uint32, wrappedDEK, encPayload []byte, authScheme int32, isRevoked bool, targetURL, headerName, queryParam string) {
	k := cacheKey{tenantID: tenantID, serviceID: serviceID, keyVersion: keyVersion}
	// Copy slices so the caller's buffer changes don't corrupt the cache.
	wCopy := make([]byte, len(wrappedDEK))
	copy(wCopy, wrappedDEK)
	pCopy := make([]byte, len(encPayload))
	copy(pCopy, encPayload)

	c.mu.Lock()
	c.entries[k] = &cacheEntry{
		wrappedDEK: wCopy,
		encPayload: pCopy,
		authScheme: authScheme,
		isRevoked:  isRevoked,
		targetURL:  targetURL,
		headerName: headerName,
		queryParam: queryParam,
		expiresAt:  time.Now().Add(c.ttl),
	}
	c.mu.Unlock()
}

// Get retrieves a cache entry.
// Returns (Entry{}, false) on miss or if the entry has expired (lazy eviction).
// Increments the hit/miss counters accordingly.
func (c *DEKCache) Get(tenantID, serviceID string, keyVersion uint32) (Entry, bool) {
	k := cacheKey{tenantID: tenantID, serviceID: serviceID, keyVersion: keyVersion}

	c.mu.RLock()
	entry, found := c.entries[k]
	c.mu.RUnlock()

	if !found || time.Now().After(entry.expiresAt) {
		if found {
			// Lazy eviction of expired entry.
			c.mu.Lock()
			// Re-check under write lock to avoid double-delete races.
			if e, ok2 := c.entries[k]; ok2 && time.Now().After(e.expiresAt) {
				delete(c.entries, k)
			}
			c.mu.Unlock()
		}
		c.misses.Add(1)
		return Entry{}, false
	}

	c.hits.Add(1)
	return Entry{
		WrappedDEK: entry.wrappedDEK,
		EncPayload: entry.encPayload,
		AuthScheme: entry.authScheme,
		IsRevoked:  entry.isRevoked,
		TargetURL:  entry.targetURL,
		HeaderName: entry.headerName,
		QueryParam: entry.queryParam,
	}, true
}

// InvalidateByService evicts all entries whose tenant_id and service_id match
// the given pair.  Called when a credential.rotated event is received for
// (tenantID, serviceID).
func (c *DEKCache) InvalidateByService(tenantID, serviceID string) {
	c.mu.Lock()
	defer c.mu.Unlock()
	for k := range c.entries {
		if k.tenantID == tenantID && k.serviceID == serviceID {
			delete(c.entries, k)
		}
	}
}

// Metrics returns the cumulative (hits, misses) counters since creation.
// These correspond to Prometheus counters
// mintkey_vault_dek_cache_hit_total / mintkey_vault_dek_cache_miss_total.
func (c *DEKCache) Metrics() (hits, misses int64) {
	return c.hits.Load(), c.misses.Load()
}

// Hits returns the cumulative cache-hit counter since creation.
func (c *DEKCache) Hits() int64 { return c.hits.Load() }

// Misses returns the cumulative cache-miss counter since creation.
func (c *DEKCache) Misses() int64 { return c.misses.Load() }
