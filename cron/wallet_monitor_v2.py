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

from compute import exit_engine, gas_sim, pnl  # noqa: E402
from compute.paper_ledger import (  # noqa: E402
    LedgerIntegrityError,
    close_trade_with_fills,
)


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(name)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _fill_dict(row):
    return {
        "seq": row["seq"], "kind": row["kind"], "ts": row["ts"],
        "qty": row["qty"], "price": row["price"],
        "reserves_base": row["reserves_base"], "reserves_quote": row["reserves_quote"],
        "base_fee": row["base_fee"], "priority_fee": row["priority_fee"],
        "native_usd": row["native_usd"], "gas_sol": row["gas_sol"],
        "slippage": row["slippage"], "amm_model": row["amm_model"],
    }


def _close_with_fills(con, trade_id, exit_fills, exit_ts, exit_reason, size_sol):
    entry_row = con.execute(
        "SELECT * FROM trade_fills WHERE trade_id=? AND kind='entry' ORDER BY seq LIMIT 1",
        (trade_id,),
    ).fetchone()
    if entry_row is None:
        raise LedgerIntegrityError("new monitor exit requires an entry fill")
    entry = _fill_dict(entry_row)
    swaps = [{
        "ts": entry["ts"], "side": "buy", "base_mint": trade_id,
        "base_qty": entry["qty"], "quote_qty": entry["qty"] * entry["price"],
        "gas_quote": entry["gas_sol"],
    }]
    total_slippage = entry["slippage"]
    total_gas = entry["gas_sol"]
    for fill in exit_fills:
        swaps.append({
            "ts": fill["ts"], "side": "sell", "base_mint": trade_id,
            "base_qty": fill["qty"], "quote_qty": fill["qty"] * fill["price"],
            "gas_quote": fill.get("gas_sol", 0),
        })
        total_slippage += fill.get("slippage", 0) or 0
        total_gas += fill.get("gas_sol", 0) or 0
    realized = pnl.fifo_trade_pnls(swaps)
    if not realized:
        raise LedgerIntegrityError("exit fills do not close the entry quantity")
    net = realized[-1] - total_slippage
    return close_trade_with_fills(
        con, trade_id, exit_fills, exit_ts=exit_ts,
        realized_pnl_sol=net, roi=net / size_sol if size_sol else 0,
        expectancy_contrib=net, gas_sol_total=total_gas,
        slippage_total=total_slippage, exit_reason=exit_reason,
    ), net


with script_lock("wallet_monitor"):
    dexdata = load("dexdata", DEPLOY / "theia-dexdata" / "server.py")
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
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
                        entry_row = con.execute(
                            "SELECT qty FROM trade_fills WHERE trade_id=? AND kind='entry' LIMIT 1",
                            (trade_id,),
                        ).fetchone()
                        if entry_row is None:
                            raise LedgerIntegrityError("new monitor exit requires an entry fill")
                        exit_fill = {
                            "seq": 1, "kind": "time_stop", "ts": now,
                            "qty": entry_row["qty"], "price": spot_sol,
                            "reserves_base": info.get("reserves_base"),
                            "reserves_quote": info.get("reserves_quote"),
                            "native_usd": info.get("native_usd"),
                            "gas_sol": gas_sim.swap_fee_sol(), "slippage": 0,
                            "amm_model": info.get("amm_model") or "unknown",
                        }
                        _, net = _close_with_fills(
                            con, trade_id, [exit_fill], now,
                            "time_stop_30m_spot", size_sol,
                        )
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

        entry_row = con.execute(
            "SELECT * FROM trade_fills WHERE trade_id=? AND kind='entry' LIMIT 1",
            (trade_id,),
        ).fetchone()
        if entry_row is None:
            print(f"[monitor] {mint[:12]} no entry fill — keep open")
            continue
        entry_qty = entry_row["qty"]
        exit_fills = []
        events = ex.get("exit_events", [])
        for seq, event in enumerate(events, start=1):
            exit_fills.append({
                "seq": seq,
                "kind": event["reason"],
                "ts": event["ts"],
                "qty": entry_qty * event["fraction"],
                "price": event["price"],
                # OHLCV does not include reserves; do not invent them.
                "reserves_base": None,
                "reserves_quote": None,
                "native_usd": None,
                "gas_sol": gas_sim.swap_fee_sol() if seq == len(events) else 0,
                "slippage": 0,
                "amm_model": "unknown",
            })
        try:
            _, net_pnl = _close_with_fills(
                con, trade_id, exit_fills, ex["exit_ts"], exit_reason, size_sol,
            )
        except LedgerIntegrityError as exc:
            print(f"[monitor] {mint[:12]} ledger close rejected: {exc} — keep open")
            continue
        closed += 1
        hold_secs = ex["exit_ts"] - entry_ts
        print(f"[exit] {mint[:12]} {exit_reason} pnl={net_pnl:+.4f} SOL "
              f"roi={net_pnl / size_sol if size_sol else 0:+.1%} hold={hold_secs//60}m")

    con.commit()
    n_open = con.execute("SELECT COUNT(*) FROM paper_trades WHERE state='open'").fetchone()[0]
    con.close()
    print(f"[monitor] closed={closed}, remaining open={n_open}")
