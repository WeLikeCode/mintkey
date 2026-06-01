package bridge

import (
	"encoding/binary"
	"errors"
	"log/slog"

	"golang.org/x/crypto/ssh"
)

// ErrInvalidPayload indicates an invalid payload format.
var ErrInvalidPayload = errors.New("invalid payload")

// SignalRequest represents a signal request from the agent.
type SignalRequest struct {
	Signal string
}

// ParseSignalRequest parses a signal request payload.
func ParseSignalRequest(payload []byte) (*SignalRequest, error) {
	if len(payload) < 4 {
		return nil, ErrInvalidPayload
	}

	sigLen := binary.BigEndian.Uint32(payload[0:4])
	if len(payload) < int(4+sigLen) {
		return nil, ErrInvalidPayload
	}

	return &SignalRequest{
		Signal: string(payload[4 : 4+sigLen]),
	}, nil
}

// ForwardSignal forwards a signal request to the backend.
func ForwardSignal(backendChannel ssh.Channel, sig string) error {
	sigBytes := []byte(sig)
	payload := make([]byte, 4+len(sigBytes))
	binary.BigEndian.PutUint32(payload[0:4], uint32(len(sigBytes)))
	copy(payload[4:], sigBytes)

	_, err := backendChannel.SendRequest("signal", false, payload)
	if err != nil {
		slog.Debug("failed to forward signal", "signal", sig, "error", err)
		return err
	}

	slog.Debug("forwarded signal", "signal", sig)
	return nil
}

// ExitStatusRequest represents an exit-status request.
type ExitStatusRequest struct {
	ExitStatus uint32
}

// ParseExitStatusRequest parses an exit-status request payload.
func ParseExitStatusRequest(payload []byte) (*ExitStatusRequest, error) {
	if len(payload) < 4 {
		return nil, ErrInvalidPayload
	}

	return &ExitStatusRequest{
		ExitStatus: binary.BigEndian.Uint32(payload[0:4]),
	}, nil
}

// ForwardExitStatus forwards an exit-status request to the agent.
func ForwardExitStatus(agentChannel ssh.Channel, exitStatus uint32) error {
	payload := make([]byte, 4)
	binary.BigEndian.PutUint32(payload[0:4], exitStatus)

	_, err := agentChannel.SendRequest("exit-status", false, payload)
	if err != nil {
		slog.Debug("failed to forward exit status", "exit_status", exitStatus, "error", err)
		return err
	}

	slog.Debug("forwarded exit status", "exit_status", exitStatus)
	return nil
}

// ExitSignalRequest represents an exit-signal request.
type ExitSignalRequest struct {
	Signal     string
	CoreDumped bool
	ErrMsg     string
	Lang       string
}

// ParseExitSignalRequest parses an exit-signal request payload.
func ParseExitSignalRequest(payload []byte) (*ExitSignalRequest, error) {
	if len(payload) < 4 {
		return nil, ErrInvalidPayload
	}

	req := &ExitSignalRequest{}
	offset := 0

	// Signal name
	sigLen := binary.BigEndian.Uint32(payload[offset : offset+4])
	offset += 4
	if len(payload) < offset+int(sigLen)+1 {
		return nil, ErrInvalidPayload
	}
	req.Signal = string(payload[offset : offset+int(sigLen)])
	offset += int(sigLen)

	// Core dumped flag
	if payload[offset] != 0 {
		req.CoreDumped = true
	}
	offset++

	// Error message
	if offset+4 > len(payload) {
		return req, nil
	}
	errLen := binary.BigEndian.Uint32(payload[offset : offset+4])
	offset += 4
	if len(payload) < offset+int(errLen)+4 {
		return req, nil
	}
	req.ErrMsg = string(payload[offset : offset+int(errLen)])
	offset += int(errLen)

	// Language tag
	langLen := binary.BigEndian.Uint32(payload[offset : offset+4])
	offset += 4
	if len(payload) < offset+int(langLen) {
		return req, nil
	}
	req.Lang = string(payload[offset : offset+int(langLen)])

	return req, nil
}

// ForwardExitSignal forwards an exit-signal request to the agent.
func ForwardExitSignal(agentChannel ssh.Channel, req *ExitSignalRequest) error {
	sigBytes := []byte(req.Signal)
	errBytes := []byte(req.ErrMsg)
	langBytes := []byte(req.Lang)

	payload := make([]byte, 4+len(sigBytes)+1+4+len(errBytes)+4+len(langBytes))
	offset := 0

	binary.BigEndian.PutUint32(payload[offset:offset+4], uint32(len(sigBytes)))
	offset += 4
	copy(payload[offset:], sigBytes)
	offset += len(sigBytes)

	if req.CoreDumped {
		payload[offset] = 1
	} else {
		payload[offset] = 0
	}
	offset++

	binary.BigEndian.PutUint32(payload[offset:offset+4], uint32(len(errBytes)))
	offset += 4
	copy(payload[offset:], errBytes)
	offset += len(errBytes)

	binary.BigEndian.PutUint32(payload[offset:offset+4], uint32(len(langBytes)))
	offset += 4
	copy(payload[offset:], langBytes)

	_, err := agentChannel.SendRequest("exit-signal", false, payload)
	if err != nil {
		slog.Debug("failed to forward exit signal", "signal", req.Signal, "error", err)
		return err
	}

	slog.Debug("forwarded exit signal", "signal", req.Signal)
	return nil
}
