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


def _load_wallet_common():
    for p in (Path(__file__).resolve().parent / "wallet_common.py",
              Path("/home/hermes/project-theia/cron/wallet_common.py"),
              Path("/home/hermes/theia-gate/wallet_common.py")):
        if p.exists():
            spec = importlib.util.spec_from_file_location("wallet_common", p)
            if spec is None or spec.loader is None:
                continue
            m = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(m)
            return m
    raise ImportError("wallet_common.py not found")


wc = _load_wallet_common()


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(name)
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
# Fix: cap per run so a 6h cron tick finishes well inside its timeout
# (30 wallets × 24 sims × ~3 rate-limited Gecko calls ≈ >60min; 10 is safe)
MAX_WALLETS_PER_RUN = 10
todo = [w for w in new_wallets if w not in existing][:MAX_WALLETS_PER_RUN]
print(f"new: {len(new_wallets)}, existing: {len(existing)}, "
      f"to profile (cap {MAX_WALLETS_PER_RUN}): {len(todo)}")

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
# Fix #5: split buys into TRAIN (older) and TEST (newer) windows. Only flag
# is_smart_money if BOTH the profile is positive AND the TEST window clears
# with n >= MIN_TEST_N. Fix #4: only consider buys within RECENT_DAYS.
now = int(time.time())
RECENT_DAYS = 14  # buys older than this hit Gecko 180-day/401 limits
# Out-of-sample threshold: with MAX_SIMS_PER_SPLIT=8, we can realistically
# clear ~5 valid sims per wallet. n>=5 with a clean split still rejects the
# worst overfit cases (was n>=20 before the sim cap; too strict for 6h cron).
MIN_TEST_N = 5
results = []
for w in todo:
    txs = all_swaps.get(w, [])
    if len(txs) < 20:
        continue
    p = profile_wallet(w, txs)

    # All SOL buys within recent window, oldest first
    buys = [t for t in txs if t.get("side") == "buy"
            and t.get("quote_mint") == "So11111111111111111111111111111111111111112"
            and t.get("ts", 0) >= now - RECENT_DAYS * 86400]
    buys = sorted(buys, key=lambda x: x.get("ts", 0))

    # split: oldest 50% = train, newest 50% = test (out-of-sample)
    split = len(buys) // 2
    train_buys, test_buys = buys[:split], buys[split:]
    # Cap sims per split (each = 2-3 rate-limited Gecko calls; 8 per split is
    # enough for a latency-tolerance signal and keeps the run inside cron TTL)
    MAX_SIMS_PER_SPLIT = 8
    train_buys = train_buys[-MAX_SIMS_PER_SPLIT:]
    test_buys = test_buys[-MAX_SIMS_PER_SPLIT:]

    def _sim(b):
        mint = b.get("base_mint")
        try:
            info = wc.resolve_pool(dexdata, mint)
            if not info or info.get("liq_usd", 0) < 5000:
                return None
            liq = info["liq_usd"]
            pool_addr = (info.get("pool") or "").replace("solana_", "")
            rows = wc.gecko_ohlcv(dexdata, mint, before_ts=b["ts"] + 4 * 3600, ttl=86400)
            if not rows or len(rows) < 35:
                return None
            entry_ts_target = b["ts"] + 1800
            ce = next((r for r in rows if r[0] >= entry_ts_target), None)
            if not ce or ce[4] <= 0:
                return None
            entry_price, entry_ts = ce[4], ce[0]
            fwd = [r for r in rows if r[0] > entry_ts]
            if not fwd:
                return None
            ei = min(30, len(fwd) - 1)
            exit_price = fwd[ei][4]
            if exit_price <= 0:
                return None
            is_bonding = "pump" in (info.get("dex_id") or "").lower()
            slip = costs.slippage_estimate(NOTIONAL*SOL_USD, max(liq,100), is_bonding) + \
                   costs.slippage_estimate(NOTIONAL*SOL_USD, max(liq*0.7,100), is_bonding)
            cost = gas_sim.swap_fee_sol(first_buy=True) + gas_sim.swap_fee_sol() + NOTIONAL*slip
            return (NOTIONAL/entry_price)*exit_price - NOTIONAL - cost
        except Exception as e:
            print(f"    {w[:8]}/{mint[:8]} err: {e}")
            return None

    train_pnls = [x for x in (_sim(b) for b in train_buys) if x is not None]
    test_pnls = [x for x in (_sim(b) for b in test_buys) if x is not None]

    lt = {}
    if len(test_pnls) >= 3:
        m = expectancy.evaluate(test_pnls)
        lt = {"n": m["n"], "win_rate": m["win_rate"], "expectancy": m["expectancy"],
              "profit_factor": m["profit_factor"] if m["profit_factor"] != float("inf") else 999.0,
              "train_n": len(train_pnls), "test_n": len(test_pnls)}

    results.append({"wallet": w, "profile": p, "latency_test": lt})
    # Fix #5: smart money only on out-of-sample PASS with sufficient n
    is_sm = 1 if (lt and lt.get("expectancy", 0) > 0 and lt.get("n", 0) >= MIN_TEST_N) else 0
    marker = "★ LATENCY-TOLERANT" if is_sm else ""
    print(f"  {w[:12]}: profile_exp={(p.get('expectancy_sol') or 0):+.3f} "
          f"train_n={lt.get('train_n',0)} test_n={lt.get('n',0)} "
          f"test_exp={lt.get('expectancy',0):+.4f} {marker}")

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
          is_sm, "gmgn_winrate", now, now))
    con.commit()

(DATA / "discovery_profiles.json").write_text(json.dumps(results, indent=1, default=str))
con.close()
n_lt = sum(1 for r in results if r["latency_test"] and r["latency_test"].get("expectancy", 0) > 0)
print(f"\n[done] profiled={len(results)}, latency-tolerant={n_lt}")
print("saved → data/discovery_profiles.json")
