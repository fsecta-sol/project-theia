#!/usr/bin/env python3
"""Task 7: Backtest harness — follow 8 latency-tolerant wallets together.

Aggregate their recent buys, apply our filters (liq, momentum, volume, price cap),
follow at T+30min, hold 30min. Decompose by wallet to check no single-point failure.

This is the VALIDATE-FIRST gate for the whole pipeline: does the combined
latency-tolerant cluster clear positive expectancy with no single-wallet dominance?
"""
import json
import sys
import time
from pathlib import Path

DATA = Path("/home/hermes/theia-gate/data")
sys.path.insert(0, "/home/hermes/project-theia")

from compute import costs, expectancy, gas_sim  # noqa: E402

NOTIONAL = 0.5
SOL_USD = json.loads((DATA / "sol_usd.json").read_text())["sol_usd"]
WSOL = "So11111111111111111111111111111111111111112"

# Load swaps for all latency-tolerant wallets
swaps = json.loads((DATA / "discovery_swaps.json").read_text())

# Load our 8 latency-tolerant wallets from DB
import sqlite3
con = sqlite3.connect("/home/hermes/.hermes/theia/theia.db")
lt_wallets = [r[0] for r in con.execute(
    "SELECT wallet FROM wallet_profiles WHERE is_smart_money=1"
).fetchall()]
con.close()
print(f"tracked wallets: {len(lt_wallets)}")

# Load dexdata for OHLCV + pool
import importlib.util
DEPLOY = Path("/home/hermes/.hermes/theia/mcp")
sys.path.insert(0, str(DEPLOY / "common"))
def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m
dexdata = load("dexdata", DEPLOY / "theia-dexdata" / "server.py")

# Collect recent buys (last 7 days) for each tracked wallet
now = int(time.time())
WINDOW = 7 * 24 * 3600
candidates = []
for w in lt_wallets:
    txs = swaps.get(w, [])
    for tx in txs:
        if tx.get("side") != "buy":
            continue
        if tx.get("quote_mint") != WSOL:
            continue
        ts = tx.get("ts", 0)
        if now - ts > WINDOW:
            continue
        candidates.append({
            "wallet": w,
            "mint": tx.get("base_mint"),
            "buy_ts": ts,
            "signal_sol": tx.get("quote_qty", 0),
            "exec_price": tx.get("exec_price", 0),
        })

print(f"candidates (7d window): {len(candidates)}")

# Simulate follow strategy
def simulate(c):
    mint = c["mint"]
    try:
        pools = dexdata.token_pools(mint)
    except Exception:
        return None
    if not pools:
        return None
    pool = pools[0]
    attr = pool.get("attributes", {})
    try:
        liq = float(attr.get("reserve_in_usd") or 0)
    except (TypeError, ValueError):
        liq = 0
    if liq < 5000:
        return None
    is_bonding = "pump" in (attr.get("dex_id") or "").lower()
    pool_addr = (pool.get("id") or "").replace("solana_", "")
    try:
        rows = dexdata.pool_ohlcv(pool_addr, timeframe="minute", aggregate=1,
                                  limit=1000, before_timestamp=c["buy_ts"] + 4*3600,
                                  currency="token")
    except Exception:
        return None
    if not rows or len(rows) < 35:
        return None

    # Entry at T+30min (close of first candle >= buy_ts + 1800)
    entry_target = c["buy_ts"] + 1800
    ce = next((r for r in rows if r[0] >= entry_target), None)
    if not ce or ce[4] <= 0:
        return None
    entry_price, entry_ts = ce[4], ce[0]

    # Filters: momentum + price cap
    idx = next(i for i, r in enumerate(rows) if r[0] == entry_ts)
    if idx >= 10 and rows[idx][4] <= rows[idx-10][4]:
        return None  # no momentum
    if c["exec_price"] > 0 and entry_price > c["exec_price"] * 1.5:
        return None  # chasing

    # Exit at T+30min (30 min after entry)
    fwd = [r for r in rows if r[0] > entry_ts]
    if not fwd:
        return None
    ei = min(30, len(fwd) - 1)
    exit_price = fwd[ei][4]
    if exit_price <= 0:
        return None

    slip = costs.slippage_estimate(NOTIONAL*SOL_USD, max(liq,100), is_bonding) + \
           costs.slippage_estimate(NOTIONAL*SOL_USD, max(liq*0.7,100), is_bonding)
    cost = gas_sim.swap_fee_sol(first_buy=True) + gas_sim.swap_fee_sol() + NOTIONAL*slip
    pnl = (NOTIONAL/entry_price)*exit_price - NOTIONAL - cost
    return {"wallet": c["wallet"], "mint": mint, "pnl": pnl, "liq": liq}

print("simulating... (this hits Gecko per candidate, ~6s each)")
trades = []
for i, c in enumerate(candidates):
    t = simulate(c)
    if t:
        trades.append(t)
        print(f"  [{i+1}/{len(candidates)}] {c['wallet'][:10]} {c['mint'][:10]} pnl={t['pnl']:+.4f}")
    time.sleep(6)  # gecko throttle

# Aggregate results
pnls = [t["pnl"] for t in trades]
m = expectancy.evaluate(pnls)
print(f"\n{'='*70}")
print(f"AGGREGATE (8 wallets, follow 30min late, 30min hold, liq>$5k):")
print(f"n={m['n']}, win={m['win_rate']:.1%}, expectancy={m['expectancy']:+.4f}, "
      f"PF={m['profit_factor']:.2f}, total={m['total']:+.3f} SOL")
print(f"{'='*70}")

# Decompose by wallet
print(f"\n{'wallet':<16} | {'n':>3} | {'win%':>6} | {'exp':>9} | {'total':>8} | {'share':>6}")
print("-" * 65)
from collections import defaultdict
by_w = defaultdict(list)
for t in trades:
    by_w[t["wallet"]].append(t["pnl"])
for w, ps in sorted(by_w.items(), key=lambda x: -sum(x[1])):
    mm = expectancy.evaluate(ps)
    share = sum(ps) / sum(pnls) * 100 if sum(pnls) else 0
    pf = mm["profit_factor"]
    pf_s = f"{pf:.2f}" if pf != float("inf") else "inf"
    print(f"{w[:14]:<16} | {mm['n']:>3} | {mm['win_rate']*100:>5.1f}% | "
          f"{mm['expectancy']:>+8.4f} | {mm['total']:>+7.3f} | {share:>5.1f}%")

# Concentration check
top_share = max((sum(ps) / sum(pnls) * 100) for ps in by_w.values()) if pnls else 0
print(f"\nTop wallet share: {top_share:.1f}% {'⚠️ single-point failure risk' if top_share > 50 else '✅ diversified'}")

(DATA / "cluster_backtest.json").write_text(json.dumps({
    "metrics": m, "trades": trades,
    "by_wallet": {w: expectancy.evaluate(ps) for w, ps in by_w.items()},
}, indent=1, default=str))
print(f"saved → data/cluster_backtest.json")
