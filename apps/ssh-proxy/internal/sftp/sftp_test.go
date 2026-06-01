package sftp

import (
	"encoding/binary"
	"testing"
)

func TestParsePacket(t *testing.T) {
	tests := []struct {
		name    string
		data    []byte
		want    *Packet
		wantErr bool
	}{
		{
			name: "valid INIT packet",
			data: func() []byte {
				// Length: 5 (1 byte type + 4 bytes version)
				// Type: SSH_FXP_INIT (1)
				// Version: 3
				data := make([]byte, 9)
				binary.BigEndian.PutUint32(data[0:4], 5)
				data[4] = SSH_FXP_INIT
				binary.BigEndian.PutUint32(data[5:9], 3)
				return data
			}(),
			want: &Packet{
				Type: SSH_FXP_INIT,
				ID:   3, // Version is parsed as ID
			},
			wantErr: false,
		},
		{
			name: "packet too short",
			data: []byte{0, 0, 0},
			wantErr: true,
		},
		{
			name: "packet length mismatch",
			data: func() []byte {
				data := make([]byte, 5)
				binary.BigEndian.PutUint32(data[0:4], 100) // Claims 100 bytes but only has 1
				data[4] = SSH_FXP_INIT
				return data
			}(),
			wantErr: true,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got, err := ParsePacket(tt.data)
			if (err != nil) != tt.wantErr {
				t.Errorf("ParsePacket() error = %v, wantErr %v", err, tt.wantErr)
				return
			}
			if !tt.wantErr {
				if got.Type != tt.want.Type {
					t.Errorf("Type = %d, want %d", got.Type, tt.want.Type)
				}
			}
		})
	}
}

func TestParseOperation(t *testing.T) {
	tests := []struct {
		name    string
		packet  *Packet
		want    *Operation
		wantErr bool
	}{
		{
			name: "OPEN operation",
			packet: &Packet{
				Type: SSH_FXP_OPEN,
				Payload: func() []byte {
					path := "/etc/passwd"
					payload := make([]byte, 4+len(path)+4)
					binary.BigEndian.PutUint32(payload[0:4], uint32(len(path)))
					copy(payload[4:], path)
					binary.BigEndian.PutUint32(payload[4+len(path):], 0) // flags
					return payload
				}(),
			},
			want: &Operation{
				Type: "read",
				Path: "/etc/passwd",
			},
			wantErr: false,
		},
		{
			name: "OPEN operation with write flag",
			packet: &Packet{
				Type: SSH_FXP_OPEN,
				Payload: func() []byte {
					path := "/tmp/file.txt"
					payload := make([]byte, 4+len(path)+4)
					binary.BigEndian.PutUint32(payload[0:4], uint32(len(path)))
					copy(payload[4:], path)
					binary.BigEndian.PutUint32(payload[4+len(path):], 0x0002) // SSH_FXF_WRITE
					return payload
				}(),
			},
			want: &Operation{
				Type: "write",
				Path: "/tmp/file.txt",
			},
			wantErr: false,
		},
		{
			name: "REMOVE operation",
			packet: &Packet{
				Type: SSH_FXP_REMOVE,
				Payload: func() []byte {
					path := "/tmp/old.txt"
					payload := make([]byte, 4+len(path))
					binary.BigEndian.PutUint32(payload[0:4], uint32(len(path)))
					copy(payload[4:], path)
					return payload
				}(),
			},
			want: &Operation{
				Type: "delete",
				Path: "/tmp/old.txt",
			},
			wantErr: false,
		},
		{
			name: "MKDIR operation",
			packet: &Packet{
				Type: SSH_FXP_MKDIR,
				Payload: func() []byte {
					path := "/tmp/newdir"
					payload := make([]byte, 4+len(path))
					binary.BigEndian.PutUint32(payload[0:4], uint32(len(path)))
					copy(payload[4:], path)
					return payload
				}(),
			},
			want: &Operation{
				Type: "mkdir",
				Path: "/tmp/newdir",
			},
			wantErr: false,
		},
		{
			name: "RMDIR operation",
			packet: &Packet{
				Type: SSH_FXP_RMDIR,
				Payload: func() []byte {
					path := "/tmp/olddir"
					payload := make([]byte, 4+len(path))
					binary.BigEndian.PutUint32(payload[0:4], uint32(len(path)))
					copy(payload[4:], path)
					return payload
				}(),
			},
			want: &Operation{
				Type: "rmdir",
				Path: "/tmp/olddir",
			},
			wantErr: false,
		},
		{
			name: "RENAME operation",
			packet: &Packet{
				Type: SSH_FXP_RENAME,
				Payload: func() []byte {
					oldPath := "/tmp/old.txt"
					newPath := "/tmp/new.txt"
					payload := make([]byte, 4+len(oldPath)+4+len(newPath))
					binary.BigEndian.PutUint32(payload[0:4], uint32(len(oldPath)))
					copy(payload[4:], oldPath)
					binary.BigEndian.PutUint32(payload[4+len(oldPath):], uint32(len(newPath)))
					copy(payload[4+len(oldPath)+4:], newPath)
					return payload
				}(),
			},
			want: &Operation{
				Type: "rename",
				Path: "/tmp/old.txt",
			},
			wantErr: false,
		},
		{
			name: "unknown operation",
			packet: &Packet{
				Type:    255,
				Payload: []byte{},
			},
			want: &Operation{
				Type: "unknown",
			},
			wantErr: false,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got, err := ParseOperation(tt.packet)
			if (err != nil) != tt.wantErr {
				t.Errorf("ParseOperation() error = %v, wantErr %v", err, tt.wantErr)
				return
			}
			if !tt.wantErr {
				if got.Type != tt.want.Type {
					t.Errorf("Type = %q, want %q", got.Type, tt.want.Type)
				}
				if got.Path != tt.want.Path {
					t.Errorf("Path = %q, want %q", got.Path, tt.want.Path)
				}
			}
		})
	}
}

