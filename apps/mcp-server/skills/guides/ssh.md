# Guide: Using an SSH service through Mintkey

URI: `mintkey://guides/ssh` · also `mintkey_bootstrap(section="ssh")`

SSH services are handled by the **SSH bastion (a separate proxy binary, the
"ssh-proxy"), NOT the Kong HTTP proxy.** You connect with a normal SSH client.
You do NOT make HTTP calls and you do NOT send the JWT in an HTTP header — the
JWT is used as your SSH **password**.

## Detecting an SSH service
In `mintkey_discover` / `mintkey_list_services` / `mintkey_describe_service`,
an SSH service has `connect_type: "ssh"` and `auth_scheme` in
`{ssh_private_key, ssh_password, ssh_ca}`. Its `base_url` is the upstream host in
the form `ssh://host:port` (ADR-0023: `services.base_url` is the canonical
upstream host:port for SSH; the credential row holds only auth material —
private key / password / `ssh_user`). For an SSH service,
`mintkey_describe_service` also returns an `agent_connection_guide` block with
the exact bastion host/port and command template. There is NO
`explicit_proxy_url` you should use for SSH — Kong has no route for it.

## The flow

### Step 1 — Request a token (same tool as HTTP)
```json
{ "tool": "mintkey_request_token",
  "arguments": { "service_id": "svc_01HX...SSH", "action": "call" } }
```
For an SSH service the response includes an `ssh_connect` block alongside the
token (proxy_url is intentionally OMITTED — Kong is HTTP-only):
```json
{
  "token": "eyJhbGciOiJFZERTQS...",
  "ssh_connect": {
    "host": "ssh-proxy", "port": 2222,
    "external_host": "<bastion-host>", "external_port": 2222,
    "ssh_user": "<your_agent_id>",
    "auth_method": "password", "password_is_jwt": true,
    "hint": "ssh -p 2222 <agent_id>@<bastion-host> — use the token as the SSH password"
  },
  "expires_at": 1715000600,
  "service_id": "svc_01HX...SSH"
}
```
`ssh_connect.host=ssh-proxy`, `port=2222` are the in-Docker-network values;
`external_host`/`external_port` are what you use from outside the Docker
network (resolved from `MINTKEY_SSH_PROXY_PUBLIC_URL`, else derived from the MCP
public URL host, else falls back to host `ssh-proxy`:2222).

### Step 2 — Connect with your SSH client
SSH to `external_host:external_port` as user `ssh_connect.ssh_user` (your
`agent_<...>` id), and supply the **token as the password**.

Non-interactive (system SSH client + sshpass):
```bash
sshpass -p "$JWT" ssh -p 2222 \
  -o PreferredAuthentications=password \
  -o PubkeyAuthentication=no \
  -o StrictHostKeyChecking=accept-new \
  "$AGENT_ID@$BASTION_HOST" 'whoami'
```
Python (paramiko):
```python
import paramiko
c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(hostname=bastion_host, port=2222, username=agent_id,
          password=jwt, look_for_keys=False, allow_agent=False)
stdin, stdout, stderr = c.exec_command("uname -a")
print(stdout.read().decode())
```

## What the bastion does vs. what the broker does
- **Broker** (`request_token`): mints the JWS-Ed25519 JWT, audience-bound to the
  SSH service, ~10-minute TTL. The broker does NOT open the SSH connection.
- **SSH proxy / bastion**: accepts your SSH password-auth, validates the JWT
  against the broker JWKS, looks up the service's `base_url` for the real
  upstream host:port, fetches the stored SSH credential (private key / password /
  CA-signed cert) from the vault, and bridges your session to the real target.
  You never see the upstream SSH credential.

## Hard rules
- **Do NOT route SSH through Kong / the HTTP proxy (`:8000`)** — there is no
  route; it will not work. The bastion (`:2222`) is the only valid endpoint.
- **Do NOT send the JWT as an HTTP header for SSH** — it is the SSH password.
- **Do NOT store the JWT** — it expires in ~10 minutes. For a longer session,
  call `mintkey_request_token` again and reconnect before expiry.
- **The bastion rejects** agent forwarding (`-A`), X11 (`-X`), and local port
  forwarding (`-L`).
- **Do NOT send your own private key** — the bastion holds and uses the stored
  one. (`ssh_ca` is Phase 2: the bastion signs a short-lived certificate for you.)

## Anti-patterns
- Treating an SSH service like a REST service and trying to GET `base_url` over HTTP → it's an SSH endpoint; use an SSH client.
- Putting the JWT in `Authorization: Bearer` and HTTP-calling the proxy → SSH uses the JWT as the password to `:2222`.
- Hardcoding the bastion IP → read `ssh_connect.external_host/external_port` (or `agent_connection_guide`) from the token/describe response.
