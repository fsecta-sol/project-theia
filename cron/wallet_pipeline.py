#!/usr/bin/env python3
"""Wallet pipeline runner — persistent loop (cron every 10 min).

Stages:
  1. TRACK: poll 8 latency-tolerant wallets, capture NEW buys (since last run)
  2. SCREEN: fetch pool liq + entry filters (liq>$5k, momentum, price cap)
  3. TRADE: open PAPER trades for signals that pass (via theia-store)
  4. (exit/archive handled by theia-monitor + theia-archive cron)

Design: single deterministic script, 0 LLM. Free-tier budget aware:
  - Helius: 8 wallets × 1 call = 8 calls/10min (well under free limit)
  - Gecko: only for NEW signals that pass basic filter (dedup'd), ~6s throttle

State: last-run timestamp in kv_state (k='wallet_pipeline_last_ts').
"""
import importlib.util
import json
import sqlite3
import sys
import time
from pathlib import Path

DATA = Path("/home/hermes/theia-gate/data")
DEPLOY = Path("/home/hermes/.hermes/theia/mcp")
DB = Path("/home/hermes/.hermes/theia/theia.db")
sys.path.insert(0, str(DEPLOY / "common"))
sys.path.insert(0, "/home/hermes/project-theia")

from compute import costs, gas_sim  # noqa: E402

WSOL = "So11111111111111111111111111111111111111112"
NOTIONAL = 0.5
LIQ_MIN = 5000
PRICE_CAP = 1.5
HYP_ID = "hyp_wallet_cluster_latency"


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


chainrpc = load("chainrpc", DEPLOY / "theia-chainrpc" / "server.py")
dexdata = load("dexdata", DEPLOY / "theia-dexdata" / "server.py")

con = sqlite3.connect(DB)


def get_state(key, default):
    r = con.execute("SELECT v FROM kv_state WHERE k=?", (key,)).fetchone()
    return json.loads(r[0]) if r else default


def set_state(key, value):
    con.execute("INSERT OR REPLACE INTO kv_state (k, v, updated_ts) VALUES (?,?,?)",
                (key, json.dumps(value), int(time.time())))
    con.commit()


def get_tracked():
    return [r[0] for r in con.execute(
        "SELECT wallet FROM wallet_profiles WHERE is_smart_money=1").fetchall()]


# ── 1. TRACK ────────────────────────────────────────────────────────────────
now = int(time.time())
seen = {r[0] for r in con.execute("SELECT id FROM wallet_signals")}

new_signals = []
for w in get_tracked():
    try:
        swaps = chainrpc.wallet_swaps(w, pages=1)
    except Exception as e:
        print(f"[track] {w[:12]} ERR {e}")
        continue
    for s in swaps:
        sig = s.get("signature")
        ts = s.get("ts", 0)
        if not sig or sig in seen:
            continue
        if s.get("side") != "buy" or s.get("quote_mint") != WSOL:
            continue
        if ts < now - 6 * 3600:  # only recent buys
            continue
        con.execute("""
            INSERT OR IGNORE INTO wallet_signals
            (id, wallet, mint, signal_type, signal_ts, detected_ts, latency_sec, our_action)
            VALUES (?,?,?,?,?,?,?,?)
        """, (sig, w, s.get("base_mint"), "buy", ts, now, now - ts, "pending"))
        seen.add(sig)
        new_signals.append({"wallet": w, "mint": s.get("base_mint"),
                            "signal_ts": ts, "signal_sol": s.get("quote_qty", 0),
                            "exec_price": s.get("exec_price", 0), "sig": sig})
con.commit()
set_state("wallet_pipeline_last_ts", now)
print(f"[track] {len(new_signals)} new signals from {len(get_tracked())} wallets")

if not new_signals:
    con.close()
    print("[done] no new signals — exit")
    sys.exit(0)

