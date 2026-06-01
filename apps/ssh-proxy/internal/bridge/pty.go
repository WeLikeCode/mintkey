package bridge

import (
	"encoding/binary"
	"log/slog"

	"golang.org/x/crypto/ssh"
)

// PTYRequest represents a PTY request from the agent.
type PTYRequest struct {
	Term     string
	Width    uint32
	Height   uint32
	WidthPx  uint32
	HeightPx uint32
	Modes    string
}

// ParsePTYRequest parses a PTY request payload.
func ParsePTYRequest(payload []byte) (*PTYRequest, error) {
	if len(payload) < 13 {
		return nil, ErrInvalidPayload
	}

	req := &PTYRequest{}

	// Parse term string
	termLen := binary.BigEndian.Uint32(payload[0:4])
	if len(payload) < int(4+termLen+16) {
		return nil, ErrInvalidPayload
	}
	req.Term = string(payload[4 : 4+termLen])

	offset := 4 + termLen
	req.Width = binary.BigEndian.Uint32(payload[offset : offset+4])
	req.Height = binary.BigEndian.Uint32(payload[offset+4 : offset+8])
	req.WidthPx = binary.BigEndian.Uint32(payload[offset+8 : offset+12])
	req.HeightPx = binary.BigEndian.Uint32(payload[offset+12 : offset+16])

	offset += 16
	if offset < len(payload) {
		modesLen := binary.BigEndian.Uint32(payload[offset : offset+4])
		offset += 4
		if offset+int(modesLen) <= len(payload) {
			req.Modes = string(payload[offset : offset+int(modesLen)])
		}
	}

	return req, nil
}

// WindowChangeRequest represents a window size change request.
type WindowChangeRequest struct {
	Width    uint32
	Height   uint32
	WidthPx  uint32
	HeightPx uint32
}

// ParseWindowChangeRequest parses a window-change request payload.
func ParseWindowChangeRequest(payload []byte) (*WindowChangeRequest, error) {
	if len(payload) < 16 {
		return nil, ErrInvalidPayload
	}

	return &WindowChangeRequest{
		Width:    binary.BigEndian.Uint32(payload[0:4]),
		Height:   binary.BigEndian.Uint32(payload[4:8]),
		WidthPx:  binary.BigEndian.Uint32(payload[8:12]),
		HeightPx: binary.BigEndian.Uint32(payload[12:16]),
	}, nil
}

// ForwardPTYRequest forwards a PTY request to the backend.
func ForwardPTYRequest(backendChannel ssh.Channel, req *PTYRequest) error {
	// Encode PTY request
	payload := encodePTYRequest(req)

	ok, err := backendChannel.SendRequest("pty-req", true, payload)
	if err != nil {
		return err
	}

	if !ok {
		slog.Warn("backend rejected PTY request")
	}

	return nil
}

// ForwardWindowChange forwards a window-change request to the backend.
func ForwardWindowChange(backendChannel ssh.Channel, req *WindowChangeRequest) error {
	payload := make([]byte, 16)
	binary.BigEndian.PutUint32(payload[0:4], req.Width)
	binary.BigEndian.PutUint32(payload[4:8], req.Height)
	binary.BigEndian.PutUint32(payload[8:12], req.WidthPx)
	binary.BigEndian.PutUint32(payload[12:16], req.HeightPx)

	_, err := backendChannel.SendRequest("window-change", false, payload)
	return err
}

func encodePTYRequest(req *PTYRequest) []byte {
	termBytes := []byte(req.Term)
	modesBytes := []byte(req.Modes)

	payload := make([]byte, 4+len(termBytes)+16+4+len(modesBytes))

	offset := 0
	binary.BigEndian.PutUint32(payload[offset:offset+4], uint32(len(termBytes)))
	offset += 4
	copy(payload[offset:], termBytes)
	offset += len(termBytes)

	binary.BigEndian.PutUint32(payload[offset:offset+4], req.Width)
	binary.BigEndian.PutUint32(payload[offset+4:offset+8], req.Height)
	binary.BigEndian.PutUint32(payload[offset+8:offset+12], req.WidthPx)
	binary.BigEndian.PutUint32(payload[offset+12:offset+16], req.HeightPx)
	offset += 16

	binary.BigEndian.PutUint32(payload[offset:offset+4], uint32(len(modesBytes)))
	offset += 4
	copy(payload[offset:], modesBytes)

	return payload
}
