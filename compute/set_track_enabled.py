#!/usr/bin/env python3
"""Set pipeline tracking based on FRESH GMGN rPnl7d/rPnl30d (authoritative).

2026-08-31 fix: previous filter used own-swap FIFO winrate which was WRONG
(4 wallets with huge GMGN PnL were wrongly disabled). Now filter on GMGN
realized_profit: require rPnl7d > 0 AND rPnl30d > 0 (consistency, not a
one-run-wonder) — this is the same spirit as the source-2 GMGN gate.
"""
import json
import glob
import sqlite3
from pathlib import Path

DB = Path.home() / ".hermes/theia/theia.db"
DATA = Path.home() / "theia-gate/data"

# read fresh refetch results
stats = {}
for f in sorted(glob.glob(str(DATA / "gmgn_refetch_*.json"))):
    try:
        d = json.load(open(f))
        w = Path(f).stem.split("_")[-1]
        i7 = ((d.get("7d") or {}).get("data") or {}).get("data") or {}
        i30 = ((d.get("30d") or {}).get("data") or {}).get("data") or {}
        stats[w] = {
            "rPnl7d": i7.get("realized_profit_7d") or 0,
            "rPnl30d": i30.get("realized_profit_30d") or 0,
        }
    except Exception:
        continue

con = sqlite3.connect(DB)
con.execute("UPDATE wallet_profiles SET track_enabled=0")
kept = []
disabled = []
for (w,) in con.execute("SELECT wallet FROM wallet_profiles WHERE is_smart_money=1"):
    # file names are truncated to 12 chars; match by prefix
    s = next((v for k, v in stats.items() if w.startswith(k) or k.startswith(w[:12])), None)
    if not s:
        disabled.append((w[:12], 0, 0, "no_refetch"))
        continue
    r7, r30 = s["rPnl7d"], s["rPnl30d"]
    if r7 > 0 and r30 > 0:
        con.execute("UPDATE wallet_profiles SET track_enabled=1 WHERE wallet=?", (w,))
        kept.append((w[:12], r7, r30))
    else:
        disabled.append((w[:12], r7, r30, "neg_or_zero"))
con.commit()

print(f"track_enabled=1: {len(kept)} wallets (rPnl7d>0 AND rPnl30d>0)")
for w, r7, r30 in sorted(kept, key=lambda x: -x[1]):
    print(f"  {w:<14} rPnl7d={r7:>10.0f} rPnl30d={r30:>10.0f}")
print("\ndisabled:")
for w, r7, r30, why in disabled:
    print(f"  {w:<14} rPnl7d={r7:>10.0f} rPnl30d={r30:>10.0f}  {why}")
con.close()