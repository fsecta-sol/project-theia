import { openDb } from "@/lib/db";
import type { WalletScanRow, WalletScansPayload } from "@/lib/types";

// Force request-time evaluation — never prerender DB-backed JSON at build.
export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const HOUR = 3600;

function nf(v: unknown): number {
  const n = typeof v === "string" ? parseFloat(v) : v;
  return typeof n === "number" && Number.isFinite(n) ? n : 0;
}
function nfn(v: unknown): number | null {
  const n = typeof v === "string" ? parseFloat(v) : v;
  return typeof n === "number" && Number.isFinite(n) ? n : null;
}

function parseTags(raw: string | null): string[] {
  if (!raw) return [];
  try {
    const v = JSON.parse(raw);
    return Array.isArray(v) ? v.map((x) => String(x)) : [];
  } catch {
    return [];
  }
}

// gate_reason dari pipeline berbentuk 'ok' | 'bad_tag:[...]' | 'wr7=0.40' |
// 'wr30=0.33' | 'txs7=12' | 'hold=132.2h' | 'dex_trending_pass:...' |
// 'dex_trending_reject:...'. Beri label untuk funnel/reject + kategori funnel.
function classifyGate(reason: string): {
  kind: "pass" | "fail";
  bucket: string;
  label: string;
} {
  if (!reason) return { kind: "fail", bucket: "other", label: reason };
  const r = reason.trim();
  if (r === "ok") return { kind: "pass", bucket: "pass", label: r };
  if (r.startsWith("bad_tag:"))
    return { kind: "fail", bucket: "bad_tag", label: r };
  if (r.startsWith("wr7=")) return { kind: "fail", bucket: "wr7", label: r };
  if (r.startsWith("wr30=")) return { kind: "fail", bucket: "wr30", label: r };
  if (r.startsWith("txs7=")) return { kind: "fail", bucket: "txs7", label: r };
  if (r.startsWith("hold=")) return { kind: "fail", bucket: "hold", label: r };
  if (r.startsWith("dex_trending_pass"))
    return { kind: "pass", bucket: "pass", label: r };
  if (r.startsWith("dex_trending_reject"))
    return { kind: "fail", bucket: "other", label: r };
  return { kind: "fail", bucket: "other", label: r };
}

