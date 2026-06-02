// Package permissions provides the email permission grant checker for email-proxy.
//
// The email-proxy calls admin-api to verify that (agent_id, email_service_id)
// exists in email_permission_grants before processing any request.
//
// If no grant exists, the request is rejected with HTTP 403 and the
// mintkey:code=permission_denied error body.
//
// Source: feat/email-permission-grants.
package permissions

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"log/slog"
	"net/http"
	"time"
)

// ErrPermissionDenied is returned when no email_permission_grant exists
// for the (agent_id, email_service_id) pair.
var ErrPermissionDenied = errors.New("agent has no email_permission_grant for this email_service")

// Checker verifies email permission grants by calling admin-api.
type Checker struct {
	adminAPIURL    string
	serviceToken   string
	httpClient     *http.Client
}

// NewChecker creates a new Checker.
//
// adminAPIURL is the base URL of the admin-api service (e.g. "http://admin-api:8080").
// serviceToken is the X-Mintkey-Service-Token used to authenticate calls to admin-api.
func NewChecker(adminAPIURL, serviceToken string) *Checker {
	return &Checker{
		adminAPIURL:  adminAPIURL,
		serviceToken: serviceToken,
		httpClient: &http.Client{
			Timeout: 5 * time.Second,
		},
	}
}

// CheckGrant verifies that (agentID, emailServiceID) has a row in
// email_permission_grants for the given tenant.
//
// Returns nil if a grant exists.
// Returns ErrPermissionDenied if no grant exists.
// Returns a wrapped error for transient failures (caller should treat as 503).
func (c *Checker) CheckGrant(ctx context.Context, tenantID, agentID, emailServiceID string) error {
	url := fmt.Sprintf(
		"%s/v1/tenants/%s/email-permission-grants?agent_id=%s&email_service_id=%s",
		c.adminAPIURL,
		tenantID,
		agentID,
		emailServiceID,
	)

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		return fmt.Errorf("permissions.CheckGrant: build request: %w", err)
	}
	req.Header.Set("X-Mintkey-Service-Token", c.serviceToken)

	resp, err := c.httpClient.Do(req)
	if err != nil {
		slog.Warn("permissions.CheckGrant: admin-api unreachable",
			"tenant_id", tenantID,
			"agent_id", agentID,
			"email_service_id", emailServiceID,
			"error", err,
		)
		return fmt.Errorf("permissions.CheckGrant: admin-api call failed: %w", err)
	}
	defer resp.Body.Close() //nolint:errcheck

	if resp.StatusCode != http.StatusOK {
		slog.Warn("permissions.CheckGrant: admin-api returned non-200",
			"status", resp.StatusCode,
			"tenant_id", tenantID,
			"agent_id", agentID,
			"email_service_id", emailServiceID,
		)
		return fmt.Errorf("permissions.CheckGrant: admin-api returned %d", resp.StatusCode)
	}

	var body struct {
		Grants []struct{} `json:"grants"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&body); err != nil {
		return fmt.Errorf("permissions.CheckGrant: decode response: %w", err)
	}

	if len(body.Grants) == 0 {
		return ErrPermissionDenied
	}

	return nil
}
