package main

import "strings"

// upstreamPath returns the path the upstream receives for reqPath: a leading
// "/"+serviceID is removed and the result starts with "/" (exactly the
// directors' rule before this change).
func upstreamPath(reqPath, serviceID string) string {
	stripped := strings.TrimPrefix(reqPath, "/"+serviceID)
	if stripped == reqPath {
		return reqPath
	}
	if stripped == "" || stripped[0] != '/' {
		stripped = "/" + stripped
	}
	return stripped
}
