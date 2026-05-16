/**
 * Resolver helpers for operator-facing public URLs (admin-ui side).
 *
 * Mirrors the precedence in admin-api and mcp-server.
 *
 * Precedence:
 *   MCP URL:   MINTKEY_MCP_PUBLIC_URL → MINTKEY_MCP_URL → http://localhost:8082
 *   Proxy URL: MINTKEY_PROXY_PUBLIC_URL → MINTKEY_PROXY_URL → http://localhost:8000
 *
 * Trailing slashes stripped. Legacy aliases logged once via stderr.
 *
 * Note: admin-ui's `process.env` is only meaningful server-side (at startup).
 * The React components receive these values through DashboardData / record params.
 *
 * See docs/NETWORK.md.
 */

const warned = new Set<string>();

function readWithFallback(canonical: string, legacyNames: string[], defaultUrl: string): string {
  const val = process.env[canonical];
  if (val) return stripTrailingSlash(val);
  for (const name of legacyNames) {
    const v = process.env[name];
    if (v) {
      if (!warned.has(name)) {
        warned.add(name);
        // eslint-disable-next-line no-console
        console.warn(
          `mintkey.public_url.legacy_env_var_used name=${name} canonical=${canonical}`,
        );
      }
      return stripTrailingSlash(v);
    }
  }
  return stripTrailingSlash(defaultUrl);
}

function stripTrailingSlash(s: string): string {
  return s.replace(/\/+$/, "");
}

export function resolveMcpPublicUrl(): string {
  return readWithFallback(
    "MINTKEY_MCP_PUBLIC_URL",
    ["MINTKEY_MCP_URL"],
    "http://localhost:8082",
  );
}

export function resolveProxyPublicUrl(): string {
  return readWithFallback(
    "MINTKEY_PROXY_PUBLIC_URL",
    ["MINTKEY_PROXY_URL"],
    "http://localhost:8000",
  );
}
