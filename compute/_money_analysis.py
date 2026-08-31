#!/usr/bin/env python3
"""Follow-the-money: analyze + scan-history cross-check (no API), plus a
bounded refetch of the strongest unknown wallets for the persistence check.

Builds on _money_trace.json (290 discovered wallets, 0 known). To test gate
predictive validity on the REAL trading wallets (proxies), we need their GMGN
stats — bounded refetch: top 6 unknowns by weight, 1 call each (7d only).
"""
import json
import sqlite3
from pathlib import Path

DB = "/home/hermes/.hermes/theia/theia.db"
trace = json.load(open("/home/hermes/project-theia/compute/_money_trace.json"))
unknown = json.load(open("/home/hermes/project-theia/compute/_money_unknowns.json"))

con = sqlite3.connect(DB)
con.row_factory = sqlite3.Row

# weight per discovered wallet (fee-payer + token-sender + sol-in appearances)
weight = {}
for tag, d in trace["whales"].items():
    for p, n in (d.get("fee_payers") or {}).items():
        weight[p] = weight.get(p, 0) + n
    for p, n in (d.get("token_senders") or {}).items():
        weight[p] = weight.get(p, 0) + n
    for p, v in (d.get("sol_in") or {}).items():
        weight[p] = weight.get(p, 0) + v
for key, d in trace.get("hop2", {}).items():
    for p, n in (d.get("own_payers") or {}).items():
        weight[p] = weight.get(p, 0) + n

# split discovered into: in-scan-history (with stats) vs never-scanned
known, unknown = [], []
discovered_all = list(weight)
for addr in discovered_all:
    sh = con.execute(
        "SELECT scan_ts, gate_pass, winrate_7d, txs_7d, realized_profit_7d, volume_7d, tags "
        "FROM wallet_scan_history WHERE wallet=? ORDER BY scan_ts DESC LIMIT 1",
        (addr,)).fetchone()
    prof = con.execute(
        "SELECT is_smart_money, track_enabled FROM wallet_profiles WHERE wallet=?",
        (addr,)).fetchone()
    if sh:
        known.append((addr, weight.get(addr, 0), dict(sh), dict(prof) if prof else {}))
    else:
        unknown.append((addr, weight.get(addr, 0)))

print(f"discovered: {len(discovered_all)} | in scan history: {len(known)} | never scanned: {len(unknown)}")
print("\n== KNOWN wallets (have GMGN stats from our daily scans) ==")
known.sort(key=lambda kv: -kv[1])
for addr, wt, sh, prof in known[:15]:
    ts = sh["scan_ts"]
    track = " TRACKED" if prof.get("track_enabled") else ""
    print(f"  {addr[:16]:<18} weight={wt:>5.1f} gate={sh['gate_pass']} wr7={sh['winrate_7d']} "
          f"r7={sh['realized_profit_7d']:.0f} txs7={sh['txs_7d']} vol7={sh['volume_7d']:.0f} "
          f"tags={(sh['tags'] or '')[:30]}{track}")

print("\n== UNKNOWN wallets by weight (top 15) ==")
unknown.sort(key=lambda kv: -kv[1])
for addr, wt in unknown[:15]:
    print(f"  {addr[:16]:<18} weight={wt:>5.1f}")

# gate v2 check on known ones: would they pass?
print("\n== gate v2 check on KNOWN wallets ==")
def gv2(sh):
    wr = sh["winrate_7d"] or 0
    txs = sh["txs_7d"] or 0
    r7 = sh["realized_profit_7d"] or 0
    vol = sh["volume_7d"] or 0
    tags = set((sh["tags"] or "").replace("[", "").replace("]", "").replace('"', "").split(","))
    tags = {t.strip() for t in tags if t.strip()}
    if tags & {"wash_trader", "bot", "bundler", "dev", "sniper", "mev"}:
        return False, "bad_tag"
    if wr < 0.30:
        return False, f"wr7={wr:.2f}"
    if wr > 0.80 and txs < 500:
        return False, "scalper"
    if txs < 500:
        return False, f"txs7={txs}"
    if r7 < 10000:
        return False, f"rPnl7d={r7:.0f}"
    if vol < 100000:
        return False, f"vol7d={vol:.0f}"
    return True, "ok"

for addr, wt, sh, prof in known[:15]:
    ok, why = gv2(sh)
    print(f"  {addr[:16]:<18} gv2={ok} ({why}) weight={wt:.1f}")
con.close()