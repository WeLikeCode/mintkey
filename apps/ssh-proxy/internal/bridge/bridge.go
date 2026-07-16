// Package bridge handles bidirectional I/O bridging between SSH channels.
package bridge

import (
	"io"
	"log/slog"
	"sync"

	"golang.org/x/crypto/ssh"
)

// Bridge manages bidirectional data flow between two SSH channels.
type Bridge struct {
	agentChannel  ssh.Channel
	backendChannel ssh.Channel
	bytesSent     int64
	bytesReceived int64
	mu            sync.Mutex
	closed        bool
}

// NewBridge creates a new bridge between agent and backend channels.
func NewBridge(agentChannel, backendChannel ssh.Channel) *Bridge {
	return &Bridge{
		agentChannel:   agentChannel,
		backendChannel: backendChannel,
	}
}

// Start begins bidirectional data forwarding.
// This method blocks until one of the channels is closed.
func (b *Bridge) Start() error {
	var wg sync.WaitGroup
	errCh := make(chan error, 2)

	// Agent -> Backend
	wg.Add(1)
	go func() {
		defer wg.Done()
		n, err := io.Copy(b.backendChannel, b.agentChannel)
		b.mu.Lock()
		b.bytesSent += n
		b.mu.Unlock()

		if err != nil && err != io.EOF {
			slog.Debug("agent->backend copy error", "error", err)
			errCh <- err
		}

		// Signal EOF to backend
		if err := b.backendChannel.CloseWrite(); err != nil {
			slog.Debug("agent->backend: CloseWrite error", "error", err)
		}
	}()

	// Backend -> Agent
	wg.Add(1)
	go func() {
		defer wg.Done()
		n, err := io.Copy(b.agentChannel, b.backendChannel)
		b.mu.Lock()
		b.bytesReceived += n
		b.mu.Unlock()

		if err != nil && err != io.EOF {
			slog.Debug("backend->agent copy error", "error", err)
			errCh <- err
		}

		// Signal EOF to agent
		if err := b.agentChannel.CloseWrite(); err != nil {
			slog.Debug("backend->agent: CloseWrite error", "error", err)
		}
	}()

	// Wait for both directions to complete
	wg.Wait()
	close(errCh)

	// Return first error if any
	for err := range errCh {
		if err != nil {
			return err
		}
	}

	return nil
}

// Close closes both channels.
func (b *Bridge) Close() {
	b.mu.Lock()
	defer b.mu.Unlock()

	if b.closed {
		return
	}

	b.closed = true
	b.agentChannel.Close()
	b.backendChannel.Close()
}

// Stats returns the bytes sent and received.
func (b *Bridge) Stats() (sent, received int64) {
	b.mu.Lock()
	defer b.mu.Unlock()
	return b.bytesSent, b.bytesReceived
}

// ForwardRequests forwards global requests from agent to backend.
func ForwardRequests(agentReqs <-chan *ssh.Request, backendConn *ssh.Conn) {
	for req := range agentReqs {
		// Forward request to backend
		ok, payload, err := (*backendConn).SendRequest(req.Type, req.WantReply, req.Payload)
		if err != nil {
			slog.Debug("failed to forward request", "type", req.Type, "error", err)
			if req.WantReply {
				_ = req.Reply(false, nil)
			}
			continue
		}

		if req.WantReply {
			_ = req.Reply(ok, payload)
		}
	}
}

// ForwardChannelRequests forwards channel-specific requests.
func ForwardChannelRequests(src <-chan *ssh.Request, dst ssh.Channel) {
	for req := range src {
		ok, err := dst.SendRequest(req.Type, req.WantReply, req.Payload)
		if err != nil {
			slog.Debug("failed to forward channel request", "type", req.Type, "error", err)
			if req.WantReply {
				_ = req.Reply(false, nil)
			}
			continue
		}

		if req.WantReply {
			_ = req.Reply(ok, nil)
		}
	}
}
