package googleserviceaccount

import (
	"fmt"
	"sync"
	"time"
)

// renewalBuffer is the time before token expiry at which a cached entry is
// considered stale and a new token should be fetched proactively.
const renewalBuffer = 5 * time.Minute

// cachedToken holds a single access token and its absolute expiry wall-clock
// time as returned by the token endpoint.
type cachedToken struct {
	token     string
	expiresAt time.Time
}

// Cache is an in-process access-token cache keyed by
// (tenantID, serviceID, privateKeyID).  Safe for concurrent use.
type Cache struct {
	mu    sync.RWMutex
	items map[string]cachedToken
}

// nowFn is the time source used by Get.  Overriding this in tests allows
// simulating clock advance without real sleeps.
var nowFn = time.Now

// cacheKey returns the string key for a given (tenantID, serviceID, privateKeyID)
// triple.
func cacheKey(tenantID, serviceID, privateKeyID string) string {
	return fmt.Sprintf("%s\x00%s\x00%s", tenantID, serviceID, privateKeyID)
}

// Get returns the cached access token if it exists and will not expire within
// the next renewalBuffer (5 min).  Returns ("", false) on miss or near-expiry.
func (c *Cache) Get(tenantID, serviceID, privateKeyID string) (string, bool) {
	k := cacheKey(tenantID, serviceID, privateKeyID)

	c.mu.RLock()
	entry, found := c.items[k]
	c.mu.RUnlock()

	if !found {
		return "", false
	}
	// Miss if the token will expire before (now + renewalBuffer).
	if nowFn().Add(renewalBuffer).After(entry.expiresAt) {
		return "", false
	}
	return entry.token, true
}

// Set stores an access token in the cache.  expiresIn is the number of seconds
// until the token expires, as returned by the token endpoint.
func (c *Cache) Set(tenantID, serviceID, privateKeyID, token string, expiresIn int) {
	k := cacheKey(tenantID, serviceID, privateKeyID)
	exp := nowFn().Add(time.Duration(expiresIn) * time.Second)

	c.mu.Lock()
	c.items[k] = cachedToken{token: token, expiresAt: exp}
	c.mu.Unlock()
}

// Invalidate removes a single cache entry.  A subsequent Get will return a
// miss, triggering a fresh token fetch.
func (c *Cache) Invalidate(tenantID, serviceID, privateKeyID string) {
	k := cacheKey(tenantID, serviceID, privateKeyID)

	c.mu.Lock()
	delete(c.items, k)
	c.mu.Unlock()
}

// GlobalCache is in-process only. On Vault Adapter restart, all entries are
// evicted and tokens are re-fetched on the next RetrieveCredential call.
var GlobalCache = &Cache{items: make(map[string]cachedToken)}
