// Mintkey Egress Proxy Plugin — skeleton entry point.
//
// This process runs alongside Kong Gateway and implements the custom
// credential-injection logic via the Kong go-pdk external plugin protocol
// (ADR-0004). In the MVP skeleton, actual go-pdk registration is deferred;
// this binary loads configuration, logs startup, and blocks until SIGINT/SIGTERM.
//
// The plugin does NOT cache plaintext credentials (ADR-0014.4). Every proxy
// hit calls the Vault Adapter gRPC endpoint for the credential and holds it
// only within request scope.
//
// Source: design §10; ADR-0004; ADR-0014.4; T-1.0.7.
package main

import (
	"context"
	"log"
	"os/signal"
	"syscall"

	"github.com/mintkey/mintkey/services/proxy-plugin/internal/config"
)

func main() {
	cfg := config.Load()

	log.Printf("proxy-plugin: starting env=%s vault=%s jwks=%s socket=%s",
		cfg.Env, cfg.VaultAddrGRPC, cfg.JWKSEndpoint, cfg.PluginSocket)

	// Block until SIGINT or SIGTERM.
	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()

	<-ctx.Done()
	log.Println("proxy-plugin: shutdown complete")
}
