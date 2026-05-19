"""
Mintkey OpenAI-compatible agent snippet.

Demonstrates calling an OpenAI-compatible endpoint through the Mintkey proxy
using the standard `openai` Python SDK.

The trick: set `api_key` to the brokered JWT from the Mintkey MCP server, and
set `base_url` to the Mintkey egress proxy URL for this service.

The proxy strips the brokered JWT, looks up the real API key from the vault
adapter, and injects `Authorization: Bearer <real-key>` before forwarding the
request to the upstream service. The agent never holds the real API key.

For the demo, the upstream service is the local mock-backend in echo mode —
no real OpenAI key is required.

Prerequisites:
  - Mintkey stack running (make demo)
  - Service registered and agent granted (bash examples/openai-compatible/register-service.sh)
  - pip install openai httpx

Usage:
  MINTKEY_AGENT_KEY=mk_agent_YOUR_AGENT_KEY_HERE \\
  MINTKEY_SVC_ID=svc_01HXXXX \\
  python3 agent.py
"""

import os
import sys
import httpx
import openai

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

with httpx.Client(timeout=10.0) as http:
    token_resp = http.post(
        f"{MCP_URL}/v1/tools/request_token",
        headers={"Authorization": f"Bearer {AGENT_KEY}"},
        json={"service_id": SVC_ID, "action": "call"},
    )
    token_resp.raise_for_status()

token_data = token_resp.json()
brokered_jwt = token_data["token"]
expires_at = token_data.get("expires_at", "unknown")

jwt_preview = brokered_jwt[:12] + "..."
print(f"    JWT received: {jwt_preview}  expires_at={expires_at}")
print("    (real OpenAI API key NOT present in this response)")

# ── Step 2: Call through the proxy using the OpenAI SDK ──────────────────────
#
# Key insight: pass the brokered JWT as `api_key`.  The OpenAI SDK sends it as
#   Authorization: Bearer <brokered_jwt>
# The Mintkey proxy receives this, validates the JWT, looks up the real key
# from the vault adapter, then forwards the request with the real key injected.
# The agent never had access to the real key.

proxy_base_url = f"{PROXY_URL}/v1/call/{SVC_ID}"
print(f"\n[2] Calling chat.completions via OpenAI SDK (base_url={proxy_base_url}) ...")

client = openai.OpenAI(
    api_key=brokered_jwt,       # brokered JWT — NOT the real backend key
    base_url=proxy_base_url,
    http_client=httpx.Client(timeout=15.0),
)

completion = client.chat.completions.create(
    model="gpt-3.5-turbo",      # mock-backend echoes the request; model name is ignored
    messages=[
        {"role": "user", "content": "Hello from Mintkey!"},
    ],
    max_tokens=64,
)

# ── Step 3: Print redacted summary ──────────────────────────────────────────

print("\n[3] Result summary:")
print(f"    model          : {completion.model}")
if completion.choices:
    reply = completion.choices[0].message.content or "<empty>"
    print(f"    assistant reply: {reply[:120]}")
print(f"    usage          : {completion.usage}")
print()
print("SUCCESS — the agent held only a short-lived JWT;")
print("          the real API key was injected by the Mintkey proxy.")
print()
print("NOTE: The mock-backend echoes the request body rather than generating a real")
print("      completion. In production, replace the service with https://api.openai.com")
print("      and store your real sk-proj-* key via admin UI → Services → Credentials.")
