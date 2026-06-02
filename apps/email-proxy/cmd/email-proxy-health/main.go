// Package main is the Docker HEALTHCHECK probe for the Email Proxy.
//
// It performs a GET /healthz against localhost:8088 and exits 0 on success,
// 1 on failure. Mirrors the ssh-proxy pattern.
package main

import (
	"fmt"
	"net/http"
	"os"
)

func main() {
	port := "8088"
	if v := os.Getenv("MINTKEY_EMAIL_PROXY_HTTP_PORT"); v != "" {
		port = v
	}

	url := fmt.Sprintf("http://localhost:%s/healthz", port)
	resp, err := http.Get(url) //nolint:gosec // localhost probe, not user-controlled
	if err != nil {
		fmt.Fprintf(os.Stderr, "health probe failed: %v\n", err)
		os.Exit(1)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		fmt.Fprintf(os.Stderr, "health probe: status %d\n", resp.StatusCode)
		os.Exit(1)
	}

	fmt.Println("ok")
	os.Exit(0)
}
