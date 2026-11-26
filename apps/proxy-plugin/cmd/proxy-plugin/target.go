package main

import (
	"net/url"

	"github.com/mintkey/mintkey/services/proxy-plugin/internal/vault"
)

// resolveTarget returns the parsed target, or nil and the text of the 502
// answer. The target is the one stored with the credential and nothing else:
// the request header X-Mintkey-Target and config.Config.DefaultTarget do not
// take part. The target must parse, use the scheme http or https and have a
// host; a nil credResp or an empty target gives "bad gateway: no target URL
// stored for this credential" and any other failure "bad gateway: invalid
// target URL".
func resolveTarget(credResp *vault.GetCredentialResponse) (*url.URL, string) {
	if credResp == nil || credResp.TargetURL == "" {
		return nil, "bad gateway: no target URL stored for this credential"
	}

	target, err := url.Parse(credResp.TargetURL)
	if err != nil {
		return nil, "bad gateway: invalid target URL"
	}
	if target.Scheme != "http" && target.Scheme != "https" {
		return nil, "bad gateway: invalid target URL"
	}
	if target.Host == "" {
		return nil, "bad gateway: invalid target URL"
	}

	return target, ""
}
