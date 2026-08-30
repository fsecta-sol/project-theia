import { DB_PATH, openDb, countByStatus, lastTs, readCronCounts } from "@/lib/db";
import type { OverviewPayload } from "@/lib/types";

// Force request-time evaluation — never prerender DB-backed JSON at build.
export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET(): Promise<Response> {
  const db = openDb();
  if (!db) {
    const payload: OverviewPayload = {
      ok: false,
      error: `unable to open theia DB at ${DB_PATH}`,
      fetchedAt: Date.now(),
      expectancy: {
        n: 0, expectancy: 0, profitFactor: null, winRate: 0, totalPnl: 0,
        hardStop: 0, voided: 0, updatedTs: null, source: "db offline",
      },
      knowledge: { verified: 0, total: 0, needsSource: 0, draft: 0, updatedTs: null },
      vitals: {
        cronsEnabled: 0, cronsTotal: 0, queueDepth: 0,
        queueBreakdown: {}, llmSpendUsd: null, llmShotsCount: 0,
        pipelineLastRunTs: null, pipelineNote: "db offline",
      },
      digest: { note: "no data — theia DB unreachable", signal24h: 0, closed24h: 0 },
    };
    return Response.json(payload, { status: 200 });
  }

  try {
    // --- hero: expectancy / profit factor from archives (deterministic, net fees) ---
    const arch = db
      .prepare(
        "SELECT realized_pnl_sol AS pnl, exit_reason AS reason FROM archives",
      )
      .all() as Array<{ pnl: number; reason: string }>;
    const pnls = arch.map((a) => a.pnl ?? 0);
    const wins = pnls.filter((p) => p > 0);
    const losses = pnls.filter((p) => p <= 0);
    const grossProfit = wins.reduce((s, p) => s + p, 0);
    const grossLoss = Math.abs(losses.reduce((s, p) => s + p, 0));
    const expectancy =
      pnls.length > 0 ? pnls.reduce((s, p) => s + p, 0) / pnls.length : 0;
    const profitFactor = grossLoss > 0 ? grossProfit / grossLoss : null;
    const winRate = pnls.length > 0 ? wins.length / pnls.length : 0;
    const hardStop = arch.filter((a) => a.reason === "hard_stop").length;
    const voided = arch.filter((a) => (a.reason ?? "").startsWith("voided")).length;
    const archUpdated = lastTs(db, "archives", "created_ts");

    // --- knowledge / exit criteria progress ---
    const kStatus = countByStatus(db, "knowledge_index", "status");
    const kTotal = Object.values(kStatus).reduce((s, n) => s + n, 0);

    // --- vitals ---
    const taskRows = countByStatus(db, "tasks", "state");
    const queueDepth =
      (taskRows["ready"] ?? 0) +
      (taskRows["blocked"] ?? 0) +
      (taskRows["running"] ?? 0);
    const llmRow = db
      .prepare("SELECT COUNT(*) AS n, COALESCE(SUM(cost_usd), 0) AS cost FROM llm_shots")
      .get() as { n: number; cost: number };
    const llmShotsCount = llmRow?.n ?? 0;
    const llmSpendUsd = llmRow && llmRow.n > 0 ? llmRow.cost : null;

    const pipeRow = db
      .prepare("SELECT v FROM kv_state WHERE k = 'wallet_pipeline_last_ts'")
      .get() as { v: string } | undefined;
    const pipelineLastRunTs = pipeRow && pipeRow.v ? Number(pipeRow.v) : null;

    const cron = readCronCounts();

    // --- digest (no journal table exists — honest note + fresh signal counts) ---
    const now = Math.floor(Date.now() / 1000);
    const dayAgo = now - 86400;
    const signal24h = (
      db.prepare("SELECT COUNT(*) AS n FROM wallet_signals WHERE detected_ts >= ?")
        .get(dayAgo) as { n: number }
    ).n;
    const closed24h = (
      db.prepare("SELECT COUNT(*) AS n FROM archives WHERE created_ts >= ?")
        .get(dayAgo) as { n: number }
    ).n;
    const digestNote = closed24h === 0 && signal24h === 0
      ? "no journal source — 0 signals / 0 closed trades in the last 24h"
      : `${signal24h} signals · ${closed24h} closed in last 24h`;

    const payload: OverviewPayload = {
      ok: true,
      fetchedAt: Date.now(),
      expectancy: {
        n: pnls.length,
        expectancy,
        profitFactor,
        winRate,
        totalPnl: pnls.reduce((s, p) => s + p, 0),
        hardStop,
        voided,
        updatedTs: archUpdated,
        source: "archives · FIFO · net of fees+latency",
      },
      knowledge: {
        verified: kStatus["verified"] ?? 0,
        total: kTotal,
        needsSource: (kStatus["needs-source"] ?? 0) + (kStatus["needs_source"] ?? 0),
        draft: kStatus["draft"] ?? 0,
        updatedTs: lastTs(db, "knowledge_index", "last_updated"),
      },
      vitals: {
        cronsEnabled: cron?.enabled ?? 0,
        cronsTotal: cron?.total ?? 0,
        queueDepth,
        queueBreakdown: taskRows,
        llmSpendUsd,
        llmShotsCount,
        pipelineLastRunTs,
        pipelineNote: pipelineLastRunTs
          ? `wallet pipeline last run ${new Date(pipelineLastRunTs * 1000).toISOString()}`
          : "no pipeline run recorded",
      },
      digest: {
        note: digestNote,
        signal24h,
        closed24h,
      },
    };
    return Response.json(payload, { status: 200 });
  } catch (err) {
    const payload: OverviewPayload = {
      ok: false,
      error: err instanceof Error ? err.message : String(err),
      fetchedAt: Date.now(),
      expectancy: {
        n: 0, expectancy: 0, profitFactor: null, winRate: 0, totalPnl: 0,
        hardStop: 0, voided: 0, updatedTs: null, source: "query error",
      },
      knowledge: { verified: 0, total: 0, needsSource: 0, draft: 0, updatedTs: null },
      vitals: {
        cronsEnabled: 0, cronsTotal: 0, queueDepth: 0,
        queueBreakdown: {}, llmSpendUsd: null, llmShotsCount: 0,
        pipelineLastRunTs: null, pipelineNote: "query error",
      },
      digest: { note: "query error — see server logs", signal24h: 0, closed24h: 0 },
    };
    return Response.json(payload, { status: 200 });
  } finally {
    db.close();
  }
}
