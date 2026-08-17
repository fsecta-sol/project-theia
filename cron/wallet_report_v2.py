#!/usr/bin/env python3
"""Wallet pipeline report v2 — adds latency + concentration stats (fix #10)."""
import json
import sqlite3
import time
from pathlib import Path

DB = Path("/home/hermes/.hermes/theia/theia.db")
con = sqlite3.connect(DB)
now = int(time.time())
day_ago = now - 24 * 3600

print("=== WALLET PIPELINE DAILY REPORT ===")
print(f"generated: {time.strftime('%Y-%m-%d %H:%M', time.gmtime(now))} UTC\n")

n_sm = con.execute("SELECT COUNT(*) FROM wallet_profiles WHERE is_smart_money=1").fetchone()[0]
print(f"[tracked wallets] {n_sm} latency-tolerant")

n_sig = con.execute("SELECT COUNT(*) FROM wallet_signals WHERE detected_ts >= ?", (day_ago,)).fetchone()[0]
print(f"[signals 24h] {n_sig} new buys")

# latency stats (fix #10): how late did we detect, for signals we acted on
lat = con.execute("""
    SELECT AVG(latency_sec), MIN(latency_sec), MAX(latency_sec)
    FROM wallet_signals WHERE detected_ts >= ? AND latency_sec IS NOT NULL
""", (day_ago,)).fetchone()
if lat and lat[0] is not None:
    print(f"[detection latency] avg={lat[0]:.0f}s min={lat[1]}s max={lat[2]}s")
else:
    print("[detection latency] no data")

print("[signal actions]")
for r in con.execute("""
    SELECT our_action, COUNT(*) FROM wallet_signals
    WHERE detected_ts >= ? GROUP BY our_action ORDER BY COUNT(*) DESC
""", (day_ago,)):
    print(f"  {r[0]}: {r[1]}")

open_trades = con.execute(
    "SELECT trade_id, mint, entry_ts, entry_price, size_sol FROM paper_trades WHERE state='open'"
).fetchall()
print(f"\n[open positions] {len(open_trades)}")
for t in open_trades:
    hold = (now - t[2]) // 60
    print(f"  {t[1][:12]} entry={t[3]:.3e} SOL size={t[4]} hold={hold}m")

closed = con.execute("""
    SELECT mint, exit_reason, realized_pnl_sol, roi, hold_secs
    FROM archives WHERE created_ts >= ?
    ORDER BY created_ts DESC
""", (day_ago,)).fetchall()
print(f"\n[closed 24h] {len(closed)}")
for c in closed:
    print(f"  {c[0][:12]} {c[1]} pnl={c[2]:+.4f} SOL roi={c[3]:+.1%} hold={c[4]//60}m")

# forward aggregate (24h + all-time)
def _agg(rows):
    if not rows:
        return None
    pnls = [r[0] for r in rows]
    wins = [p for p in pnls if p > 0]
    gw = sum(wins)
    gl = abs(sum(p for p in pnls if p <= 0))
    pf = gw / gl if gl > 0 else float("inf")
    return {"n": len(pnls), "win_rate": len(wins)/len(pnls),
            "expectancy": sum(pnls)/len(pnls), "pf": pf, "total": sum(pnls)}

c24 = _agg(con.execute("SELECT realized_pnl_sol FROM archives WHERE created_ts >= ?", (day_ago,)).fetchall())
if c24:
    print(f"\n[forward 24h] n={c24['n']}, win={c24['win_rate']:.1%}, "
          f"exp={c24['expectancy']:+.4f}, PF={c24['pf']:.2f}, total={c24['total']:+.3f}")

call = _agg(con.execute("SELECT realized_pnl_sol FROM archives").fetchall())
if call:
    print(f"[forward ALL-TIME] n={call['n']}, win={call['win_rate']:.1%}, "
          f"exp={call['expectancy']:+.4f}, PF={call['pf']:.2f}, total={call['total']:+.3f}")

# concentration check (fix #6): top wallet share of all-time PnL
print("\n[concentration]")
try:
    # opened_by is JSON; extract wallet via substr
    rows = con.execute("""
        SELECT opened_by, realized_pnl_sol FROM archives a
        JOIN paper_trades p ON p.trade_id = a.trade_id
    """).fetchall()
    from collections import defaultdict
    by_w = defaultdict(float)
    for ob, pnl in rows:
        try:
            obd = json.loads(ob) if isinstance(ob, str) else (ob or {})
        except Exception:
            obd = {}
        w = obd.get("wallet") if isinstance(obd, dict) else "?"
        by_w[w] += pnl or 0
    total = sum(by_w.values())
    if total > 0:
        for w, pnl in sorted(by_w.items(), key=lambda x: -x[1])[:5]:
            print(f"  {w[:14]}: {pnl:+.3f} SOL ({pnl/total*100:.0f}%)")
        top = max(by_w.values())
        print(f"  top-wallet share: {top/total*100:.0f}% "
              f"{'WARN single-wallet dominance' if top/total > 0.5 else 'OK diversified'}")
except Exception as e:
    print(f"  concentration n/a: {e}")

con.close()
