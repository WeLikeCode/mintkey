// Package svcid provides a client that reads a Mintkey service token from a
// file, supporting hot rotation (ADR-0014.2).
//
// Token() reads the file on every call so that a credential rotation (replacing
// the file content) is picked up without a restart.
package svcid

import (
	"fmt"
	"os"
	"strings"
)

const defaultTokenPath = "/run/secrets/mintkey_service_token"

// Client holds the resolved path of the service-token file.
type Client struct {
	path string
}

// NewClient creates a Client that reads the service token from filePath.
// If filePath is empty the default path "/run/secrets/mintkey_service_token" is
// used.  An error is returned if the file cannot be read at construction time
// (fast-fail so misconfigured deployments surface immediately).
func NewClient(filePath string) (*Client, error) {
	if filePath == "" {
		filePath = defaultTokenPath
	}
	// Validate the file is readable at startup.
	if _, err := os.ReadFile(filePath); err != nil {
		return nil, fmt.Errorf("svcid: cannot read token file %q: %w", filePath, err)
	}
	return &Client{path: filePath}, nil
}

// Token reads and returns the current token from the file.  Each call re-reads
// the file so that an in-place rotation is reflected immediately.
func (c *Client) Token() (string, error) {
	data, err := os.ReadFile(c.path)
	if err != nil {
		return "", fmt.Errorf("svcid: cannot read token file %q: %w", c.path, err)
	}
	return strings.TrimRight(string(data), "\r\n"), nil
}
