/**
 * Global teardown — clean up test data via admin-api.
 *
 * Reads a file written by tests that records created entity IDs
 * so we can delete them in reverse order.
 */

import { writeFileSync, existsSync, readFileSync } from "fs";
import { join, dirname } from "path";
import { fileURLToPath } from "url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

const CLEANUP_FILE = join(__dirname, "tests", "_cleanup.json");

interface CleanupEntry {
  method: string;
  url: string;
}

export default async function globalTeardown() {
  if (!existsSync(CLEANUP_FILE)) return;

  const raw = readFileSync(CLEANUP_FILE, "utf-8");
  let entries: CleanupEntry[] = [];
  try {
    entries = JSON.parse(raw);
  } catch {
    // ignore malformed files
  }

  const adminApi = process.env.ADMIN_API_URL ?? "http://localhost:8080";
  const token = process.env.PLAYWRIGHT_API_JWT ?? "";

  // Delete in reverse order (teardown LIFO)
  for (const entry of entries.reverse()) {
    try {
      await fetch(`${adminApi}${entry.url}`, {
        method: entry.method as string,
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
      });
    } catch {
      // best-effort cleanup
    }
  }

  console.log(`🧹 Global teardown — cleaned up ${entries.length} entities`);
}