#!/usr/bin/env python3
"""Who passed gate v2 today (unique wallets, latest scan verdict)?"""
import sqlite3
import datetime

c = sqlite3.connect("/home/hermes/.hermes/theia/theia.db")
c.row_factory = sqlite3.Row

rows = c.execute(
    "SELECT wallet, scan_ts, gate_pass, gate_reason, txs_7d, realized_profit_7d, "
    "winrate_7d, volume_7d FROM wallet_scan_history "
    "WHERE scan_ts >= strftime('%s','2026-08-31') ORDER BY wallet, scan_ts").fetchall()

latest = {}
for r in rows:
    latest[r["wallet"]] = r

passed = [r for r in latest.values() if r["gate_pass"] == 1]
print(f"unique wallets scanned today: {len(latest)} | latest-verdict PASS: {len(passed)}")
for r in passed:
    ts = datetime.datetime.fromtimestamp(
        r["scan_ts"], datetime.timezone(datetime.timedelta(hours=7))).strftime("%m-%d %H:%M")
    vol = r["volume_7d"] or 0
    r7 = r["realized_profit_7d"] or 0
    wr = r["winrate_7d"] if r["winrate_7d"] is not None else 0
    txs = r["txs_7d"] or 0
    print(f"  {r['wallet'][:14]:<16} {ts} {r['gate_reason'][:44]} "
          f"txs={txs} r7={r7:,.0f} wr={wr:.2f} vol={vol:,.0f}")

# how many of those are already in wallet_profiles tracked?
tracked = {x[0] for x in c.execute(
    "SELECT wallet FROM wallet_profiles WHERE track_enabled=1 AND is_smart_money=1")}
new = [r for r in passed if r["wallet"] not in tracked]
print(f"\nalready tracked: {len(passed) - len(new)} | NEW candidates: {len(new)}")
