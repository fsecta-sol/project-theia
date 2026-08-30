import { DB_PATH, openDb, countByStatus, lastTs } from "@/lib/db";
import type { PipelineV4Payload, V4ScopeData } from "@/lib/types";

// Force request-time evaluation — never prerender DB-backed JSON at build.
export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const ZERO_SCOPE: V4ScopeData = {
  counts: {
    harvest: 0, qualify: 0, wallets: 0, buy: 0,
    screenPass: 0, screenVeto: 0, entry: 0, monitor: 0, exit: 0,
  },
  screenExText: "",
  monitorPnlText: "—",
  monitorPnlCls: "flat",
  monitorGuardText: "",
  exitPnlText: "—",
  exitPnlCls: "flat",
  exitNoteText: "",
};

function fmtPct(v: number): string {
  return `${v > 0 ? "+" : ""}${(v * 100).toFixed(1)}%`;
}

const ERR_PAYLOAD = (error: string) => ({
  ok: false,
  error,
  fetchedAt: Date.now(),
  scopes: { all: ZERO_SCOPE, h24: ZERO_SCOPE },
  timing: {
    signalLatencyAvgSecs: null,
    avgHoldSecs: null,
    lastSignalTs: null,
    pipelineLastRunTs: null,
  },
  notes: { exitReasons: {}, signalSkips: {}, smartTotal: 0, harvestTotal: 0 },
  digestNote: "",
});

