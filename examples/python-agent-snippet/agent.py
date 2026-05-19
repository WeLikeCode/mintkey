"""
Mintkey Python agent snippet.

Demonstrates:
  1. Authenticate with a Mintkey agent API key.
  2. Request a short-lived brokered JWT from the MCP server.
  3. Call a backend service through the Mintkey egress proxy.

Prerequisites:
  - Mintkey stack running (make demo)
  - Agent created in admin UI; API key exported as MINTKEY_AGENT_KEY
  - Service registered and permission grant created for the agent
  - pip install httpx>=0.27,<0.28

Usage:
  MINTKEY_AGENT_KEY=mk_agent_YOUR_AGENT_KEY_HERE \\
  MINTKEY_SVC_ID=svc_01HXXXX \\
  python3 agent.py
"""

import os
import sys
import httpx

# ── Configuration (read from environment) ────────────────────────────────────

AGENT_KEY = os.environ.get("MINTKEY_AGENT_KEY", "")
SVC_ID = os.environ.get("MINTKEY_SVC_ID", "")

MCP_URL = os.environ.get("MINTKEY_MCP_URL", "http://localhost:8082")
PROXY_URL = os.environ.get("MINTKEY_PROXY_URL", "http://localhost:8000")

if not AGENT_KEY:
    print("ERROR: MINTKEY_AGENT_KEY is not set.", file=sys.stderr)
    print("  export MINTKEY_AGENT_KEY=mk_agent_YOUR_AGENT_KEY_HERE", file=sys.stderr)
    sys.exit(1)

if not SVC_ID:
    print("ERROR: MINTKEY_SVC_ID is not set.", file=sys.stderr)
    print("  export MINTKEY_SVC_ID=svc_01HXXXX", file=sys.stderr)
    sys.exit(1)

# ── Step 1: Request a brokered JWT ───────────────────────────────────────────

print(f"[1] Requesting brokered JWT from {MCP_URL}/v1/tools/request_token ...")

with httpx.Client(timeout=10.0) as client:
    token_resp = client.post(
        f"{MCP_URL}/v1/tools/request_token",
        headers={"Authorization": f"Bearer {AGENT_KEY}"},
        json={"service_id": SVC_ID, "action": "call"},
    )
    token_resp.raise_for_status()

token_data = token_resp.json()
brokered_jwt = token_data["token"]
expires_at = token_data.get("expires_at", "unknown")

# Redact the JWT in output — show only the algorithm header prefix
jwt_preview = brokered_jwt[:12] + "..." if len(brokered_jwt) > 12 else "<short>"
print(f"    JWT received: {jwt_preview}  expires_at={expires_at}")
print("    (real backend credential NOT present in this response)")

# ── Step 2: Call the backend through the egress proxy ───────────────────────

proxy_path = f"{PROXY_URL}/v1/call/{SVC_ID}/echo"
print(f"\n[2] Calling backend through proxy: POST {proxy_path} ...")

with httpx.Client(timeout=10.0) as client:
    proxy_resp = client.post(
        proxy_path,
        headers={"Authorization": f"Bearer {brokered_jwt}"},
        json={"hello": "mintkey-python-snippet"},
    )
    proxy_resp.raise_for_status()

echo_data = proxy_resp.json()

# ── Step 3: Print redacted summary ──────────────────────────────────────────

injected_key = (
    echo_data.get("headers", {}).get("x-api-key")
    or echo_data.get("headers", {}).get("X-Api-Key")
    or "<not visible in echo>"
)

print("\n[3] Result summary:")
print(f"    HTTP status    : {proxy_resp.status_code}")
print(f"    Agent sent     : Authorization: Bearer {jwt_preview}")
print(f"    Backend received x-api-key: {'<REDACTED>' if injected_key != '<not visible in echo>' else injected_key}")
print(f"    Echo body      : {echo_data.get('body', echo_data)}")
print()
print("SUCCESS — the agent held only a short-lived JWT;")
print("          the real credential was injected by the Mintkey proxy.")
