#!/usr/bin/env python3
"""How many 'active momentum whales' (OOS-confirmed gate-v2 criteria) do we have?"""
import sqlite3

DB = "/home/hermes/.hermes/theia/theia.db"
con = sqlite3.connect(DB)
con.row_factory = sqlite3.Row

rows = con.execute(
    "SELECT wallet, scan_ts, txs_7d, volume_7d, realized_profit_7d, "
    "avg_holding_period_7d, winrate_7d, tags FROM wallet_scan_history "
    "WHERE scan_ts >= strftime('%s','2026-08-25') ORDER BY wallet, scan_ts").fetchall()

latest = {}
for r in rows:
    latest[r["wallet"]] = {
        "txs": r["txs_7d"], "vol": r["volume_7d"] or 0, "r7": r["realized_profit_7d"],
        "hold": r["avg_holding_period_7d"], "wr": r["winrate_7d"],
    }

vols = sorted(v["vol"] for v in latest.values() if v["vol"] > 0)
q3 = vols[int(len(vols) * 0.75)] if vols else 0
print(f"wallets scanned since 25-Aug: {len(latest)}")
print(f"volume q3 (top-quartile cutoff): {q3:,.0f}")

whales = [(w, v) for w, v in latest.items()
          if (v["txs"] or 0) >= 500 and (v["r7"] or 0) >= 10000
          and (v["hold"] or 0) < 48 * 3600 and v["vol"] >= q3]
print(f"\nACTIVE MOMENTUM WHALES (all 4 gate-v2 criteria): {len(whales)}")
print(f"{'wallet':<16} {'txs':>6} {'vol7d':>14} {'rPnl7d':>12} {'hold':>7} {'wr7':>5}")
for w, v in sorted(whales, key=lambda x: -x[1]["r7"])[:20]:
    hold_h = (v["hold"] or 0) / 3600
    print(f"{w[:14]:<16} {v['txs']:>6} {v['vol']:>14,.0f} {v['r7']:>12,.0f} {hold_h:>6.1f}h {v['wr'] if v['wr'] is not None else 0:>5.2f}")

tracked = set(r[0] for r in con.execute(
    "SELECT wallet FROM wallet_profiles WHERE track_enabled=1"))
overlap = [w for w, _ in whales if w in tracked]
print(f"\nalready tracked by pipeline: {len(overlap)}")
print(f"NOT yet tracked: {len(whales) - len(overlap)}")

# partial: how many meet 3 of 4 criteria (relaxed)?
relaxed = [(w, v) for w, v in latest.items()
           if (v["txs"] or 0) >= 500 and (v["r7"] or 0) >= 10000 and (v["hold"] or 0) < 48 * 3600]
print(f"\nrelaxed (txs>=500 + rPnl>=10k + hold<48h, no vol cutoff): {len(relaxed)}")
