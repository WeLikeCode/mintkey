package main

import "strings"

const (
	refusalMethod = "method not permitted"
	refusalPath   = "path not permitted"
)

// checkScopeClaims returns "" when method and path are within the token's
// optional methods and path_prefix claims, else refusalMethod or refusalPath.
func checkScopeClaims(claims map[string]any, method, path string) string {
	if raw, ok := claims["methods"]; ok {
		methods, ok := raw.([]any)
		if !ok || len(methods) == 0 {
			return refusalMethod
		}
		permitted := false
		for _, entry := range methods {
			name, ok := entry.(string)
			if !ok {
				return refusalMethod
			}
			if name == method {
				permitted = true
			}
		}
		if !permitted {
			return refusalMethod
		}
	}

	if raw, ok := claims["path_prefix"]; ok {
		prefix, ok := raw.(string)
		if !ok || !strings.HasPrefix(prefix, "/") {
			return refusalPath
		}
		for _, segment := range strings.Split(path, "/") {
			if segment == "." || segment == ".." {
				return refusalPath
			}
		}
		if path != prefix && !strings.HasPrefix(path, strings.TrimSuffix(prefix, "/")+"/") {
			return refusalPath
		}
	}

	return ""
}
