package metrics

import (
	"testing"

	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/testutil"
)

func TestRecordSessionStart(t *testing.T) {
	// Reset metrics
	ActiveSessions.Set(0)
	SessionsByAgent.Reset()
	SessionsByService.Reset()

	// Record session start
	RecordSessionStart("agent_123", "service_456")

	// Verify active sessions incremented
	if got := testutil.ToFloat64(ActiveSessions); got != 1 {
		t.Errorf("ActiveSessions = %v, want 1", got)
	}

	// Verify agent sessions incremented
	if got := testutil.ToFloat64(SessionsByAgent.WithLabelValues("agent_123")); got != 1 {
		t.Errorf("SessionsByAgent(agent_123) = %v, want 1", got)
	}

	// Verify service sessions incremented
	if got := testutil.ToFloat64(SessionsByService.WithLabelValues("service_456")); got != 1 {
		t.Errorf("SessionsByService(service_456) = %v, want 1", got)
	}
}

func TestRecordSessionEnd(t *testing.T) {
	// Reset metrics
	ActiveSessions.Set(1)
	SessionsByAgent.WithLabelValues("agent_123").Set(1)
	SessionsByService.WithLabelValues("service_456").Set(1)

	// Record session end
	RecordSessionEnd("agent_123", "service_456", 3600.0, 1024, 2048)

	// Verify active sessions decremented
	if got := testutil.ToFloat64(ActiveSessions); got != 0 {
		t.Errorf("ActiveSessions = %v, want 0", got)
	}

	// Verify agent sessions decremented
	if got := testutil.ToFloat64(SessionsByAgent.WithLabelValues("agent_123")); got != 0 {
		t.Errorf("SessionsByAgent(agent_123) = %v, want 0", got)
	}

	// Verify service sessions decremented
	if got := testutil.ToFloat64(SessionsByService.WithLabelValues("service_456")); got != 0 {
		t.Errorf("SessionsByService(service_456) = %v, want 0", got)
	}
}

func TestRecordAuthFailure(t *testing.T) {
	// Reset metrics
	AuthFailures.Reset()

	// Record auth failures
	RecordAuthFailure("jwt")
	RecordAuthFailure("jwt")
	RecordAuthFailure("api_key")

	// Verify JWT failures
	if got := testutil.ToFloat64(AuthFailures.WithLabelValues("jwt")); got != 2 {
		t.Errorf("AuthFailures(jwt) = %v, want 2", got)
	}

	// Verify API key failures
	if got := testutil.ToFloat64(AuthFailures.WithLabelValues("api_key")); got != 1 {
		t.Errorf("AuthFailures(api_key) = %v, want 1", got)
	}
}

func TestRecordCommandBlock(t *testing.T) {
	// Get initial value
	initial := testutil.ToFloat64(CommandBlocks)

	// Record command block
	RecordCommandBlock()

	// Verify incremented
	if got := testutil.ToFloat64(CommandBlocks); got != initial+1 {
		t.Errorf("CommandBlocks = %v, want %v", got, initial+1)
	}
}

func TestRecordSessionTimeout(t *testing.T) {
	// Get initial value
	initial := testutil.ToFloat64(SessionTimeouts)

	// Record session timeout
	RecordSessionTimeout()

	// Verify incremented
	if got := testutil.ToFloat64(SessionTimeouts); got != initial+1 {
		t.Errorf("SessionTimeouts = %v, want %v", got, initial+1)
	}
}

func TestRecordBackendConnectionError(t *testing.T) {
	// Reset metrics
	BackendConnectionErrors.Reset()

	// Record errors
	RecordBackendConnectionError("timeout")
	RecordBackendConnectionError("timeout")
	RecordBackendConnectionError("refused")

	// Verify timeout errors
	if got := testutil.ToFloat64(BackendConnectionErrors.WithLabelValues("timeout")); got != 2 {
		t.Errorf("BackendConnectionErrors(timeout) = %v, want 2", got)
	}

	// Verify refused errors
	if got := testutil.ToFloat64(BackendConnectionErrors.WithLabelValues("refused")); got != 1 {
		t.Errorf("BackendConnectionErrors(refused) = %v, want 1", got)
	}
}

func TestRecordCommand(t *testing.T) {
	// Get initial value
	initial := testutil.ToFloat64(CommandCount)

	// Record command
	RecordCommand()

	// Verify incremented
	if got := testutil.ToFloat64(CommandCount); got != initial+1 {
		t.Errorf("CommandCount = %v, want %v", got, initial+1)
	}
}

func TestRecordSFTPOperation(t *testing.T) {
	// Reset metrics
	SFTPOperationCount.Reset()

	// Record operations
	RecordSFTPOperation("read")
	RecordSFTPOperation("read")
	RecordSFTPOperation("write")

	// Verify read operations
	if got := testutil.ToFloat64(SFTPOperationCount.WithLabelValues("read")); got != 2 {
		t.Errorf("SFTPOperationCount(read) = %v, want 2", got)
	}

	// Verify write operations
	if got := testutil.ToFloat64(SFTPOperationCount.WithLabelValues("write")); got != 1 {
		t.Errorf("SFTPOperationCount(write) = %v, want 1", got)
	}
}

func TestMetricsRegistration(t *testing.T) {
	// Verify all metrics are registered
	metrics := []prometheus.Collector{
		ActiveSessions,
		SessionDuration,
		BytesSent,
		BytesReceived,
		AuthFailures,
		CommandBlocks,
		SessionTimeouts,
		BackendConnectionErrors,
		VaultFetchDuration,
		SessionsByAgent,
		SessionsByService,
		CommandCount,
		SFTPOperationCount,
	}

	for _, metric := range metrics {
		if metric == nil {
			t.Error("metric is nil")
		}
	}
}
