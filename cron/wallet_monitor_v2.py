#!/usr/bin/env python3
"""Wallet pipeline monitor v2 — deterministic exit with shared helpers.

Fix #2 (flock single-instance), #3 (cached OHLCV), #7 (pool fallback), #10
(latency + concentration stats in report). 0 LLM.
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

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))


def _load_wallet_common():
    for p in (HERE / "wallet_common.py",
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
gecko_ohlcv = wc.gecko_ohlcv
resolve_pool = wc.resolve_pool
script_lock = wc.script_lock

from compute import exit_engine, gas_sim  # noqa: E402


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(name)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


with script_lock("wallet_monitor"):
    dexdata = load("dexdata", DEPLOY / "theia-dexdata" / "server.py")
    con = sqlite3.connect(DB)
    open_trades = con.execute(
        "SELECT trade_id, mint, hypothesis_id, entry_ts, entry_price, size_sol "
        "FROM paper_trades WHERE state='open'"
    ).fetchall()

    if not open_trades:
        print("[monitor] no open positions")
        con.close()
        sys.exit(0)

    now = int(time.time())
    closed = 0
    for trade_id, mint, hyp_id, entry_ts, entry_price, size_sol in open_trades:
        rows = []
        try:
            rows = gecko_ohlcv(dexdata, mint, before_ts=0, ttl=60)  # cached 60s
        except Exception as e:
            print(f"[monitor] {mint[:12]} ohlcv err {e} — fallback to spot")
        if not rows:
            # Fallback (fix #7): fresh pump.fun tokens aren't on Gecko yet; use
            # DexScreener spot for a time-stop decision.
            try:
                info = resolve_pool(dexdata, mint)
                if info and info.get("price_usd"):
                    spot_sol = info["price_usd"] / 150.0  # sol_usd fallback
                    hold_min = (now - entry_ts) // 60
                    if hold_min >= 30:
                        # time-stop at spot
                        tokens = size_sol / entry_price if entry_price else 0
                        raw = tokens * spot_sol - size_sol
                        net = raw - gas_sim.swap_fee_sol()
                        con.execute("UPDATE paper_trades SET state='closed' WHERE trade_id=?", (trade_id,))
                        con.execute("""
                            INSERT OR REPLACE INTO archives
                            (trade_id, mint, hypothesis_id, entry_ts, exit_ts, hold_secs,
                             realized_pnl_sol, roi, expectancy_contrib, gas_sol_total,
                             slippage_total, exit_reason, created_ts)
                            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                        """, (trade_id, mint, hyp_id, entry_ts, now, (now - entry_ts),
                              net, net / size_sol if size_sol else 0, net,
                              gas_sim.swap_fee_sol(), 0.0, "time_stop_30m_spot", now))
                        closed += 1
                        print(f"[exit] {mint[:12]} time_stop_spot pnl={net:+.4f} SOL")
                else:
                    print(f"[monitor] {mint[:12]} no price source — keep open")
            except Exception as e:
                print(f"[monitor] {mint[:12]} spot err {e} — keep open")
            continue

        forward = [[r[0], r[1], r[2], r[3], r[4], r[5]] for r in rows if r[0] > entry_ts]
        if not forward:
            continue

        params = {"hard_stop": -0.35, "tp_ladder": [(2.0, 0.5), (4.0, 0.5)],
                  "trail_drop": 0.25, "time_stop_secs": 30 * 60}
        ex = exit_engine.simulate_exit(entry_price, entry_ts, forward, params)
        exit_price = ex["realized_price"]
        exit_reason = ex["final_reason"]
        if exit_reason in ("path_end", "none"):
            continue  # still holding

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
