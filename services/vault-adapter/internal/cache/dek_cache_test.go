package cache_test

import (
	"testing"
	"time"

	"github.com/mintkey/mintkey/services/vault-adapter/internal/cache"
)

func TestCacheHit(t *testing.T) {
	c := cache.New(5 * time.Minute)
	wrappedDEK := []byte("wrapped-dek-bytes")
	encPayload := []byte("enc-payload-bytes")
	c.Put("tenant_01", "svc_01", 1, wrappedDEK, encPayload, 1, false, "", "", "")

	entry, ok := c.Get("tenant_01", "svc_01", 1)
	if !ok {
		t.Fatal("expected cache hit")
	}
	if string(entry.WrappedDEK) != string(wrappedDEK) {
		t.Fatalf("expected wrappedDEK %q got %q", wrappedDEK, entry.WrappedDEK)
	}
	if string(entry.EncPayload) != string(encPayload) {
		t.Fatalf("expected encPayload %q got %q", encPayload, entry.EncPayload)
	}
	if entry.AuthScheme != 1 {
		t.Fatalf("expected auth_scheme=1, got %d", entry.AuthScheme)
	}
	if entry.IsRevoked {
		t.Fatal("expected IsRevoked=false")
	}
}

func TestCacheMiss(t *testing.T) {
	c := cache.New(5 * time.Minute)
	_, ok := c.Get("tenant_01", "svc_01", 1)
	if ok {
		t.Fatal("expected cache miss")
	}
}

func TestCacheExpiry(t *testing.T) {
	c := cache.New(10 * time.Millisecond)
	c.Put("tenant_01", "svc_01", 1, []byte("dek"), []byte("payload"), 0, false, "", "", "")
	time.Sleep(20 * time.Millisecond)
	_, ok := c.Get("tenant_01", "svc_01", 1)
	if ok {
		t.Fatal("expected expired entry to be evicted")
	}
}

func TestCacheInvalidateByServicePair(t *testing.T) {
	c := cache.New(5 * time.Minute)
	c.Put("tenant_01", "svc_01", 1, []byte("dek_v1"), []byte("pay_v1"), 0, false, "", "", "")
	c.Put("tenant_01", "svc_01", 2, []byte("dek_v2"), []byte("pay_v2"), 0, false, "", "", "")
	c.Put("tenant_01", "svc_02", 1, []byte("dek_other"), []byte("pay_other"), 0, false, "", "", "")

	c.InvalidateByService("tenant_01", "svc_01")

	_, ok1 := c.Get("tenant_01", "svc_01", 1)
	_, ok2 := c.Get("tenant_01", "svc_01", 2)
	_, ok3 := c.Get("tenant_01", "svc_02", 1) // unaffected

	if ok1 || ok2 {
		t.Fatal("expected svc_01 entries to be evicted")
	}
	if !ok3 {
		t.Fatal("expected svc_02 entry to survive")
	}
}

func TestCacheMetrics(t *testing.T) {
	c := cache.New(5 * time.Minute)
	c.Put("tenant_01", "svc_01", 1, []byte("dek"), []byte("payload"), 0, false, "", "", "")
	c.Get("tenant_01", "svc_01", 1)  // hit
	c.Get("tenant_01", "svc_01", 99) // miss

	hits, misses := c.Metrics()
	if hits != 1 {
		t.Fatalf("expected 1 hit, got %d", hits)
	}
	if misses != 1 {
		t.Fatalf("expected 1 miss, got %d", misses)
	}
}
