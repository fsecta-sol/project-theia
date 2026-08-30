import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { openDb } from "@/lib/db";
import type { WalletsPayload, LiveWallet } from "@/lib/types";

// Force request-time evaluation — never prerender DB-backed JSON at build.
export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const GATE_DATA = process.env.THEIA_GATE_DATA || "/home/hermes/theia-gate/data";
const DISCOVERED = resolve(GATE_DATA, "discovered_wallets.json");

interface GmgnWallet {
  address: string;
  nickname?: string;
  twitter_username?: string;
  winrate_7d?: number;
  winrate_30d?: number;
  pnl_7d?: string | number;
  realized_profit_7d?: string | number;
  txs_7d?: number;
  avg_holding_period_7d?: number;
  volume_7d?: string | number;
  pnl_gt_5x_num_7d?: number;
  pnl_2x_5x_num_7d?: number;
  pnl_lt_2x_num_7d?: number;
  pnl_minus_dot5_0x_num_7d?: number;
  pnl_lt_minus_dot5_num_7d?: number;
  tags?: string[];
  last_active?: number;
}

function num(v: string | number | undefined): number {
  const n = typeof v === "string" ? parseFloat(v) : v;
  return Number.isFinite(n as number) ? (n as number) : 0;
}

export async function GET(): Promise<Response> {
  let raw: { gmgn?: GmgnWallet[]; ts?: number };
  try {
    raw = JSON.parse(readFileSync(DISCOVERED, "utf8")) as typeof raw;
  } catch {
    return Response.json(
      { ok: false, error: `unable to read ${DISCOVERED}`, fetchedAt: Date.now(), ts: 0, wallets: [], smartCount: 0, total: 0 } satisfies WalletsPayload,
      { status: 200 },
    );
  }

  const gmgn = Array.isArray(raw.gmgn) ? raw.gmgn : [];

  let smartSet = new Set<string>();
  try {
    const db = openDb();
    if (db) {
      try {
        const rows = db
          .prepare("SELECT wallet FROM wallet_profiles WHERE is_smart_money = 1")
          .all() as Array<{ wallet: string }>;
        smartSet = new Set(rows.map((r) => r.wallet));
      } finally {
        db.close();
      }
    }
  } catch {
    /* smart flag unavailable — everything stays candidate */
  }

  const wallets: LiveWallet[] = gmgn.map((g) => ({
    address: g.address,
    nickname: g.nickname ?? "",
    twitter: g.twitter_username ?? "",
    winrate7d: num(g.winrate_7d),
    winrate30d: num(g.winrate_30d),
    pnl7d: num(g.pnl_7d),
    realizedProfit7d: num(g.realized_profit_7d),
    txs7d: g.txs_7d ?? 0,
    avgHoldingSec: g.avg_holding_period_7d ?? 0,
    volume7d: num(g.volume_7d),
    tags: Array.isArray(g.tags) ? g.tags : [],
    lastActiveTs: g.last_active ?? null,
    dist: [
      [g.pnl_gt_5x_num_7d ?? 0, ">5x"],
      [g.pnl_2x_5x_num_7d ?? 0, "2–5x"],
      [g.pnl_lt_2x_num_7d ?? 0, "<2x"],
      [g.pnl_minus_dot5_0x_num_7d ?? 0, "-0.5–0x"],
      [g.pnl_lt_minus_dot5_num_7d ?? 0, "<-0.5x"],
    ] as [number, string][],
    isSmartMoney: smartSet.has(g.address),
    source: smartSet.has(g.address) ? "gmgn + wallet_profiles" : "gmgn discovered_wallets.json",
  }));

  wallets.sort((a, b) =>
    a.isSmartMoney === b.isSmartMoney ? b.winrate7d - a.winrate7d : a.isSmartMoney ? -1 : 1,
  );

  const payload: WalletsPayload = {
    ok: true,
    fetchedAt: Date.now(),
    ts: raw.ts ?? 0,
    wallets,
    smartCount: wallets.filter((w) => w.isSmartMoney).length,
    total: wallets.length,
  };
  return Response.json(payload, { status: 200 });
}
