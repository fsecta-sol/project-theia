#!/usr/bin/env python3
"""ACTUAL PnL accounting for whale-copy and whale-own trades.

Two ledgers, deterministic, from stored data:
1. COPY-TRADE ledger: our paper entry at whale-buy-ts+30m, exit 30 candles
   later, notional 0.5 SOL, costs from compute libs (gas + slippage).
   -> already in _token_trace_pnl.json; recompute aggregates from raw rows.
2. WHALE-OWN ledger: whale's actual SOL in/out per mint from decoded lots
   (their real fill prices are unknown; their OWN PnL approximated as
   SOL_in - SOL_out per mint, which is what 'realized' means here since
   whales buy/sell SOL against tokens). This is the whale's realized cash
   flow — no simulation, no notional, no costs assumption.
3. Comparison table per mint: our copy PnL vs whale's actual net.
"""
import json
import sys

sys.path.insert(0, "/home/hermes/project-theia")

from compute import expectancy  # noqa: E402

NOTIONAL = 0.5
rows = json.load(open("/home/hermes/project-theia/compute/_token_trace_pnl.json"))
trace = json.load(open("/home/hermes/project-theia/compute/_token_trace.json"))
agg = trace["agg"]
v2 = json.load(open("/home/hermes/project-theia/compute/_whale_lots_v2.json"))
suqh = json.load(open("/home/hermes/project-theia/compute/_suqh_lots.json"))

# ── 1. copy-trade ledger aggregates ──
pnls = [r["pnl_copy_net"] for r in rows]
m = expectancy.evaluate(pnls)
print("== COPY-TRADE ledger (our paper sim, 0.5 SOL notional, T+30m, 30m hold, net costs) ==")
print(f"  trades={m['n']}  total={m['total']:+.4f} SOL  expectancy={m['expectancy']:+.4f}  "
      f"PF={m['profit_factor']:.3f}  win={m['win_rate']:.2f}")
wins = sum(p for p in pnls if p > 0)
losses = sum(p for p in pnls if p < 0)
print(f"  gross wins={wins:+.4f}  gross losses={losses:+.4f}")

# ── 2. whale-own actual cash flow per mint ──
def whale_flows(mint, whale_tag):
    """SOL in (sell proceeds) and out (buy spend) for a whale on a mint."""
    sol_in = sol_out = 0.0
    n_in = n_out = 0
    for w, dd in v2.items():
        tag = {'2fg5QD1eD7rzNNCsvnhmXFm5hqNgwTTG8p7kQ6f3rx6f': '2fg5',
               'ardinRsN1mNYVeoJWTBsWeYeXvuR9UUDGMsCDKpb6AT': 'ardin',
               '6G8Cu53PRgm5aPHxMaZRguYHJfaNxmnmgoR129cKMvJk': '6G8'}.get(w, w[:6])
        if tag != whale_tag:
            continue
        for l in dd.get("lots", []):
            if l["mint"] != mint:
                continue
            if l["side"] == "buy" and l["sol_out"] > 0.01:
                sol_out += l["sol_out"]
                n_out += 1
            if l["side"] == "sell" and l["sol_in"] > 0.01:
                sol_in += l["sol_in"]
                n_in += 1
    if whale_tag == "suqh":
        for l in suqh:
            if l["mint"] != mint:
                continue
            if l["side"] == "buy" and l["sol_out"] > 0.01:
                sol_out += l["sol_out"]
                n_out += 1
            if l["side"] == "sell" and l["sol_in"] > 0.01:
                sol_in += l["sol_in"]
                n_in += 1
    return sol_in, sol_out, n_in, n_out


print()
print("== WHALE-OWN actual ledger (real SOL in/out per mint, from decoded lots) ==")
print(f"{'whale':<5} {'mint':<11} {'SOLout':>7} {'SOLin':>7} {'nBuy':>4} {'nSell':>5} {'whaleNet':>9} {'ourCopy':>9} {'delta':>8}")
by_whale_net = {}
comparison = []
for r in rows:
    mint = r["mint"]
    w = r["whale"]
    si, so, n_in, n_out = whale_flows(mint, w)
    net = si - so
    our = r["pnl_copy_net"]
    comparison.append({"whale": w, "mint": mint, "whale_sol_out": so, "whale_sol_in": si,
                       "whale_net": net, "our_copy_net": our, "delta_whale_minus_us": net - our})
    print(f"{w:<5} {mint[:9]:<11} {so:>7.2f} {si:>7.2f} {n_out:>4} {n_in:>5} {net:>+9.2f} {our:>+9.3f} {net-our:>+8.2f}")

# whale totals (cash-flow actuals over the decoded window)
tot_in = sum(c["whale_sol_in"] for c in comparison)
tot_out = sum(c["whale_sol_out"] for c in comparison)
tot_net = sum(c["whale_net"] for c in comparison)
print(f"\n  whale TOTAL (these 12 mints): out={tot_out:.2f} in={tot_in:.2f} net={tot_net:+.2f} SOL")
our_total = sum(c["our_copy_net"] for c in comparison)
print(f"  our copy TOTAL: {our_total:+.4f} SOL (0.5 SOL notional each)")

# whale-own full ledger beyond the top-12 (all real-LEG mints)
print()
print("== whale-own FULL ledger (every whale, every mint w/ real SOL legs, all mints decoded) ==")
full_in = full_out = 0.0
n_mints = 0
from collections import defaultdict
full = defaultdict(lambda: {"in": 0.0, "out": 0.0})
for w, dd in v2.items():
    tag = {'2fg5QD1eD7rzNNCsvnhmXFm5hqNgwTTG8p7kQ6f3rx6f': '2fg5',
           'ardinRsN1mNYVeoJWTBsWeYeXvuR9UUDGMsCDKpb6AT': 'ardin',
           '6G8Cu53PRgm5aPHxMaZRguYHJfaNxmnmgoR129cKMvJk': '6G8'}.get(w, w[:6])
    for l in dd.get("lots", []):
        if l["sol_out"] > 0.01 or l["sol_in"] > 0.01:
            full[tag]["out" if l["side"] == "buy" else "in"] += max(l["sol_out"], l["sol_in"])
for l in suqh:
    if l["sol_out"] > 0.01 or l["sol_in"] > 0.01:
        full["suqh"]["out" if l["side"] == "buy" else "in"] += max(l["sol_out"], l["sol_in"])
print(f"{'whale':<5} {'SOL out (buys)':>15} {'SOL in (sells)':>15} {'net':>10}")
for w in ("suqh", "2fg5", "ardin", "6G8"):
    d = full.get(w, {"in": 0, "out": 0})
    print(f"{w:<5} {d['out']:>15.2f} {d['in']:>15.2f} {d['in']-d['out']:>+10.2f}")

json.dump({"copy": m, "comparison": comparison},
          open("/home/hermes/project-theia/compute/_pnl_actual.json", "w"), indent=1)
print("\nsaved _pnl_actual.json")