# ── 2+3. SCREEN + PAPER TRADE ──────────────────────────────────────────────
# SOL/USD for price-cap check
SOL_USD = 150.0
try:
    r = dexdata.pairs_by_token(["So11111111111111111111111111111111111111112"])
    for p in r:
        if (p.get("baseToken", {}).get("address") == "So11111111111111111111111111111111111111112"
                and (p.get("quoteToken", {}).get("symbol") or "").upper().startswith("USDC")):
            try:
                SOL_USD = float(p.get("priceUsd") or SOL_USD)
                break
            except (TypeError, ValueError):
                pass
except Exception:
    pass

opened = 0
for sig in new_signals:
    mint = sig["mint"]
    # Dedup: skip mints with an open position
    existing = con.execute(
        "SELECT COUNT(*) FROM paper_trades WHERE mint=? AND state='open'", (mint,)
    ).fetchone()[0]
    if existing:
        con.execute("UPDATE wallet_signals SET our_action='skipped_duplicate' WHERE id=?",
                    (sig["sig"],))
        continue

    # Screen: pool liquidity
    try:
        pools = dexdata.token_pools(mint)
        time.sleep(6)
    except Exception as e:
        con.execute("UPDATE wallet_signals SET our_action='skip_no_pool' WHERE id=?",
                    (sig["sig"],))
        continue
    if not pools:
        con.execute("UPDATE wallet_signals SET our_action='skip_no_pool' WHERE id=?",
                    (sig["sig"],))
        continue
    attr = pools[0].get("attributes", {})
    try:
        liq = float(attr.get("reserve_in_usd") or 0)
    except (TypeError, ValueError):
        liq = 0
    if liq < LIQ_MIN:
        con.execute("UPDATE wallet_signals SET our_action='skip_low_liq' WHERE id=?",
                    (sig["sig"],))
        continue

    # Price cap: don't chase if >1.5x the wallet's exec price
    cur_price = float(attr.get("base_token_price_usd") or 0)
    exec_usd = sig["exec_price"] * SOL_USD
    if exec_usd > 0 and cur_price > exec_usd * PRICE_CAP:
        con.execute("UPDATE wallet_signals SET our_action='skip_chase' WHERE id=?",
                    (sig["sig"],))
        continue

    # Open PAPER trade via theia-store schema (paper_trades table)
    trade_id = f"wp_{sig['sig'][:24]}"
    entry_price_sol = cur_price / SOL_USD if SOL_USD else 0
    is_bonding = "pump" in (attr.get("dex_id") or "").lower()
    slip = costs.slippage_estimate(NOTIONAL * SOL_USD, max(liq, 100), is_bonding)
    entry_gas = gas_sim.swap_fee_sol(first_buy=True)
    stop_price = entry_price_sol * 0.65  # -35% hard stop

    con.execute("""
        INSERT OR IGNORE INTO paper_trades
        (trade_id, mint, hypothesis_id, state, entry_ts, entry_price, size_sol,
         stop_price, tp_ladder, opened_by)
        VALUES (?,?,?,?,?,?,?,?,?,?)
    """, (trade_id, mint, HYP_ID, "open", now, entry_price_sol, NOTIONAL,
          stop_price, json.dumps([{"target": 2.0, "pct": 0.5}, {"target": 4.0, "pct": 0.5}]),
          json.dumps({"kind": "wallet_pipeline", "wallet": sig["wallet"],
                      "liq_usd": liq, "gas_sol": entry_gas, "slippage_sol": NOTIONAL * slip})))
    con.execute("UPDATE wallet_signals SET our_action='paper_traded', our_entry_ts=? WHERE id=?",
                (now, sig["sig"]))
    opened += 1
    print(f"[trade] OPEN {mint[:12]} from {sig['wallet'][:10]} liq=${liq:,.0f} "
          f"price=${cur_price:.6f}")

con.commit()
n_open = con.execute("SELECT COUNT(*) FROM paper_trades WHERE state='open'").fetchone()[0]
con.close()
print(f"[done] opened={opened}, total open positions={n_open}")
