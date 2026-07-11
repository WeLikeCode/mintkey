package budget_test

import (
	"bytes"
	"strings"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"

	"github.com/mintkey/mintkey/services/proxy-plugin/internal/budget"
)

func TestBudgetMetrics_SetUsed(t *testing.T) {
	m := budget.NewBudgetMetrics()
	labels := budget.MetricLabels{
		PermissionID: "perm_01ABC",
		AgentID:      "agent_01DEF",
		ServiceID:    "svc_01GHI",
		TenantID:     "tnt_01JKL",
	}

	m.SetUsed(labels, 42)

	var buf bytes.Buffer
	err := m.WriteMetricsTo(&buf)
	require.NoError(t, err)

	output := buf.String()
	assert.Contains(t, output, "mintkey_budget_used")
	assert.Contains(t, output, `permission_id="perm_01ABC"`)
	assert.Contains(t, output, `agent_id="agent_01DEF"`)
	assert.Contains(t, output, `service_id="svc_01GHI"`)
	assert.Contains(t, output, `tenant_id="tnt_01JKL"`)
	assert.Contains(t, output, "42")
}

func TestBudgetMetrics_SetCeiling(t *testing.T) {
	m := budget.NewBudgetMetrics()
	labels := budget.MetricLabels{
		PermissionID: "perm_01ABC",
		AgentID:      "agent_01DEF",
		ServiceID:    "svc_01GHI",
		TenantID:     "tnt_01JKL",
	}

	m.SetCeiling(labels, 1000)

	var buf bytes.Buffer
	err := m.WriteMetricsTo(&buf)
	require.NoError(t, err)

	output := buf.String()
	assert.Contains(t, output, "mintkey_budget_ceiling")
	assert.Contains(t, output, "1000")
}

func TestBudgetMetrics_IncDenied(t *testing.T) {
	m := budget.NewBudgetMetrics()
	labels := budget.MetricLabels{
		PermissionID: "perm_01ABC",
		AgentID:      "agent_01DEF",
		ServiceID:    "svc_01GHI",
		TenantID:     "tnt_01JKL",
	}

	m.IncDenied(labels)
	m.IncDenied(labels)

	var buf bytes.Buffer
	err := m.WriteMetricsTo(&buf)
	require.NoError(t, err)

	output := buf.String()
	assert.Contains(t, output, "mintkey_budget_denied_total")
	// Should be 2 after two increments.
	lines := strings.Split(output, "\n")
	for _, line := range lines {
		if strings.Contains(line, "mintkey_budget_denied_total{") {
			assert.Contains(t, line, " 2")
		}
	}
}

func TestBudgetMetrics_AllThreeAfterBudgetCheckedRequest(t *testing.T) {
	m := budget.NewBudgetMetrics()
	labels := budget.MetricLabels{
		PermissionID: "perm_01ABC",
		AgentID:      "agent_01DEF",
		ServiceID:    "svc_01GHI",
		TenantID:     "tnt_01JKL",
	}

	// Simulate a budget-checked request flow:
	// 1. Set ceiling when config is loaded.
	m.SetCeiling(labels, 100)
	// 2. Set used after successful increment.
	m.SetUsed(labels, 50)
	// 3. Increment denied (simulating a separate denial).
	m.IncDenied(labels)

	var buf bytes.Buffer
	err := m.WriteMetricsTo(&buf)
	require.NoError(t, err)

	output := buf.String()

	// All three metric families must be present.
	assert.Contains(t, output, "# TYPE mintkey_budget_used gauge")
	assert.Contains(t, output, "# TYPE mintkey_budget_ceiling gauge")
	assert.Contains(t, output, "# TYPE mintkey_budget_denied_total counter")

	// All labels must appear.
	assert.Contains(t, output, `permission_id="perm_01ABC"`)
	assert.Contains(t, output, `agent_id="agent_01DEF"`)
	assert.Contains(t, output, `service_id="svc_01GHI"`)
	assert.Contains(t, output, `tenant_id="tnt_01JKL"`)
}
