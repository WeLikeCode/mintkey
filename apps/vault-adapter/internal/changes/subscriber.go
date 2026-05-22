// Package changes subscribes to the mintkey:credential PostgreSQL NOTIFY channel
// and invalidates the in-process DEK cache on credential.rotated events.
//
// ADR-0014.1: The channel name is global (mintkey:credential); tenant filtering
// is performed by the subscriber, not the channel name.
// ADR-0014.4: The DEK cache lives in the Vault Adapter only.
//
// Source: T-1.3.5.
package changes

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"sync/atomic"
	"time"

	"github.com/lib/pq"
)

const channel = "mintkey:credential"

// dekInvalidator is the subset of the DEK cache used by the subscriber.
type dekInvalidator interface {
	InvalidateByService(tenantID, serviceID string)
}

// Subscriber listens on the mintkey:credential PostgreSQL NOTIFY channel.
// On a credential.rotated event it calls dekCache.InvalidateByService.
// lastMessageNanos records the UnixNano timestamp of the most recently
// processed notification (not keepalive pings); used for lag metrics.
type Subscriber struct {
	dsn              string
	dekCache         dekInvalidator
	lastMessageNanos atomic.Int64
}

// rotationPayload is the JSON shape of a credential.rotated notification.
type rotationPayload struct {
	EventType string `json:"event_type"`
	TenantID  string `json:"tenant_id"`
	ServiceID string `json:"service_id"`
	KeyVersion int   `json:"key_version"`
}

// NewSubscriber creates a Subscriber that uses dsn to open the LISTEN connection
// and calls dekCache.InvalidateByService on credential.rotated events.
func NewSubscriber(dsn string, dekCache dekInvalidator) *Subscriber {
	return &Subscriber{dsn: dsn, dekCache: dekCache}
}

// Start opens a PostgreSQL LISTEN connection, subscribes to mintkey:credential,
// and dispatches incoming notifications until ctx is cancelled.
// It blocks until ctx is done and then returns ctx.Err().
func (s *Subscriber) Start(ctx context.Context) error {
	reportProblem := func(ev pq.ListenerEventType, err error) {
		if err != nil {
			log.Printf("changes.Subscriber: listener event %d: %v", ev, err)
		}
	}

	listener := pq.NewListener(s.dsn, 10*time.Second, time.Minute, reportProblem)
	if err := listener.Listen(channel); err != nil {
		return fmt.Errorf("changes.Subscriber: LISTEN %s: %w", channel, err)
	}
	defer func() { _ = listener.Close() }()

	for {
		select {
		case <-ctx.Done():
			return ctx.Err()
		case n, ok := <-listener.Notify:
			if !ok {
				// Channel closed — listener was shut down.
				return fmt.Errorf("changes.Subscriber: notify channel closed")
			}
			if n == nil {
				// Keepalive ping; ignore.
				continue
			}
			if err := s.handleNotification(n.Extra); err != nil {
				log.Printf("changes.Subscriber: handle notification: %v", err)
			}
		}
	}
}

// handleNotification parses a single NOTIFY payload and invalidates the DEK
// cache when the event_type is "credential.rotated".
// Unknown event types are silently ignored (forward-compatible).
// Malformed JSON returns an error.
// Every call (including unknown event types) records the receipt time so that
// LagSeconds reflects the last active message, not the last rotation.
func (s *Subscriber) handleNotification(payload string) error {
	// Record receipt time before parsing so that even unknown events count.
	s.lastMessageNanos.Store(time.Now().UnixNano())

	var p rotationPayload
	if err := json.Unmarshal([]byte(payload), &p); err != nil {
		return fmt.Errorf("changes.Subscriber: malformed JSON: %w", err)
	}

	if p.EventType != "credential.rotated" {
		// Unknown event — ignore; do not return an error.
		return nil
	}

	s.dekCache.InvalidateByService(p.TenantID, p.ServiceID)
	return nil
}

// LagSeconds returns the number of seconds elapsed since the last notification
// was received from the PostgreSQL channel.
// Returns 0 if no message has ever been received (subscriber idle since startup).
func (s *Subscriber) LagSeconds() float64 {
	last := s.lastMessageNanos.Load()
	if last == 0 {
		return 0 // never received a message
	}
	return float64(time.Now().UnixNano()-last) / 1e9
}