export async function GET(): Promise<Response> {
  const handle = openDb();
  if (!handle) {
    return Response.json(ERR_PAYLOAD(`unable to open theia DB at ${DB_PATH}`), { status: 200 });
  }
  const db = handle;

  try {
    const count = (sql: string, ...bind: unknown[]): number => {
      try {
        const row = db.prepare(sql).get(...bind) as { n: number };
        return row?.n ?? 0;
      } catch {
        return 0;
      }
    };

    const dayAgo = Math.floor(Date.now() / 1000) - 86400;

    // ── per-scope counts. `since = null` → all-time window.
    function scopeData(since: number | null): V4ScopeData {
      const w = (col: string): string => (since === null ? "1=1" : `${col} >= ?`);
      const b = since === null ? [] : [since];

      // Signal detection
      const harvest = count(`SELECT COUNT(*) AS n FROM wallet_profiles WHERE ${w("first_seen_ts")}`, ...b);
      const qualify = count(
        `SELECT COUNT(*) AS n FROM wallet_profiles WHERE total_trades > 0 AND win_rate IS NOT NULL AND ${w("first_seen_ts")}`,
        ...b,
      );
      const wallets = count(
        "SELECT COUNT(*) AS n FROM wallet_profiles WHERE is_smart_money = 1",
      ); // watchlist size is point-in-time, not windowed
      const buy = count(`SELECT COUNT(*) AS n FROM wallet_signals WHERE ${w("detected_ts")}`, ...b);

      // Trade lifecycle
      const screensAll = db
        .prepare(`SELECT verdict AS k, COUNT(*) AS n FROM screens WHERE ${w("screen_ts")} GROUP BY verdict`)
        .all(...(b as unknown[])) as Array<{ k: string; n: number }>;
      const screenPass = screensAll.find((r) => r.k === "pass")?.n ?? 0;
      const screenVeto = screensAll.filter((r) => r.k !== "pass").reduce((s, r) => s + r.n, 0);

      const entry = count(`SELECT COUNT(*) AS n FROM paper_trades WHERE ${w("entry_ts")}`, ...b);
      const monitor = count(
        since === null
          ? "SELECT COUNT(*) AS n FROM paper_trades WHERE state = 'open'"
          : "SELECT COUNT(*) AS n FROM paper_trades WHERE state = 'open' AND entry_ts >= ?",
        ...b,
      );
      const exits = countByStatus(db, "archives", "exit_reason"); // archives immutable — all-time only makes sense
      void exits;

      // examples
      let screenExText = "";
      if (buy === 0) {
        screenExText = since !== null || count("SELECT COUNT(*) AS n FROM wallet_signals") === 0
          ? "no signals in the last 24h"
          : "";
      }
      if (!screenExText && since === null) {
        const lastVeto = db
          .prepare(
            "SELECT reject_reason FROM screens WHERE verdict != 'pass' AND reject_reason IS NOT NULL AND reject_reason != '' ORDER BY screen_ts DESC LIMIT 1",
          )
          .get() as { reject_reason: string } | undefined;
        screenExText = lastVeto?.reject_reason ? `veto · ${lastVeto.reject_reason}` : "";
      }

      const archAgg = (() => {
        try {
          return db
            .prepare(
              `SELECT COALESCE(AVG(roi), NULL) AS roi, COUNT(*) AS n FROM archives
               WHERE exit_reason NOT LIKE 'voided%'${since === null ? "" : " AND created_ts >= ?"}`,
            )
            .get(...(since === null ? [] : [since]) as []) as { roi: number | null; n: number };
        } catch {
          return { roi: null, n: 0 };
        }
      })();

      const monitorPnl = (() => {
        try {
          return db
            .prepare(
              "SELECT COALESCE(SUM(size_sol), 0) AS size FROM paper_trades WHERE state = 'open'",
            )
            .get() as { size: number };
        } catch {
          return { size: 0 };
        }
      })();

      return {
        counts: {
          harvest,
          qualify,
          wallets,
          buy,
          screenPass,
          screenVeto,
          entry,
          monitor,
          exit: archAgg?.n ?? 0,
        },
        screenExText:
          screenExText ||
          (screenPass + screenVeto === 0 ? (since === null ? "" : "no signals in the last 24h") : ""),
        monitorPnlText: monitor > 0 && monitorPnl.size > 0 ? `${monitor} open` : "—",
        monitorPnlCls: monitor > 0 ? "ok" : "flat",
        monitorGuardText:
          monitor > 0 ? "guard: stop −35% · TP 2x–4x · time 60m" : "no open positions",
        exitPnlText: archAgg?.roi !== null && archAgg?.roi !== undefined ? fmtPct(archAgg.roi) : "—",
        exitPnlCls: (archAgg?.roi ?? 0) > 0 ? "ok" : (archAgg?.roi ?? 0) < 0 ? "fail" : "flat",
        exitNoteText:
          (archAgg?.n ?? 0) > 0 ? "net of gas + fees + slippage" : "no exits yet",
      };
    }

    const all = scopeData(null);
    const h24 = scopeData(dayAgo);

    // ── timing
    const latRow = (() => {
      try {
        return db
          .prepare("SELECT AVG(latency_sec) AS v FROM wallet_signals WHERE latency_sec IS NOT NULL")
          .get() as { v: number | null };
      } catch {
        return { v: null };
      }
    })();
    const holdRow = (() => {
      try {
        return db
          .prepare("SELECT AVG(hold_secs) AS v FROM archives WHERE hold_secs > 0")
          .get() as { v: number | null };
      } catch {
        return { v: null };
      }
    })();
    const pipeRow = (() => {
      try {
        return db.prepare("SELECT v FROM kv_state WHERE k = 'wallet_pipeline_last_ts'").get() as
          | { v: string }
          | undefined;
      } catch {
        return undefined;
      }
    })();

    // ── notes breakdowns
    const exitReasons: Record<string, number> = {};
    for (const [k, n] of Object.entries(countByStatus(db, "archives", "exit_reason"))) {
      exitReasons[k] = n;
    }
    const signalSkips: Record<string, number> = {};
    try {
      const rows = db
        .prepare("SELECT our_action AS a, COUNT(*) AS n FROM wallet_signals GROUP BY our_action")
        .all() as Array<{ a: string; n: number }>;
      for (const r of rows) signalSkips[r.a] = r.n;
    } catch {
      /* fresh DB */
    }

    const harvestTotal = count("SELECT COUNT(*) AS n FROM wallet_profiles");
    const smartTotal = count("SELECT COUNT(*) AS n FROM wallet_profiles WHERE is_smart_money = 1");
    const lastSignalTs = lastTs(db, "wallet_signals", "detected_ts");

    const payload: PipelineV4Payload = {
      ok: true,
      fetchedAt: Date.now(),
      scopes: { all, h24 },
      timing: {
        signalLatencyAvgSecs: latRow?.v ? Math.round(latRow.v) : null,
        avgHoldSecs: holdRow?.v ? Math.round(holdRow.v) : null,
        lastSignalTs,
        pipelineLastRunTs: pipeRow?.v ? Number(pipeRow.v) : null,
      },
      notes: { exitReasons, signalSkips, smartTotal, harvestTotal },
      digestNote:
        all.counts.buy === 0
          ? "no pipeline activity recorded"
          : `${h24.counts.buy} signals in last 24h`,
    };
    return Response.json(payload, { status: 200 });
  } catch (err) {
    return Response.json(ERR_PAYLOAD(err instanceof Error ? err.message : String(err)), { status: 200 });
  } finally {
    db.close();
  }
}
