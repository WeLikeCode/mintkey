package server

import (
	"fmt"
	"os"
	"strings"
)

// IdentitySpec describes one service identity the vault adapter registers at boot.
type IdentitySpec struct {
	IDVar                string   // variable holding the identity id
	DefaultID            string   // id used when IDVar's value is empty
	TokenVar             string   // variable holding the identity's token
	Scopes               []string // scopes the identity is registered with
	RequiredInProduction bool     // production refuses to start when TokenVar's value is empty
}

// BootIdentities lists the identities registered at boot, in registration order.
var BootIdentities = []IdentitySpec{
	{"MINTKEY_VAULT_PROXY_IDENTITY_ID", "svcid_proxy", "MINTKEY_VAULT_PROXY_TOKEN",
		[]string{"vault.read", "vault.put"}, true},
	{"MINTKEY_VAULT_ADMIN_IDENTITY_ID", "svcid_admin_api", "MINTKEY_VAULT_ADMIN_TOKEN",
		[]string{"vault.read", "vault.put", "vault.secret.put", "vault.secret.delete"}, true},
	{"MINTKEY_VAULT_SSH_PROXY_IDENTITY_ID", "svcid_ssh_proxy", "MINTKEY_VAULT_SSH_PROXY_TOKEN",
		[]string{"vault.read", "vault.put"}, false},
	{"MINTKEY_VAULT_EMAIL_PROXY_IDENTITY_ID", "svcid_email_proxy", "MINTKEY_VAULT_EMAIL_PROXY_TOKEN",
		[]string{"vault.read"}, false},
	{"MINTKEY_VAULT_MCP_IDENTITY_ID", "svcid_mcp", "MINTKEY_VAULT_MCP_TOKEN",
		[]string{"vault.secret.put", "vault.secret.read", "vault.secret.delete"}, false},
}

// resolvedIdentity holds one spec's id and token after reading the variables.
type resolvedIdentity struct {
	spec  IdentitySpec
	id    string
	token string
}

// RegisterBootIdentities registers the identities of BootIdentities on v, reading every variable through lookup.
// It returns the TokenVar of each identity left unregistered because its token is empty, in table order (nil when
// all five are registered).
func (v *VaultService) RegisterBootIdentities(env string, lookup func(name string) (string, error)) (unset []string, err error) {
	resolved := make([]resolvedIdentity, 0, len(BootIdentities))
	for _, spec := range BootIdentities {
		id, err := lookup(spec.IDVar)
		if err != nil {
			return nil, fmt.Errorf("read %s: %w", spec.IDVar, err)
		}
		token, err := lookup(spec.TokenVar)
		if err != nil {
			return nil, fmt.Errorf("read %s: %w", spec.TokenVar, err)
		}
		if id == "" {
			id = spec.DefaultID
		}
		resolved = append(resolved, resolvedIdentity{spec: spec, id: id, token: token})
	}

	if env == "production" {
		var missing []string
		for _, r := range resolved {
			if r.spec.RequiredInProduction && r.token == "" {
				missing = append(missing, r.spec.TokenVar)
			}
		}
		if len(missing) > 0 {
			return nil, fmt.Errorf("production requires these variables to be set: %s", strings.Join(missing, ", "))
		}
	}

	for _, r := range resolved {
		if r.token == "" {
			unset = append(unset, r.spec.TokenVar)
			continue
		}
		if err := v.RegisterServiceIdentity(r.id, []byte(r.token), r.spec.Scopes); err != nil {
			return nil, err
		}
	}

	return unset, nil
}

// RegisterBootIdentitiesFromEnv is RegisterBootIdentities with a lookup that returns os.Getenv(name), nil.
func (v *VaultService) RegisterBootIdentitiesFromEnv(env string) (unset []string, err error) {
	return v.RegisterBootIdentities(env, func(name string) (string, error) {
		return os.Getenv(name), nil
	})
}
