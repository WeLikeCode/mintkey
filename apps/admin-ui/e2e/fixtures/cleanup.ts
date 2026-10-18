/**
 * Persisted cleanup queue.
 *
 * Fixtures run in Playwright worker processes and global-teardown in the runner process, so an
 * in-memory list never reached the teardown (and the teardown authenticated with an unset
 * PLAYWRIGHT_API_JWT, which admin-api rejects): nothing was ever cleaned up and every run left its
 * services and agents behind. Entries are appended here, one JSON object per line, and
 * global-teardown replays them (LIFO) with the saved OIDC session.
 */

import { appendFileSync, existsSync, mkdirSync, rmSync } from "fs";
import path from "path";
import { fileURLToPath } from "url";

const here = path.dirname(fileURLToPath(import.meta.url));

export const CLEANUP_FILE = path.resolve(here, "..", ".cleanup.ndjson");

export interface CleanupEntry {
  method: "DELETE";
  url: string;
}

export function recordCleanup(entry: CleanupEntry): void {
  mkdirSync(path.dirname(CLEANUP_FILE), { recursive: true });
  appendFileSync(CLEANUP_FILE, JSON.stringify(entry) + "\n");
}

export function clearCleanupFile(): void {
  if (existsSync(CLEANUP_FILE)) rmSync(CLEANUP_FILE);
}
