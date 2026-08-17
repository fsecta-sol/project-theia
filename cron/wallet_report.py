#!/usr/bin/env python3
"""Daily wallet pipeline report — summary of forward paper trading.

Prints a plain-text digest for the LLM cron job to format. 0 LLM here —
just aggregates the numbers from the store.
"""
import json
import sqlite3
import time
from pathlib import Path

DB = Path("/home/hermes/.hermes/theia/theia.db")
sys = __import__("sys")

con = sqlite3.connect(DB)
now = int(time.time())
day_ago = now - 24 * 3600

print("=== WALLET PIPELINE DAILY REPORT ===")
print(f"generated: {time.strftime('%Y-%m-%d %H:%M', time.gmtime(now))} UTC\n")

# Tracked wallets
n_sm = con.execute("SELECT COUNT(*) FROM wallet_profiles WHERE is_smart_money=1").fetchone()[0]
print(f"[tracked wallets] {n_sm} latency-tolerant")

# Signals today
n_sig = con.execute("SELECT COUNT(*) FROM wallet_signals WHERE detected_ts >= ?", (day_ago,)).fetchone()[0]
print(f"[signals 24h] {n_sig} new buys captured")

# Signal actions breakdown
print("[signal actions]")
for r in con.execute("""
    SELECT our_action, COUNT(*) FROM wallet_signals
    WHERE detected_ts >= ? GROUP BY our_action ORDER BY COUNT(*) DESC
""", (day_ago,)):
    print(f"  {r[0]}: {r[1]}")

# Open positions
open_trades = con.execute(
    "SELECT trade_id, mint, entry_ts, entry_price, size_sol FROM paper_trades WHERE state='open'"
).fetchall()
print(f"\n[open positions] {len(open_trades)}")
for t in open_trades:
    hold = (now - t[2]) // 60
    print(f"  {t[1][:12]} entry={t[3]:.3e} SOL size={t[4]} hold={hold}m")

# Closed positions (24h)
closed = con.execute("""
    SELECT mint, exit_reason, realized_pnl_sol, roi, hold_secs
    FROM archives WHERE created_ts >= ?
    ORDER BY created_ts DESC
""", (day_ago,)).fetchall()
print(f"\n[closed 24h] {len(closed)}")
for c in closed:
    print(f"  {c[0][:12]} {c[1]} pnl={c[2]:+.4f} SOL roi={c[3]:+.1%} hold={c[4]//60}m")

# Aggregate forward stats
if closed:
    pnls = [c[2] for c in closed]
    wins = [p for p in pnls if p > 0]
    gross_win = sum(wins)
    gross_loss = abs(sum(p for p in pnls if p <= 0))
    pf = gross_win / gross_loss if gross_loss > 0 else float("inf")
    print(f"\n[forward aggregate 24h] n={len(pnls)}, win_rate={len(wins)/len(pnls):.1%}, "
          f"expectancy={sum(pnls)/len(pnls):+.4f} SOL, PF={pf:.2f}")

# All-time forward stats
all_closed = con.execute("""
    SELECT realized_pnl_sol FROM archives ORDER BY created_ts
""").fetchall()
if all_closed:
    pnls = [c[0] for c in all_closed]
    wins = [p for p in pnls if p > 0]
    gross_win = sum(wins)
    gross_loss = abs(sum(p for p in pnls if p <= 0))
    pf = gross_win / gross_loss if gross_loss > 0 else float("inf")
    print(f"\n[forward aggregate ALL-TIME] n={len(pnls)}, win_rate={len(wins)/len(pnls):.1%}, "
          f"expectancy={sum(pnls)/len(pnls):+.4f} SOL, PF={pf:.2f}, total={sum(pnls):+.3f} SOL")

con.close()
