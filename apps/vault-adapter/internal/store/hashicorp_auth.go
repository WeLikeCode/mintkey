// hashicorp_auth.go — AppRole login + background token renewal for the
// HashiCorp Vault KV v2 backend.
//
// Security constraint (NFR-1): the roleID value, secretID value, and client
// token MUST NEVER appear in any log message, error string, or slog attribute.
// Only fixed strings and numeric TTL values are logged.
package store

import (
	"context"
	"log/slog"
	"time"

	approle "github.com/hashicorp/vault/api/auth/approle"

	vaultapi "github.com/hashicorp/vault/api"
)

// appRoleAuth manages the lifecycle of a HashiCorp Vault AppRole token,
// including background renewal and re-login on expiry.
type appRoleAuth struct {
	client *vaultapi.Client
	log    *slog.Logger
	cancel context.CancelFunc
	done   chan struct{}
}

// newAppRoleAuth performs an AppRole login and starts the background renewal
// goroutine. The renewal goroutine is tied to ctx; call stop() to shut it down.
//
// SECURITY: roleID and secretID are not logged at any point in this function.
func newAppRoleAuth(ctx context.Context, client *vaultapi.Client, roleID, secretID string, log *slog.Logger) (*appRoleAuth, error) {
	auth, err := approle.NewAppRoleAuth(roleID, &approle.SecretID{FromString: secretID})
	if err != nil {
		return nil, err
	}

	authSecret, err := client.Auth().Login(ctx, auth)
	if err != nil {
		return nil, err
	}

	childCtx, cancel := context.WithCancel(ctx)
	a := &appRoleAuth{
		client: client,
		log:    log,
		cancel: cancel,
		done:   make(chan struct{}),
	}
	go a.startRenewal(childCtx, authSecret, roleID, secretID)
	return a, nil
}

// startRenewal watches the auth token's lifetime and renews it automatically.
// On renewal failure it re-logs in with exponential backoff.
// The goroutine exits when ctx is cancelled.
//
// SECURITY: no log message emits the token, roleID, or secretID.
func (a *appRoleAuth) startRenewal(ctx context.Context, secret *vaultapi.Secret, roleID, secretID string) {
	defer close(a.done)

	watcher, err := a.client.NewLifetimeWatcher(&vaultapi.LifetimeWatcherInput{Secret: secret})
	if err != nil {
		a.log.Error("hashicorp watcher create failed")
		return
	}
	go watcher.Start()
	defer watcher.Stop()

	for {
		select {
		case renewal := <-watcher.RenewCh():
			a.log.Info("hashicorp token renewed", "ttl", renewal.Secret.LeaseDuration)

		case <-watcher.DoneCh():
			// Token expired or renewal failed; re-login with backoff.
			a.log.Info("hashicorp token renewal done; re-logging in")
			if !a.reloginWithBackoff(ctx, roleID, secretID) {
				// Context cancelled during backoff — exit.
				return
			}
			// Successfully re-logged in; the client token is already updated.
			// Start a fresh watcher for the new token.
			newSecret, err := a.client.Auth().Token().LookupSelf()
			if err != nil {
				a.log.Warn("hashicorp token lookup after re-login failed")
				return
			}
			watcher.Stop()
			watcher, err = a.client.NewLifetimeWatcher(&vaultapi.LifetimeWatcherInput{Secret: newSecret})
			if err != nil {
				a.log.Error("hashicorp watcher re-create failed")
				return
			}
			go watcher.Start()
			a.log.Info("hashicorp token renewal restarted")

		case <-ctx.Done():
			return
		}
	}
}

// reloginWithBackoff attempts to re-login via AppRole with exponential backoff.
// Returns true on success, false if ctx is cancelled before success.
// Max 5 retries; backoff starts at 250 ms, doubles each attempt, capped at 2 s.
func (a *appRoleAuth) reloginWithBackoff(ctx context.Context, roleID, secretID string) bool {
	const maxRetries = 5
	delay := 250 * time.Millisecond
	maxDelay := 2 * time.Second

	for attempt := 0; attempt < maxRetries; attempt++ {
		select {
		case <-ctx.Done():
			return false
		default:
		}

		auth, err := approle.NewAppRoleAuth(roleID, &approle.SecretID{FromString: secretID})
		if err == nil {
			_, err = a.client.Auth().Login(ctx, auth)
		}
		if err == nil {
			a.log.Info("hashicorp re-login succeeded")
			return true
		}
		a.log.Warn("hashicorp re-login failed; retrying")

		select {
		case <-ctx.Done():
			return false
		case <-time.After(delay):
		}

		delay *= 2
		if delay > maxDelay {
			delay = maxDelay
		}
	}

	a.log.Error("hashicorp re-login exhausted retries; giving up")
	return false
}

// stop cancels the renewal goroutine and waits for it to exit.
func (a *appRoleAuth) stop() {
	a.cancel()
	<-a.done
}
