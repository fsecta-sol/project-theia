#!/usr/bin/env python3
"""Summarize suqh decode: owner-delta rate + proxy-trading verdict."""
import json

W = "suqh5sHtr8HyJ7q8scBimULPkPpA557prMG47xCHQfK"
txs = json.load(open("/home/hermes/project-theia/compute/_suqh_enhanced.json"))
n_owner = 0
for t in txs:
    hit = False
    for x in (t.get("accountData") or []):
        for ch in (x.get("tokenBalanceChanges") or []):
            if ch.get("userAccount") == W:
                hit = True
                break
        if hit:
            break
    if hit:
        n_owner += 1
print(f"txs={len(txs)}, owner-delta txs={n_owner} ({100 * n_owner / len(txs):.1f}%)")

lots = json.load(open("/home/hermes/project-theia/compute/_suqh_lots.json"))
real = [l for l in lots if l["sol_out"] > 0.01 or l["sol_in"] > 0.01]
print(f"lots with real SOL leg (>0.01 SOL): {len(real)}")
for l in real:
    print(f"  {l['side']:<5} {l['mint'][:8]} qty={l['qty']:>12,.0f} sol_out={l['sol_out']:.3f} sol_in={l['sol_in']:.3f}")
print()
print("=> suqh = proxy-trading pattern: the wallet itself is mostly a RECEIVER;")
print("   real trades ride a different payer wallet. GMGN's +105k for suqh is")
print("   their attribution, not reproducible from this wallet's own balance flow.")