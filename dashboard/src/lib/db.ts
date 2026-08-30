import { DatabaseSync } from "node:sqlite";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

export const DB_PATH =
  process.env.THEIA_DB_PATH || "/home/hermes/.hermes/theia/theia.db";

const REPO_ROOT = process.env.THEIA_REPO_ROOT || resolve(process.cwd(), "..");
const CRON_CONFIG = resolve(REPO_ROOT, "cron", "theia-jobs.json");

export function openDb(): DatabaseSync | null {
  try {
    return new DatabaseSync(DB_PATH, { readOnly: true });
  } catch {
    return null;
  }
}

export function countByStatus(
  db: DatabaseSync,
  table: string,
  col: string,
): Record<string, number> {
  const out: Record<string, number> = {};
  try {
    const rows = db
      .prepare(`SELECT ${col} AS k, COUNT(*) AS n FROM ${table} GROUP BY ${col}`)
      .all() as Array<{ k: string; n: number }>;
    for (const r of rows) out[r.k] = r.n;
  } catch {
    /* table may be absent in a fresh DB */
  }
  return out;
}

export function lastTs(db: DatabaseSync, table: string, col: string): number | null {
  try {
    const row = db
      .prepare(`SELECT MAX(${col}) AS m FROM ${table}`)
      .get() as { m: number | null } | undefined;
    return row && row.m ? row.m : null;
  } catch {
    return null;
  }
}

export function readCronCounts(): { enabled: number; total: number } | null {
  try {
    const raw = JSON.parse(readFileSync(CRON_CONFIG, "utf8")) as {
      jobs?: Array<{ enabled?: boolean }>;
    };
    const jobs = Array.isArray(raw.jobs) ? raw.jobs : [];
    return {
      enabled: jobs.filter((j) => j.enabled === true).length,
      total: jobs.length,
    };
  } catch {
    return null;
  }
}