func TestExtractString(t *testing.T) {
	tests := []struct {
		name    string
		data    []byte
		want    string
		wantErr bool
	}{
		{
			name: "valid string",
			data: func() []byte {
				s := "hello"
				data := make([]byte, 4+len(s))
				binary.BigEndian.PutUint32(data[0:4], uint32(len(s)))
				copy(data[4:], s)
				return data
			}(),
			want:    "hello",
			wantErr: false,
		},
		{
			name:    "data too short",
			data:    []byte{0, 0},
			wantErr: true,
		},
		{
			name: "string length mismatch",
			data: func() []byte {
				data := make([]byte, 5)
				binary.BigEndian.PutUint32(data[0:4], 100) // Claims 100 bytes
				data[4] = 'a'
				return data
			}(),
			wantErr: true,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got, err := extractString(tt.data)
			if (err != nil) != tt.wantErr {
				t.Errorf("extractString() error = %v, wantErr %v", err, tt.wantErr)
				return
			}
			if !tt.wantErr && got != tt.want {
				t.Errorf("extractString() = %q, want %q", got, tt.want)
			}
		})
	}
}

func TestSFTPConstants(t *testing.T) {
	// Verify SFTP packet type constants
	if SSH_FXP_INIT != 1 {
		t.Errorf("SSH_FXP_INIT = %d, want 1", SSH_FXP_INIT)
	}

	if SSH_FXP_OPEN != 3 {
		t.Errorf("SSH_FXP_OPEN = %d, want 3", SSH_FXP_OPEN)
	}

	if SSH_FXP_CLOSE != 4 {
		t.Errorf("SSH_FXP_CLOSE = %d, want 4", SSH_FXP_CLOSE)
	}

	if SSH_FXP_READ != 5 {
		t.Errorf("SSH_FXP_READ = %d, want 5", SSH_FXP_READ)
	}

	if SSH_FXP_WRITE != 6 {
		t.Errorf("SSH_FXP_WRITE = %d, want 6", SSH_FXP_WRITE)
	}

	if SSH_FXP_REMOVE != 13 {
		t.Errorf("SSH_FXP_REMOVE = %d, want 13", SSH_FXP_REMOVE)
	}

	if SSH_FXP_MKDIR != 14 {
		t.Errorf("SSH_FXP_MKDIR = %d, want 14", SSH_FXP_MKDIR)
	}

	if SSH_FXP_RMDIR != 15 {
		t.Errorf("SSH_FXP_RMDIR = %d, want 15", SSH_FXP_RMDIR)
	}

	if SSH_FXP_RENAME != 18 {
		t.Errorf("SSH_FXP_RENAME = %d, want 18", SSH_FXP_RENAME)
	}
}
