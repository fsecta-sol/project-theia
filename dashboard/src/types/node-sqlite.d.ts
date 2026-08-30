// Minimal ambient types for Node's built-in `node:sqlite` (DatabaseSync).
// Node runtime ≥22.5 ships this; @types/node@20 lacks it, so we declare it
// locally rather than pinning a newer @types/node.
declare module "node:sqlite" {
  export class DatabaseSync {
    constructor(path: string, options?: { readOnly?: boolean });
    prepare(sql: string): StatementSync;
    exec(sql: string): void;
    close(): void;
  }

  export interface StatementSync {
    get(...bind: unknown[]): Record<string, unknown> | undefined;
    all(...bind: unknown[]): Record<string, unknown>[];
    run(...bind: unknown[]): { changes: number; lastInsertRowid: number | bigint };
  }
}