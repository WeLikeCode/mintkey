package main

import (
	"strings"

	"github.com/mintkey/mintkey/services/proxy-plugin/internal/wireid"
)

// addressedServiceID returns the service a request addresses: serviceHeader
// when it is not empty; else, for a path starting with "/v1/call/", the
// segment after it (any form, possibly ""); else urlServiceID(reqPath).
func addressedServiceID(reqPath, serviceHeader string) string {
	if serviceHeader != "" {
		return serviceHeader
	}
	if rest, ok := strings.CutPrefix(reqPath, "/v1/call/"); ok {
		if i := strings.IndexByte(rest, '/'); i >= 0 {
			return rest[:i]
		}
		return rest
	}
	return urlServiceID(reqPath)
}

// upstreamPath returns the path the upstream receives for reqPath, the request
// path as the proxy received it:
//
//	"/v1/call/<seg>[/<rest>]" -> "/<rest>" when wireid.Canonical(seg, "svc_") ==
//	                             wireid.Canonical(serviceID, "svc_")
//	                             ("/" when there is no rest)
//	otherwise the rule before this change: a leading "/"+serviceID is removed
//	and the result starts with "/".
func upstreamPath(reqPath, serviceID string) string {
	const callPrefix = "/v1/call/"
	if rest, ok := strings.CutPrefix(reqPath, callPrefix); ok {
		seg := rest
		tail := ""
		if i := strings.IndexByte(rest, '/'); i >= 0 {
			seg = rest[:i]
			tail = rest[i:]
		}
		if wireid.Canonical(seg, "svc_") == wireid.Canonical(serviceID, "svc_") {
			if tail == "" {
				return "/"
			}
			return tail
		}
	}

	stripped := strings.TrimPrefix(reqPath, "/"+serviceID)
	if stripped == reqPath {
		return reqPath
	}
	if stripped == "" || stripped[0] != '/' {
		stripped = "/" + stripped
	}
	return stripped
}
