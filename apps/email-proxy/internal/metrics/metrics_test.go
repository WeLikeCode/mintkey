package metrics

import (
	"testing"

	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/testutil"
)

// TestMetricsRegistration verifies that all 6 metric vectors are non-nil and
// registered against prometheus.DefaultRegisterer.
func TestMetricsRegistration(t *testing.T) {
	collectors := []prometheus.Collector{
		RequestsTotal,
		RequestDuration,
		OAuth2RefreshTotal,
		RateLimitThrottledTotal,
		ActiveConnections,
		AuditEventsEmittedTotal,
	}
	for i, c := range collectors {
		if c == nil {
			t.Errorf("metric[%d] is nil — promauto registration failed", i)
		}
	}
}

// TestRecordRequest verifies RequestsTotal increments and RequestDuration observes.
func TestRecordRequest(t *testing.T) {
	RequestsTotal.Reset()

	RecordRequest("list_mailboxes", "read:email", "200", 0.05)
	RecordRequest("list_mailboxes", "read:email", "200", 0.02)
	RecordRequest("list_mailboxes", "read:email", "429", 0.001)

	if got := testutil.ToFloat64(RequestsTotal.WithLabelValues("list_mailboxes", "read:email", "200")); got != 2 {
		t.Errorf("RequestsTotal(list_mailboxes,read:email,200) = %v, want 2", got)
	}
	if got := testutil.ToFloat64(RequestsTotal.WithLabelValues("list_mailboxes", "read:email", "429")); got != 1 {
		t.Errorf("RequestsTotal(list_mailboxes,read:email,429) = %v, want 1", got)
	}
}

// TestRecordOAuth2Refresh verifies OAuth2RefreshTotal label cardinality.
func TestRecordOAuth2Refresh(t *testing.T) {
	OAuth2RefreshTotal.Reset()

	RecordOAuth2Refresh("gmail", "success")
	RecordOAuth2Refresh("gmail", "success")
	RecordOAuth2Refresh("gmail", "revoked")
	RecordOAuth2Refresh("outlook", "error")

	if got := testutil.ToFloat64(OAuth2RefreshTotal.WithLabelValues("gmail", "success")); got != 2 {
		t.Errorf("OAuth2Refresh(gmail,success) = %v, want 2", got)
	}
	if got := testutil.ToFloat64(OAuth2RefreshTotal.WithLabelValues("gmail", "revoked")); got != 1 {
		t.Errorf("OAuth2Refresh(gmail,revoked) = %v, want 1", got)
	}
	if got := testutil.ToFloat64(OAuth2RefreshTotal.WithLabelValues("outlook", "error")); got != 1 {
		t.Errorf("OAuth2Refresh(outlook,error) = %v, want 1", got)
	}
}

// TestRecordRateLimitThrottle verifies RateLimitThrottledTotal by (agent,service).
func TestRecordRateLimitThrottle(t *testing.T) {
	RateLimitThrottledTotal.Reset()

	RecordRateLimitThrottle("agent_01", "svc_01")
	RecordRateLimitThrottle("agent_01", "svc_01")
	RecordRateLimitThrottle("agent_02", "svc_01")

	if got := testutil.ToFloat64(RateLimitThrottledTotal.WithLabelValues("agent_01", "svc_01")); got != 2 {
		t.Errorf("RateLimitThrottle(agent_01,svc_01) = %v, want 2", got)
	}
	if got := testutil.ToFloat64(RateLimitThrottledTotal.WithLabelValues("agent_02", "svc_01")); got != 1 {
		t.Errorf("RateLimitThrottle(agent_02,svc_01) = %v, want 1", got)
	}
}

// TestRecordActiveConnections verifies the gauge is set (not incremented).
func TestRecordActiveConnections(t *testing.T) {
	ActiveConnections.Reset()

	RecordActiveConnections("gmail", 3)
	if got := testutil.ToFloat64(ActiveConnections.WithLabelValues("gmail")); got != 3 {
		t.Errorf("ActiveConnections(gmail) = %v, want 3", got)
	}

	// Gauge should reflect the latest Set, not accumulate.
	RecordActiveConnections("gmail", 1)
	if got := testutil.ToFloat64(ActiveConnections.WithLabelValues("gmail")); got != 1 {
		t.Errorf("ActiveConnections(gmail) after update = %v, want 1", got)
	}
}

// TestRecordAuditEvent verifies AuditEventsEmittedTotal by event_type.
func TestRecordAuditEvent(t *testing.T) {
	AuditEventsEmittedTotal.Reset()

	RecordAuditEvent("email.message.sent")
	RecordAuditEvent("email.message.sent")
	RecordAuditEvent("email.mailboxes.listed")

	if got := testutil.ToFloat64(AuditEventsEmittedTotal.WithLabelValues("email.message.sent")); got != 2 {
		t.Errorf("AuditEventsEmitted(email.message.sent) = %v, want 2", got)
	}
	if got := testutil.ToFloat64(AuditEventsEmittedTotal.WithLabelValues("email.mailboxes.listed")); got != 1 {
		t.Errorf("AuditEventsEmitted(email.mailboxes.listed) = %v, want 1", got)
	}
}
