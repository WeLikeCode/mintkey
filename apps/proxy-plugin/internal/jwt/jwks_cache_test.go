package jwt_test

import (
	"testing"
	"time"

	"github.com/mintkey/mintkey/services/proxy-plugin/internal/jwt"
)

func TestJWKSRefreshRateLimit_FirstUnknownKIDTriggersRefresh(t *testing.T) {
	c := jwt.NewJWKSRefreshLimiter()
	// First attempt for unknown kid → allowed (shouldRefresh=true)
	if !c.ShouldRefresh("kid_unknown") {
		t.Fatal("expected first unknown kid to trigger refresh")
	}
}

func TestJWKSRefreshRateLimit_SecondRequestWithin60sSkipsRefresh(t *testing.T) {
	c := jwt.NewJWKSRefreshLimiter()
	c.ShouldRefresh("kid_unknown")      // first: allowed
	if c.ShouldRefresh("kid_unknown") { // second within 60s: blocked
		t.Fatal("expected second request within 60s to be blocked")
	}
}

func TestJWKSRefreshRateLimit_AfterExpiryAllowsRefresh(t *testing.T) {
	c := jwt.NewJWKSRefreshLimiterWithTTL(10 * time.Millisecond)
	c.ShouldRefresh("kid_unknown")
	time.Sleep(20 * time.Millisecond)
	if !c.ShouldRefresh("kid_unknown") {
		t.Fatal("expected refresh to be allowed after TTL expires")
	}
}

func TestJWKSRefreshRateLimit_DifferentKIDsAreIndependent(t *testing.T) {
	c := jwt.NewJWKSRefreshLimiter()
	c.ShouldRefresh("kid_A")
	if !c.ShouldRefresh("kid_B") {
		t.Fatal("different kids should be independent")
	}
}
