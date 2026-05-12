/**
 * MCP Connect snippet generator.
 *
 * Generates the JSON config snippet shown in the Agent "Connect" panel.
 * The snippet guides the operator to configure their AI agent to connect to
 * Mintkey's MCP server.
 *
 * Source: ADMIN_UI_SPEC.md §2.5; T-1.4.3; ADR-0009.
 */

export interface McpConnectOptions {
  agentId: string;
  mcpEndpoint: string;
  /** Hint for display only — never the actual key value. */
  apiKeyHint?: string;
}

/**
 * Returns a JSON string containing the MCP server configuration snippet
 * for the given agent. The snippet uses a placeholder instead of the actual
 * API key to avoid any plaintext leakage in the UI.
 */
export function getMcpConnectSnippet(opts: McpConnectOptions): string {
  const config = {
    mcpServers: {
      mintkey: {
        url: opts.mcpEndpoint,
        headers: {
          Authorization: "Bearer <your_api_key>",
        },
        env: {
          MINTKEY_AGENT_ID: opts.agentId,
        },
      },
    },
  };
  return JSON.stringify(config, null, 2);
}
