#!/usr/bin/env python3
"""Wallet pipeline monitor — deterministic exit for open paper trades.

Runs every 5 min. For each open position:
  - refresh price via pool_ohlcv
  - evaluate exit_engine (hard stop -35%, TP ladder 2x/4x, 30min time stop)
  - on exit: close trade (state='closed'), archive realized pnl

0 LLM. Uses compute/exit_engine for all exit decisions.
"""
import importlib.util
import json
import sqlite3
import sys
import time
from pathlib import Path

DEPLOY = Path("/home/hermes/.hermes/theia/mcp")
DB = Path("/home/hermes/.hermes/theia/theia.db")
sys.path.insert(0, str(DEPLOY / "common"))
sys.path.insert(0, "/home/hermes/project-theia")

from compute import exit_engine, gas_sim  # noqa: E402


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


dexdata = load("dexdata", DEPLOY / "theia-dexdata" / "server.py")

con = sqlite3.connect(DB)
open_trades = con.execute(
    "SELECT trade_id, mint, hypothesis_id, entry_ts, entry_price, size_sol FROM paper_trades WHERE state='open'"
).fetchall()

if not open_trades:
    print("[monitor] no open positions")
    con.close()
    sys.exit(0)

now = int(time.time())
closed = 0
for trade_id, mint, hyp_id, entry_ts, entry_price, size_sol in open_trades:
    try:
        pools = dexdata.token_pools(mint)
        if not pools:
            print(f"[monitor] {mint[:12]} no pool — keep open")
            continue
        pool_addr = (pools[0].get("id") or "").replace("solana_", "")
        rows = dexdata.pool_ohlcv(pool_addr, timeframe="minute", aggregate=1,
                                  limit=1000, currency="token")
        time.sleep(6)
    except Exception as e:
        print(f"[monitor] {mint[:12]} fetch err {e} — keep open")
        continue

    if not rows:
        continue

    # Forward path from entry
    forward = [[r[0], r[1], r[2], r[3], r[4], r[5]] for r in rows if r[0] > entry_ts]
    if not forward:
        continue

    # Exit decision with 30-min time stop
    params = {"hard_stop": -0.35, "tp_ladder": [(2.0, 0.5), (4.0, 0.5)],
              "trail_drop": 0.25, "time_stop_secs": 30 * 60}
    ex = exit_engine.simulate_exit(entry_price, entry_ts, forward, params)
    exit_price = ex["realized_price"]
    exit_reason = ex["final_reason"]

    # Only close on a real exit signal (not path_end = still holding)
    if exit_reason in ("path_end", "none"):
        continue

    tokens = size_sol / entry_price if entry_price else 0
    raw_pnl = tokens * exit_price - size_sol
    gas = gas_sim.swap_fee_sol()
    net_pnl = raw_pnl - gas
    roi = net_pnl / size_sol if size_sol else 0
    hold_secs = ex.get("hold_secs", now - entry_ts)

    con.execute("UPDATE paper_trades SET state='closed' WHERE trade_id=?", (trade_id,))
    con.execute("""
        INSERT OR REPLACE INTO archives
        (trade_id, mint, hypothesis_id, entry_ts, exit_ts, hold_secs,
         realized_pnl_sol, roi, expectancy_contrib, gas_sol_total, slippage_total,
         exit_reason, created_ts)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (trade_id, mint, hyp_id, entry_ts, now, hold_secs,
          net_pnl, roi, net_pnl, gas, 0.0, exit_reason, now))
    closed += 1
    print(f"[exit] {mint[:12]} {exit_reason} pnl={net_pnl:+.4f} SOL "
          f"roi={roi:+.1%} hold={hold_secs//60}m")

con.commit()
n_open = con.execute("SELECT COUNT(*) FROM paper_trades WHERE state='open'").fetchone()[0]
con.close()
print(f"[monitor] closed={closed}, remaining open={n_open}")
