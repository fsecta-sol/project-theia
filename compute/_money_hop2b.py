#!/usr/bin/env python3
"""Follow-the-money hop 2b: cross-check discovered wallets against scan history."""
import datetime
import json
import sqlite3
from pathlib import Path

TZ = datetime.timezone(datetime.timedelta(hours=7))
DB = "/home/hermes/.hermes/theia/theia.db"

trace = json.load(open("/home/hermes/project-theia/compute/_money_trace.json"))
discovered = set()
for tag, d in trace["whales"].items():
    discovered |= set(d.get("fee_payers") or {}) | set(d.get("sol_in") or {}) | set(d.get("token_senders") or {})
for key, d in trace.get("hop2", {}).items():
    discovered |= set(d.get("own_payers") or {})
discovered.discard("")

con = sqlite3.connect(DB)
con.row_factory = sqlite3.Row

print(f"discovered wallets total: {len(discovered)}")
hits = 0
rows = []
for addr in sorted(discovered):
    sh = con.execute(
        "SELECT scan_ts, gate_pass, gate_reason, winrate_7d, txs_7d, realized_profit_7d, "
        "volume_7d, tags FROM wallet_scan_history WHERE wallet = ? ORDER BY scan_ts DESC LIMIT 1",
        (addr,)).fetchone()
    prof = con.execute(
        "SELECT is_smart_money, track_enabled, source FROM wallet_profiles WHERE wallet = ?",
        (addr,)).fetchone()
    if sh:
        hits += 1
        ts = datetime.datetime.fromtimestamp(sh["scan_ts"], TZ).strftime("%m-%d %H:%M")
        track = " TRACKED" if (prof and prof["track_enabled"]) else ""
        print(f"  {addr[:16]:<18} scan@{ts} gate={sh['gate_pass']} wr7={sh['winrate_7d']} "
              f"r7={sh['realized_profit_7d']:.0f} txs7={sh['txs_7d']} "
              f"tags={(sh['tags'] or '')[:36]}{track}")
    else:
        rows.append(addr)
print(f"  ({hits}/{len(discovered)} discovered wallets already in our labeled scan history)")
print(f"  unknown wallets (never scanned): {len(rows)}")
for a in rows[:8]:
    print(f"    {a[:16]}")

# hop 3: scan the promising unknowns (fee-payers with real SWAP counts) via scan_history-style refetch?
# Just list the strongest unknowns by their tx weight
print("\n== strongest unknown wallets (fee-payer weight in whale txs) ==")
weight = {}
for tag, d in trace["whales"].items():
    for p, n in (d.get("fee_payers") or {}).items():
        weight[p] = weight.get(p, 0) + n
    for p, n in (d.get("token_senders") or {}).items():
        weight[p] = weight.get(p, 0) + n
    for p, v in (d.get("sol_in") or {}).items():
        weight[p] = weight.get(p, 0) + v
strong = [(p, w) for p, w in weight.items() if p not in [x for x in rows[:0]] and p not in discovered.intersection(set())]
strong_unknown = [(p, w) for p, w in weight.items() if p in rows]
strong_unknown.sort(key=lambda kv: -kv[1])
for p, w in strong_unknown[:10]:
    print(f"  {p[:16]:<18} weight={w:.1f}")
con.close()
json.dump({"unknown": rows, "strong_unknown": strong_unknown[:20]},
          open("/home/hermes/project-theia/compute/_money_trace_unknowns.json", "w"))
print("\nsaved _money_trace_unknowns.json")