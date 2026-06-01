package sftp

import (
	"context"
	"io"
	"log/slog"

	"github.com/WeLikeCode/mintkey/apps/ssh-proxy/internal/audit"
	"github.com/WeLikeCode/mintkey/apps/ssh-proxy/internal/session"
	"golang.org/x/crypto/ssh"
)

// SessionHandler handles an SFTP session with audit logging.
type SessionHandler struct {
	handler     *Handler
	auditEmitter *audit.Emitter
	sessCtx     *session.SessionContext
	sessionID   string
}

// NewSessionHandler creates a new SFTP session handler.
func NewSessionHandler(handler *Handler, auditEmitter *audit.Emitter, sessCtx *session.SessionContext, sessionID string) *SessionHandler {
	return &SessionHandler{
		handler:      handler,
		auditEmitter: auditEmitter,
		sessCtx:      sessCtx,
		sessionID:    sessionID,
	}
}

// Run runs the SFTP session, forwarding packets and logging operations.
func (sh *SessionHandler) Run(ctx context.Context) error {
	// Create channels for bidirectional forwarding
	done := make(chan error, 2)

	// Agent -> Backend
	go func() {
		done <- sh.forwardWithAudit(ctx, sh.handler.agentChannel, sh.handler.backendChannel, "agent->backend")
	}()

	// Backend -> Agent
	go func() {
		done <- sh.forward(sh.handler.backendChannel, sh.handler.agentChannel, "backend->agent")
	}()

	// Wait for first error or completion
	err := <-done

	// Close channels to stop the other goroutine
	sh.handler.agentChannel.Close()
	sh.handler.backendChannel.Close()

	// Wait for other goroutine
	<-done

	return err
}

func (sh *SessionHandler) forwardWithAudit(ctx context.Context, src, dst ssh.Channel, direction string) error {
	buf := make([]byte, 32*1024)

	for {
		n, err := src.Read(buf)
		if n > 0 {
			// Try to parse as SFTP packet
			if packet, parseErr := ParsePacket(buf[:n]); parseErr == nil {
				// Extract operation
				if op, opErr := ParseOperation(packet); opErr == nil && op.Path != "" {
					// Emit audit event
					if auditErr := sh.auditEmitter.EmitSessionSFTP(ctx, sh.sessCtx, sh.sessionID, op.Type, op.Path); auditErr != nil {
						slog.Debug("failed to emit SFTP audit event", "error", auditErr)
					}
				}
			}

			// Forward to destination
			if _, writeErr := dst.Write(buf[:n]); writeErr != nil {
				return writeErr
			}
		}

		if err != nil {
			if err == io.EOF {
				return nil
			}
			return err
		}
	}
}

func (sh *SessionHandler) forward(src, dst ssh.Channel, direction string) error {
	buf := make([]byte, 32*1024)

	for {
		n, err := src.Read(buf)
		if n > 0 {
			if _, writeErr := dst.Write(buf[:n]); writeErr != nil {
				return writeErr
			}
		}

		if err != nil {
			if err == io.EOF {
				return nil
			}
			return err
		}
	}
}