export async function GET(request: Request): Promise<Response> {
  const fail = (error: string): Response =>
    Response.json(
      { ok: false, error, fetchedAt: Date.now(), ts: 0, runs: [], rows: [] } satisfies WalletScansPayload,
      { status: 200 },
    );

  // Range (hari) dibatasi di query SQL agar payload tetap kecil — UI memilih
  // 24h/7d/30d/all; "all" = seluruh riwayat (saat ini < 4 hari, aman).
  const url = new URL(request.url);
  const daysRaw = Number(url.searchParams.get("days") ?? "");
  const days = Number.isFinite(daysRaw) && daysRaw > 0 ? Math.min(daysRaw, 90) : null;
  const since = days ? Math.floor(Date.now() / 1000) - days * 86400 : null;

  const db = openDb();
  if (!db) return fail("unable to open theia.db");

  try {
    const table = db
      .prepare(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='wallet_scan_history'",
      )
      .get() as { name: string } | undefined;
    if (!table) return fail("wallet_scan_history table not found");

    const rows = (
      since
        ? db
            .prepare(
              `SELECT wallet, scan_ts, winrate_7d, winrate_30d, txs_7d, buy_7d, sell_7d,
                      avg_holding_period_7d, volume_7d, realized_profit_7d, pnl_7d,
                      tags, gate_pass, gate_reason, last_active, nickname, twitter_username,
                      pnl_gt_5x_num_7d, pnl_2x_5x_num_7d, pnl_lt_2x_num_7d,
                      pnl_minus_dot5_0x_num_7d, pnl_lt_minus_dot5_num_7d
               FROM wallet_scan_history WHERE scan_ts >= ? ORDER BY scan_ts DESC`,
            )
            .all(since)
        : db
            .prepare(
              `SELECT wallet, scan_ts, winrate_7d, winrate_30d, txs_7d, buy_7d, sell_7d,
                      avg_holding_period_7d, volume_7d, realized_profit_7d, pnl_7d,
                      tags, gate_pass, gate_reason, last_active, nickname, twitter_username,
                      pnl_gt_5x_num_7d, pnl_2x_5x_num_7d, pnl_lt_2x_num_7d,
                      pnl_minus_dot5_0x_num_7d, pnl_lt_minus_dot5_num_7d
               FROM wallet_scan_history ORDER BY scan_ts DESC`,
            )
            .all()
    ) as Array<Record<string, unknown>>;

    const out: WalletScanRow[] = rows.map((r) => {
      const reason = String(r.gate_reason ?? "");
      const g = classifyGate(reason);
      return {
        addr: String(r.wallet),
        scanTs: nf(r.scan_ts),
        win7: nf(r.winrate_7d),
        win30: nf(r.winrate_30d),
        trades: Math.round(nf(r.txs_7d)),
        buys: Math.round(nf(r.buy_7d)),
        sells: Math.round(nf(r.sell_7d)),
        holdingSec: nfn(r.avg_holding_period_7d),
        vol7: nf(r.volume_7d),
        pnl7: nf(r.realized_profit_7d),
        tags: parseTags(String(r.tags ?? "")),
        gate: g.kind,
        gateReason: reason,
        reasonBucket: g.bucket,
        lastActiveTs: nfn(r.last_active),
        nickname: r.nickname ? String(r.nickname) : "",
        twitter: r.twitter_username ? String(r.twitter_username) : "",
        dist: [
          Math.round(nf(r.pnl_gt_5x_num_7d)),
          Math.round(nf(r.pnl_2x_5x_num_7d)),
          Math.round(nf(r.pnl_lt_2x_num_7d)),
          Math.round(nf(r.pnl_minus_dot5_0x_num_7d)),
          Math.round(nf(r.pnl_lt_minus_dot5_num_7d)),
        ],
      };
    });

    // Satu "run" = satu jam penuh (scan pipeline berjalan ~tepat jam).
    // Kelompokkan ke jam; gap antar run = tidak ada data pada jam itu.
    const byHour = new Map<number, { rows: WalletScanRow[]; i: number }>();
    for (const row of out) {
      const h = Math.floor(row.scanTs / HOUR) * HOUR;
      let bucket = byHour.get(h);
      if (!bucket) {
        bucket = { rows: [], i: byHour.size };
        byHour.set(h, bucket);
      }
      bucket.rows.push(row);
    }
    const hours = [...byHour.keys()].sort((a, b) => b - a);
    const runs = hours.map((h) => {
      const b = byHour.get(h)!;
      const scanned = b.rows.length;
      const passed = b.rows.filter((r) => r.gate === "pass").length;
      // tooltip chart butuh top reject per run — kirim agregat, bukan row penuh.
      const rejects: Record<string, number> = {};
      b.rows.forEach((r) => {
        if (r.gate === "fail") rejects[r.reasonBucket || "other"] = (rejects[r.reasonBucket || "other"] || 0) + 1;
      });
      return {
        i: b.i,
        ts: h,
        gap: false,
        scanned,
        passed,
        rejects: Object.keys(rejects)
          .map((k) => ({ bucket: k, n: rejects[k] }))
          .sort((a, c) => c.n - a.n),
      };
    });
    // jam-jam kosong di antara run → gap (tidak ada data scan jam itu)
    if (runs.length > 1) {
      const full: typeof runs = [];
      for (let k = 0; k < runs.length; k++) {
        full.push(runs[k]);
        const next = runs[k + 1];
        if (next) {
          const diffH = Math.round((runs[k].ts - next.ts) / 3600000);
          for (let g = 1; g < diffH; g++) {
            full.push({ i: full.length, ts: runs[k].ts - g * HOUR, gap: true, scanned: 0, passed: 0, rejects: [] });
          }
        }
      }
      runs.length = 0;
      runs.push(...full);
    }

    const payload: WalletScansPayload = {
      ok: true,
      fetchedAt: Date.now(),
      ts: out.length ? out[0].scanTs : 0,
      runs,
      rows: out,
    };
    return Response.json(payload, { status: 200 });
  } catch (e) {
    return fail(e instanceof Error ? e.message : String(e));
  } finally {
    db.close();
  }
}
