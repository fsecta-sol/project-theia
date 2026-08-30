#!/usr/bin/env python3
"""Audit Theia paper ledger + hypothesis + wallet signal state."""
import sqlite3

DB = "/home/hermes/.hermes/theia/theia.db"
c = sqlite3.connect(DB)
c.row_factory = sqlite3.Row


def rows(sql, *args):
    return [dict(r) for r in c.execute(sql, args)]


print("== TRADES by state ==")
for r in rows("select state, count(*) n from paper_trades group by state"):
    print(r)

print("\n== ARCHIVES summary ==")
for r in rows("select exit_reason, count(*) n, round(sum(realized_pnl_sol),4) pnl, "
              "round(avg(realized_pnl_sol),4) avg_pnl from archives group by exit_reason"):
    print(r)

arch = rows("select * from archives")
tot = sum(a["realized_pnl_sol"] for a in arch)
wins = sum(1 for a in arch if a["realized_pnl_sol"] > 0)
print(f"\nTOTAL realized: {tot:.4f} SOL | trades: {len(arch)} | wins: {wins} "
      f"| reconstructable: {sum(a['reconstructable'] for a in arch)}")

print("\n== ARCHIVES detail ==")
for a in sorted(arch, key=lambda x: x["exit_ts"] or ""):
    print(f"  {a['trade_id']} {a['mint'][:6]} {a['exit_reason']:<14} pnl={a['realized_pnl_sol']:+.4f} "
          f"hold={a['hold_secs']} exit={a['exit_ts']} recon={a['reconstructable']}")

print("\n== HYPOTHESES ==")
for r in rows("select id, status, best_expectancy, best_pf, best_winrate, "
              "substr(title,1,60) t from hypotheses"):
    print(r)

print("\n== WALLET SIGNALS ==")
for r in rows("select signal_type, our_action, count(*) n, round(avg(latency_sec),0) avg_lat "
              "from wallet_signals group by signal_type, our_action"):
    print(r)

print("\n== WALLET PROFILES by source ==")
for r in rows("select source, is_smart_money, count(*) n from wallet_profiles group by source, is_smart_money"):
    print(r)

print("\n== WALLET SCAN HISTORY recency ==")
for r in rows("select date(scan_ts) d, count(*) n from wallet_scan_history group by d order by d desc limit 10"):
    print(r)
