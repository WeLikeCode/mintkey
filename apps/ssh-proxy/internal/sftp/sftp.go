// Package sftp handles SFTP subsystem requests in SSH sessions.
package sftp

import (
	"encoding/binary"
	"errors"
	"fmt"
	"log/slog"

	"golang.org/x/crypto/ssh"
)

// SFTP packet types (from SFTP protocol v3)
const (
	SSH_FXP_INIT          = 1
	SSH_FXP_VERSION       = 2
	SSH_FXP_OPEN          = 3
	SSH_FXP_CLOSE         = 4
	SSH_FXP_READ          = 5
	SSH_FXP_WRITE         = 6
	SSH_FXP_LSTAT         = 7
	SSH_FXP_FSTAT         = 8
	SSH_FXP_SETSTAT       = 9
	SSH_FXP_FSETSTAT      = 10
	SSH_FXP_OPENDIR       = 11
	SSH_FXP_READDIR       = 12
	SSH_FXP_REMOVE        = 13
	SSH_FXP_MKDIR         = 14
	SSH_FXP_RMDIR         = 15
	SSH_FXP_REALPATH      = 16
	SSH_FXP_STAT          = 17
	SSH_FXP_RENAME        = 18
	SSH_FXP_READLINK      = 19
	SSH_FXP_SYMLINK       = 20
	SSH_FXP_STATUS        = 101
	SSH_FXP_HANDLE        = 102
	SSH_FXP_DATA          = 103
	SSH_FXP_NAME          = 104
	SSH_FXP_ATTRS         = 105
	SSH_FXP_EXTENDED      = 200
	SSH_FXP_EXTENDED_REPLY = 201
)

// Handler handles SFTP subsystem requests.
type Handler struct {
	agentChannel   ssh.Channel
	backendChannel ssh.Channel
}

// NewHandler creates a new SFTP handler.
func NewHandler(agentChannel, backendChannel ssh.Channel) *Handler {
	return &Handler{
		agentChannel:   agentChannel,
		backendChannel: backendChannel,
	}
}

// HandleSubsystemRequest handles an SFTP subsystem request.
func (h *Handler) HandleSubsystemRequest(req *ssh.Request) error {
	// Parse subsystem name
	if len(req.Payload) < 4 {
		return errors.New("invalid subsystem request payload")
	}

	nameLen := binary.BigEndian.Uint32(req.Payload[0:4])
	if len(req.Payload) < int(4+nameLen) {
		return errors.New("invalid subsystem name length")
	}

	subsystem := string(req.Payload[4 : 4+nameLen])

	if subsystem != "sftp" {
		slog.Debug("unknown subsystem", "name", subsystem)
		if req.WantReply {
			req.Reply(false, nil)
		}
		return fmt.Errorf("unknown subsystem: %s", subsystem)
	}

	slog.Debug("SFTP subsystem request received")

	// Forward to backend
	ok, err := h.backendChannel.SendRequest("subsystem", true, req.Payload)
	if err != nil {
		return fmt.Errorf("failed to forward subsystem request: %w", err)
	}

	if !ok {
		slog.Warn("backend rejected SFTP subsystem")
		if req.WantReply {
			req.Reply(false, nil)
		}
		return errors.New("backend rejected SFTP subsystem")
	}

	if req.WantReply {
		req.Reply(true, nil)
	}

	return nil
}

// Packet represents an SFTP packet.
type Packet struct {
	Type    byte
	ID      uint32
	Payload []byte
}

// ParsePacket parses an SFTP packet.
func ParsePacket(data []byte) (*Packet, error) {
	if len(data) < 5 {
		return nil, errors.New("packet too short")
	}

	length := binary.BigEndian.Uint32(data[0:4])
	if len(data) < int(4+length) {
		return nil, errors.New("packet length mismatch")
	}

	packet := &Packet{
		Type:    data[4],
		Payload: data[5 : 4+length],
	}

	// Extract ID if present (most packets have it)
	if len(packet.Payload) >= 4 {
		packet.ID = binary.BigEndian.Uint32(packet.Payload[0:4])
		packet.Payload = packet.Payload[4:]
	}

	return packet, nil
}

// Operation represents an SFTP operation.
type Operation struct {
	Type string
	Path string
}

// ParseOperation extracts the operation type and path from an SFTP packet.
func ParseOperation(packet *Packet) (*Operation, error) {
	op := &Operation{}

	switch packet.Type {
	case SSH_FXP_OPEN:
		op.Type = "read" // or "write" depending on flags
		path, err := extractString(packet.Payload)
		if err != nil {
			return nil, err
		}
		op.Path = path

		// Check flags to determine read vs write
		if len(packet.Payload) > len(path)+4 {
			flags := binary.BigEndian.Uint32(packet.Payload[len(path)+4 : len(path)+8])
			if flags&0x0002 != 0 { // SSH_FXF_WRITE
				op.Type = "write"
			}
		}

	case SSH_FXP_CLOSE:
		op.Type = "close"
		// Handle is in payload, not path

	case SSH_FXP_READ:
		op.Type = "read"
		// Handle is in payload, not path

	case SSH_FXP_WRITE:
		op.Type = "write"
		// Handle is in payload, not path

	case SSH_FXP_LSTAT, SSH_FXP_STAT:
		op.Type = "list"
		path, err := extractString(packet.Payload)
		if err != nil {
			return nil, err
		}
		op.Path = path

	case SSH_FXP_OPENDIR:
		op.Type = "list"
		path, err := extractString(packet.Payload)
		if err != nil {
			return nil, err
		}
		op.Path = path

	case SSH_FXP_READDIR:
		op.Type = "list"
		// Handle is in payload, not path

	case SSH_FXP_REMOVE:
		op.Type = "delete"
		path, err := extractString(packet.Payload)
		if err != nil {
			return nil, err
		}
		op.Path = path

	case SSH_FXP_MKDIR:
		op.Type = "mkdir"
		path, err := extractString(packet.Payload)
		if err != nil {
			return nil, err
		}
		op.Path = path

	case SSH_FXP_RMDIR:
		op.Type = "rmdir"
		path, err := extractString(packet.Payload)
		if err != nil {
			return nil, err
		}
		op.Path = path

	case SSH_FXP_RENAME:
		op.Type = "rename"
		oldPath, err := extractString(packet.Payload)
		if err != nil {
			return nil, err
		}
		op.Path = oldPath

	case SSH_FXP_REALPATH:
		op.Type = "list"
		path, err := extractString(packet.Payload)
		if err != nil {
			return nil, err
		}
		op.Path = path

	default:
		op.Type = "unknown"
	}

	return op, nil
}

func extractString(data []byte) (string, error) {
	if len(data) < 4 {
		return "", errors.New("string too short")
	}

	length := binary.BigEndian.Uint32(data[0:4])
	if len(data) < int(4+length) {
		return "", errors.New("string length mismatch")
	}

	return string(data[4 : 4+length]), nil
}
