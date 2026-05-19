/**
 * Mintkey TypeScript agent snippet.
 *
 * Demonstrates:
 *   1. Authenticate with a Mintkey agent API key.
 *   2. Request a short-lived brokered JWT from the MCP server.
 *   3. Call a backend service through the Mintkey egress proxy.
 *
 * Prerequisites:
 *   - Mintkey stack running (make demo)
 *   - Agent created in admin UI; API key set as MINTKEY_AGENT_KEY env var
 *   - Service registered and permission grant created for the agent
 *   - Node 18+ (native fetch)
 *
 * Usage:
 *   MINTKEY_AGENT_KEY=mk_agent_YOUR_AGENT_KEY_HERE \
 *   MINTKEY_SVC_ID=svc_01HXXXX \
 *   pnpm start
 */

// ── Configuration (read from environment) ────────────────────────────────────

const AGENT_KEY: string = process.env.MINTKEY_AGENT_KEY ?? "";
const SVC_ID: string = process.env.MINTKEY_SVC_ID ?? "";

const MCP_URL: string = process.env.MINTKEY_MCP_URL ?? "http://localhost:8082";
const PROXY_URL: string = process.env.MINTKEY_PROXY_URL ?? "http://localhost:8000";

if (!AGENT_KEY) {
  console.error("ERROR: MINTKEY_AGENT_KEY is not set.");
  console.error("  export MINTKEY_AGENT_KEY=mk_agent_YOUR_AGENT_KEY_HERE");
  process.exit(1);
}

if (!SVC_ID) {
  console.error("ERROR: MINTKEY_SVC_ID is not set.");
  console.error("  export MINTKEY_SVC_ID=svc_01HXXXX");
  process.exit(1);
}

// ── Types ────────────────────────────────────────────────────────────────────

interface TokenResponse {
  token: string;
  expires_at: string;
  service_id: string;
  action: string;
}

interface EchoResponse {
  method?: string;
  path?: string;
  headers?: Record<string, string>;
  body?: unknown;
}

// ── Step 1: Request a brokered JWT ───────────────────────────────────────────

async function requestBrokeredJwt(): Promise<string> {
  console.log(`[1] Requesting brokered JWT from ${MCP_URL}/v1/tools/request_token ...`);

  const resp = await fetch(`${MCP_URL}/v1/tools/request_token`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${AGENT_KEY}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ service_id: SVC_ID, action: "call" }),
  });

  if (!resp.ok) {
    const text = await resp.text();
    throw new Error(`Token request failed (${resp.status}): ${text}`);
  }

  const data = (await resp.json()) as TokenResponse;
  const jwtPreview = data.token.slice(0, 12) + "...";
  console.log(`    JWT received: ${jwtPreview}  expires_at=${data.expires_at}`);
  console.log("    (real backend credential NOT present in this response)");

  return data.token;
}

// ── Step 2: Call the backend through the egress proxy ───────────────────────

async function callThroughProxy(brokeredJwt: string): Promise<EchoResponse> {
  const proxyPath = `${PROXY_URL}/v1/call/${SVC_ID}/echo`;
  console.log(`\n[2] Calling backend through proxy: POST ${proxyPath} ...`);

  const resp = await fetch(proxyPath, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${brokeredJwt}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ hello: "mintkey-typescript-snippet" }),
  });

  if (!resp.ok) {
    const text = await resp.text();
    throw new Error(`Proxy call failed (${resp.status}): ${text}`);
  }

  return (await resp.json()) as EchoResponse;
}

// ── Step 3: Print redacted summary ──────────────────────────────────────────

function printSummary(brokeredJwt: string, echoData: EchoResponse): void {
  const headers = echoData.headers ?? {};
  const injectedKey =
    headers["x-api-key"] ?? headers["X-Api-Key"] ?? "<not visible in echo>";

  const jwtPreview = brokeredJwt.slice(0, 12) + "...";

  console.log("\n[3] Result summary:");
  console.log(`    Agent sent     : Authorization: Bearer ${jwtPreview}`);
  console.log(
    `    Backend received x-api-key: ${injectedKey !== "<not visible in echo>" ? "<REDACTED>" : injectedKey}`
  );
  console.log(`    Echo body      : ${JSON.stringify(echoData.body ?? echoData)}`);
  console.log();
  console.log("SUCCESS — the agent held only a short-lived JWT;");
  console.log("          the real credential was injected by the Mintkey proxy.");
}

// ── Main ─────────────────────────────────────────────────────────────────────

async function main(): Promise<void> {
  const brokeredJwt = await requestBrokeredJwt();
  const echoData = await callThroughProxy(brokeredJwt);
  printSummary(brokeredJwt, echoData);
}

main().catch((err: unknown) => {
  console.error("ERROR:", err instanceof Error ? err.message : String(err));
  process.exit(1);
});
