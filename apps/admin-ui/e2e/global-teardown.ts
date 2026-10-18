/**
 * Global teardown -- delete the entities the fixtures created, via admin-api.
 *
 * fixtures/test-data.ts persists every created entity to e2e/.cleanup.ndjson (see
 * fixtures/cleanup.ts); here they are deleted in reverse order with the OIDC session that
 * global-setup saved in state.json (mintkey_session + csrf_token). Best effort: a service that
 * already has a credential cannot be hard-deleted (FK) and is reported, not fatal.
 */

import { existsSync, readFileSync } from "fs";
import { ADMIN_API } from "./env.js";
import { CLEANUP_FILE, clearCleanupFile, type CleanupEntry } from "./fixtures/cleanup.js";
import { getApiSession } from "./fixtures/session.js";

export default async function globalTeardown() {
  if (!existsSync(CLEANUP_FILE)) return;

  const entries: CleanupEntry[] = [];
  for (const line of readFileSync(CLEANUP_FILE, "utf-8").split("\n")) {
    if (!line.trim()) continue;
    try {
      entries.push(JSON.parse(line) as CleanupEntry);
    } catch {
      // ignore a torn line
    }
  }
  clearCleanupFile();

  const session = getApiSession();
  if (!session) {
    console.warn(`Global teardown: no saved session; ${entries.length} entities left behind`);
    return;
  }

  let deleted = 0;
  let kept = 0;
  // Delete in reverse order (teardown LIFO)
  for (const entry of entries.reverse()) {
    try {
      const resp = await fetch(`${ADMIN_API}${entry.url}`, {
        method: entry.method,
        headers: {
          Cookie: `mintkey_session=${session.sessionToken}; csrf_token=${session.csrfToken}`,
          "X-Mintkey-Csrf": session.csrfToken,
        },
      });
      if (resp.ok || resp.status === 404) deleted++;
      else kept++;
    } catch {
      kept++; // best-effort cleanup
    }
  }

  console.log(`Global teardown -- deleted ${deleted} of ${entries.length} entities (${kept} could not be deleted)`);
}
