#!/usr/bin/env python3
"""Profile newly discovered wallets: fetch swaps → profile → latency-tolerance backtest.

Only for wallets NOT already in DB. Respects free-tier budget: max 30 new wallets
per run, pages=5 per wallet (~50 txs each).
"""
import importlib.util
import json
import sqlite3
import sys
import time
from pathlib import Path

DATA = Path("/home/hermes/theia-gate/data")
DEPLOY = Path("/home/hermes/.hermes/theia/mcp")
sys.path.insert(0, str(DEPLOY / "common"))
sys.path.insert(0, "/home/hermes/project-theia")

from compute.wallet_profiler import profile_wallet  # noqa: E402
from compute import costs, expectancy, gas_sim  # noqa: E402


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


chainrpc = load("chainrpc", DEPLOY / "theia-chainrpc" / "server.py")
dexdata = load("dexdata", DEPLOY / "theia-dexdata" / "server.py")

disc = json.loads((DATA / "discovered_wallets.json").read_text())
new_wallets = [w["address"] for w in disc["gmgn"]]

# Skip wallets already profiled
con = sqlite3.connect("/home/hermes/.hermes/theia/theia.db")
existing = {r[0] for r in con.execute("SELECT wallet FROM wallet_profiles")}
todo = [w for w in new_wallets if w not in existing][:30]
print(f"new: {len(new_wallets)}, existing: {len(existing)}, to profile: {len(todo)}")

# Fetch swaps + profile
swaps_cache = DATA / "discovery_swaps.json"
all_swaps = json.loads(swaps_cache.read_text()) if swaps_cache.exists() else {}
SOL_USD = json.loads((DATA / "sol_usd.json").read_text())["sol_usd"]
NOTIONAL = 0.5

for w in todo:
    if w in all_swaps and all_swaps[w]:
        continue
    try:
        all_swaps[w] = chainrpc.wallet_swaps(w, pages=5)
        print(f"  {w[:12]}: {len(all_swaps[w])} txs")
    except Exception as e:
        print(f"  {w[:12]} ERROR: {e}")
        all_swaps[w] = []
    time.sleep(0.4)
swaps_cache.write_text(json.dumps(all_swaps))

# Profile each, then latency-tolerance backtest on their recent SOL buys
now = int(time.time())
results = []
for w in todo:
    txs = all_swaps.get(w, [])
    if len(txs) < 10:
        continue
    p = profile_wallet(w, txs)
    if (p.get("expectancy_sol") or 0) <= 0:
        continue

    # Latency-tolerance: take their last 15 SOL buys, simulate follow +30min, hold 30m
    buys = [t for t in txs if t.get("side") == "buy"
            and t.get("quote_mint") == "So11111111111111111111111111111111111111112"]
    buys = sorted(buys, key=lambda x: -x.get("ts", 0))[:15]

    pnls = []
    for b in buys:
        mint = b.get("base_mint")
        try:
            # find pool
            pools = dexdata.token_pools(mint)
            if not pools:
                continue
            pool = pools[0]
            attr = pool.get("attributes", {})
            try:
                liq = float(attr.get("reserve_in_usd") or 0)
            except (TypeError, ValueError):
                liq = 0
            if liq < 5000:
                continue
            pool_addr = (pool.get("id") or "").replace("solana_", "")
            rows = dexdata.pool_ohlcv(pool_addr, timeframe="minute", aggregate=1,
                                      limit=1000, before_timestamp=b["ts"] + 4*3600,
                                      currency="token")
            if not rows or len(rows) < 35:
                continue
            entry_ts_target = b["ts"] + 1800
            ce = next((r for r in rows if r[0] >= entry_ts_target), None)
            if not ce or ce[4] <= 0:
                continue
            entry_price, entry_ts = ce[4], ce[0]
            fwd = [r for r in rows if r[0] > entry_ts]
            if not fwd:
                continue
            ei = min(30, len(fwd) - 1)
            exit_price = fwd[ei][4]
            if exit_price <= 0:
                continue
            is_bonding = "pump" in (attr.get("dex_id") or "").lower()
            slip = costs.slippage_estimate(NOTIONAL*SOL_USD, max(liq,100), is_bonding) + \
                   costs.slippage_estimate(NOTIONAL*SOL_USD, max(liq*0.7,100), is_bonding)
            cost = gas_sim.swap_fee_sol(first_buy=True) + gas_sim.swap_fee_sol() + NOTIONAL*slip
            pnls.append((NOTIONAL/entry_price)*exit_price - NOTIONAL - cost)
            time.sleep(6)  # gecko throttle
        except Exception as e:
            print(f"    {w[:8]}/{mint[:8]} err: {e}")
            time.sleep(2)

    lt = {}
    if len(pnls) >= 3:
        m = expectancy.evaluate(pnls)
        lt = {"n": m["n"], "win_rate": m["win_rate"], "expectancy": m["expectancy"],
              "profit_factor": m["profit_factor"] if m["profit_factor"] != float("inf") else 999.0}

    results.append({"wallet": w, "profile": p, "latency_test": lt})
    marker = "★ LATENCY-TOLERANT" if lt and lt.get("expectancy", 0) > 0 else ""
    print(f"  {w[:12]}: profile_exp={p.get('expectancy_sol',0):+.3f} "
          f"latency_n={lt.get('n',0)} latency_exp={lt.get('expectancy',0):+.4f} {marker}")

    # Persist
    con.execute("""
        INSERT OR REPLACE INTO wallet_profiles
        (wallet, first_seen_ts, last_active_ts, total_trades, total_buys, total_sells,
         unique_tokens, median_buy_sol, mean_buy_sol, median_hold_min, median_pnl_pct,
         win_rate, profit_factor, expectancy_sol, pattern_cluster, is_smart_money, source,
         created_ts, updated_ts)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (w, p.get("first_seen_ts"), p.get("last_active_ts"), p.get("total_trades", 0),
          p.get("total_buys", 0), p.get("total_sells", 0), p.get("unique_tokens", 0),
          p.get("median_buy_sol"), p.get("mean_buy_sol"), p.get("median_hold_min"),
          p.get("median_pnl_pct"), p.get("win_rate"),
          (p.get("profit_factor") or 0) if p.get("profit_factor") != float("inf") else 999.0,
          p.get("expectancy_sol"), p.get("pattern_cluster", "unknown"),
          1 if lt and lt.get("expectancy", 0) > 0 else 0, "gmgn_winrate", now, now))
    con.commit()

(DATA / "discovery_profiles.json").write_text(json.dumps(results, indent=1, default=str))
con.close()
n_lt = sum(1 for r in results if r["latency_test"] and r["latency_test"].get("expectancy", 0) > 0)
print(f"\n[done] profiled={len(results)}, latency-tolerant={n_lt}")
print("saved → data/discovery_profiles.json")
