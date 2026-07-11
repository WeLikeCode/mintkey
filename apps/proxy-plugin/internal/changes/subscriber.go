// Package changes subscribes to the mintkey:agent PostgreSQL change channel
// and populates in-memory revocation sets for the Egress Proxy plugin.
//
// Per ADR-0014.4 the plugin does NOT subscribe to mintkey:credential —
// the Vault Adapter handles credential cache invalidation.
//
// Source: ADR-0014.1; ADR-0014.4; T-1.6.7.
package changes

import (
	"context"
	"encoding/json"
	"fmt"
	"time"

	"github.com/lib/pq"

	"github.com/mintkey/mintkey/services/proxy-plugin/internal/revocation"
)

// listenChannel is the only channel this subscriber ever listens on.
// The plugin must NOT subscribe to mintkey:credential per ADR-0014.4.
const listenChannel = "mintkey:agent"

// ClassicalKeyCache is the subset of classicalkey.Handler used for cache eviction.
// Accepts nil — calls are no-ops when no classical-key branch is wired.
type ClassicalKeyCache interface {
	EvictByFingerprint(fp string)
	EvictByAgentID(agentID string)
}

// BudgetCacheInvalidator is called when a budget.config_updated event arrives.
// It invalidates any locally cached budget state for the affected permission_id.
// Accepts nil — calls are no-ops when budget tracking is not wired.
//
// Source: FR-10, design §6; T-BUD-3.4.
type BudgetCacheInvalidator interface {
	InvalidateBudget(permissionID string)
}

// Subscriber listens on the mintkey:agent PostgreSQL NOTIFY channel.
// It does NOT listen to mintkey:credential (Vault Adapter owns that).
type Subscriber struct {
	dsn         string
	agents      *revocation.AgentRevocationSet
	jtis        *revocation.JTIRevocationSet
	cache       ClassicalKeyCache      // nil when classical-key branch is not wired
	budgetCache BudgetCacheInvalidator // nil when budget tracking is not wired
}

// NewSubscriber constructs a Subscriber with the provided revocation sets.
// cache may be nil when the classical-key branch is not active.
// budgetCache may be nil when budget tracking is not active.
func NewSubscriber(
	dsn string,
	agents *revocation.AgentRevocationSet,
	jtis *revocation.JTIRevocationSet,
	cache ClassicalKeyCache,
	opts ...SubscriberOption,
) *Subscriber {
	s := &Subscriber{dsn: dsn, agents: agents, jtis: jtis, cache: cache}
	for _, opt := range opts {
		opt(s)
	}
	return s
}

// SubscriberOption is a functional option for NewSubscriber.
type SubscriberOption func(*Subscriber)

// WithBudgetCache wires a BudgetCacheInvalidator into the subscriber.
func WithBudgetCache(bc BudgetCacheInvalidator) SubscriberOption {
	return func(s *Subscriber) {
		s.budgetCache = bc
	}
}

// Start opens a pq.Listener on listenChannel and blocks dispatching
// notifications until ctx is cancelled. On transient connection failures it
// reconnects with a 5-second backoff (via pq.Listener's built-in reconnect).
//
// Start returns only when ctx is Done.
func (s *Subscriber) Start(ctx context.Context) error {
	l := pq.NewListener(
		s.dsn,
		5*time.Second,  // minReconnectInterval
		60*time.Second, // maxReconnectInterval
		nil,            // no event callback needed
	)
	defer l.Close()

	if err := l.Listen(listenChannel); err != nil {
		return fmt.Errorf("LISTEN %s: %w", listenChannel, err)
	}

	for {
		select {
		case <-ctx.Done():
			return ctx.Err()
		case n, ok := <-l.Notify:
			if !ok {
				return fmt.Errorf("notification channel closed")
			}
			if n == nil {
				// nil is a keep-alive ping from pq — ignore.
				continue
			}
			// Non-fatal: log-worthy but keep running.
			_ = s.HandleNotification(n.Extra)
		case <-time.After(90 * time.Second):
			// Periodic ping to detect a dead connection (lib/pq recommendation).
			if err := l.Ping(); err != nil {
				// Reconnect will be handled by pq.Listener automatically on the
				// next iteration; just log by returning and letting Start loop.
				return fmt.Errorf("ping failed: %w", err)
			}
		}
	}
}

// HandleNotification dispatches a raw NOTIFY payload to the appropriate set.
// Exported to allow unit testing without a real database connection.
func (s *Subscriber) HandleNotification(payload string) error {
	var evt struct {
		EventType      string `json:"event_type"`
		AgentID        string `json:"agent_id"`
		JTI            string `json:"jti"`
		KeyFingerprint string `json:"key_fingerprint"`
		TargetID       string `json:"target_id"`
	}
	if err := json.Unmarshal([]byte(payload), &evt); err != nil {
		return fmt.Errorf("parse notification payload: %w", err)
	}

	switch evt.EventType {
	case "agent.revoked":
		s.agents.Add(evt.AgentID)
		if s.cache != nil {
			s.cache.EvictByAgentID(evt.AgentID)
		}
	case "token.revoked":
		s.jtis.Add(evt.JTI)
	case "api_key.revoked":
		if s.cache != nil {
			s.cache.EvictByFingerprint(evt.KeyFingerprint)
		}
	case "budget.config_updated":
		if s.budgetCache != nil && evt.TargetID != "" {
			s.budgetCache.InvalidateBudget(evt.TargetID)
		}
	// Unknown event types are silently ignored — forward compatibility.
	}
	return nil
}
