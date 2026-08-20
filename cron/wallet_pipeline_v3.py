#!/usr/bin/env python3
"""Wallet pipeline runner — persistent loop (cron every 10 min).

Stages:
  1. TRACK: poll latency-tolerant wallets, capture NEW buys (since last run),
     pages=3 to reduce miss-rate on high-frequency wallets (fix #8)
  2. SCREEN: pool liq + price cap via cached/parallel helpers (fix #1,#2,#3,#7)
  3. TRADE: open PAPER trades for signals that pass; per-wallet exposure cap
     to protect against single-wallet dominance (fix #6)
  4. exit/archive handled by theia-wallet-monitor cron

Single-instance via flock (fix #2 overlap). 0 LLM.
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

# allow running from anywhere (cron profile scripts dir vs repo cron/)
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, "/home/hermes/project-theia")

# wallet_common may live next to this script OR in project-theia/cron
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
sol_usd = wc.sol_usd
script_lock = wc.script_lock
parallel_map = wc.parallel_map

from compute import costs, gas_sim  # noqa: E402
from compute.paper_ledger import LedgerIntegrityError, open_trade_with_entry_fill  # noqa: E402

WSOL = "So11111111111111111111111111111111111111112"
NOTIONAL = 0.5
LIQ_MIN = 5000
PRICE_CAP = 1.5
HYP_ID = "hyp_wallet_cluster_latency"
MAX_OPEN_PER_WALLET = 3  # at most 3 concurrent open positions per wallet (fix #6)
# Window for a buy to be tradeable: our edge is follow-within-30min. A signal
# older than ENTRY_WINDOW would be entered too late (the backtest assumes entry
# at T+30m window close; older than that = we missed it). Fix #4.
ENTRY_WINDOW = 30 * 60
# Extra catch: allow signals slightly older if they were detected late (e.g. API lag)
DETECT_GRACE = 5 * 60


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {name} from {path}")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


with script_lock("wallet_pipeline"):
    print("[pipeline] started (single instance)")
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

    # ── 1. TRACK ────────────────────────────────────────────────────────────
    now = int(time.time())
    seen = {r[0] for r in con.execute("SELECT id FROM wallet_signals")}
    tracked = get_tracked()
    new_signals = []

    # fetch wallet swaps in parallel (fix #1; still rate-limited inside chainrpc? no —
    # chainrpc has its own API key rotation, safe to parallelize)
    from concurrent import futures
    def _fetch(w):
        try:
            return w, chainrpc.wallet_swaps(w, pages=5)
        except Exception as e:
            print(f"[track] {w[:12]} ERR {e}")
            return w, []

    with futures.ThreadPoolExecutor(max_workers=4) as ex:
        for w, swaps in ex.map(_fetch, tracked):
            for s in swaps:
                sig = s.get("signature")
                ts = s.get("ts", 0)
                if not sig or sig in seen:
                    continue
                if s.get("side") != "buy" or s.get("quote_mint") != WSOL:
                    continue
                # Tradeable only if the buy is within our entry window (or within
                # grace of it). Older buys = missed; store but never paper-trade
                # them, so stale history can't pollute the forward sample.
                if ts < now - ENTRY_WINDOW - DETECT_GRACE:
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
    print(f"[track] {len(new_signals)} new signals from {len(tracked)} wallets")

    # ── 1b. Also pick up any PENDING signals still inside the entry window ──
    # (captured on a previous tick but never processed — don't strand them)
    pending_rows = con.execute("""
        SELECT id, wallet, mint, signal_ts, our_action FROM wallet_signals
        WHERE our_action='pending' AND signal_ts >= ?
    """, (now - ENTRY_WINDOW - DETECT_GRACE,)).fetchall()
    pending_signals = []
    for sig_id, w, mint, sig_ts, _ in pending_rows:
        pending_signals.append({
            "wallet": w, "mint": mint, "signal_ts": sig_ts,
            "signal_sol": 0.0, "exec_price": 0.0, "sig": sig_id, "from_pending": True,
        })
    print(f"[track] {len(pending_signals)} pending still within entry window")

    if not new_signals and not pending_signals:
        con.close()
        print("[done] no signals — exit")
        sys.exit(0)

    # ── 2+3. SCREEN + PAPER TRADE (parallel screen) ────────────────────────
    usd = sol_usd(dexdata)  # cached 15m

    # Combine new + pending signals for screening
    all_signals = new_signals + pending_signals

    def _screen(sig):
        mint = sig["mint"]
        try:
            info = resolve_pool(dexdata, mint)
        except Exception:
            info = None
        if not info or info.get("liq_usd", 0) < LIQ_MIN:
            return "skip_low_liq", info
        # price cap: don't chase >1.5x wallet exec
        cur_price = info.get("price_usd", 0)
        exec_usd = sig["exec_price"] * usd
        if exec_usd > 0 and cur_price > exec_usd * PRICE_CAP:
            return "skip_chase", info
        return "ok", info

    # parallel_map returns [(item, result), ...]; result = (action, info) or None on error
    screened = parallel_map(_screen, all_signals, workers=3)
    opened = 0
    for item, result in screened:
        if result is None:
            continue  # screen raised — leave signal pending for next run
        sig = item
        action, info = result
        mint = sig["mint"]
        if action != "ok":
            con.execute("UPDATE wallet_signals SET our_action=? WHERE id=?", (action, sig["sig"]))
            continue

        # dedup: already open?
        existing = con.execute(
            "SELECT COUNT(*) FROM paper_trades WHERE mint=? AND state='open'", (mint,)
        ).fetchone()[0]
        if existing:
            con.execute("UPDATE wallet_signals SET our_action='skipped_duplicate' WHERE id=?",
                        (sig["sig"],))
            continue

        # per-wallet exposure cap (fix #6): count open trades opened_by this wallet
        # (opened_by is a JSON string; wallet is stored inside it)
        n_wallet_open = con.execute(
            "SELECT COUNT(*) FROM paper_trades WHERE state='open' AND opened_by LIKE ?",
            (f'%"wallet": "{sig["wallet"]}"%',)
        ).fetchone()[0]
        if n_wallet_open >= MAX_OPEN_PER_WALLET:
            con.execute("UPDATE wallet_signals SET our_action='skip_wallet_cap' WHERE id=?",
                        (sig["sig"],))
            continue

        # open PAPER trade
        trade_id = f"wp_{sig['sig'][:24]}"
        liq = info.get("liq_usd") or 0
        is_bonding = "pump" in (info.get("dex_id") or "").lower()
        slip = costs.slippage_estimate(NOTIONAL * usd, max(liq, 100), is_bonding)
        entry_gas = gas_sim.swap_fee_sol(first_buy=True)
        entry_price_sol = (info.get("price_usd") or 0) / usd if usd else 0
        if entry_price_sol <= 0:
            con.execute("UPDATE wallet_signals SET our_action='skip_missing_entry_price' WHERE id=?",
                        (sig["sig"],))
            continue
        entry_qty = NOTIONAL / entry_price_sol
        stop_price = entry_price_sol * 0.65

        try:
            open_trade_with_entry_fill(
                con,
                trade_id=trade_id,
                mint=mint,
                hypothesis_id=HYP_ID,
                entry_ts=now,
                entry_price=entry_price_sol,
                size_sol=NOTIONAL,
                stop_price=stop_price,
                tp_ladder=[{"target": 2.0, "pct": 0.5}, {"target": 4.0, "pct": 0.5}],
                opened_by={"kind": "wallet_pipeline", "wallet": sig["wallet"],
                           "liq_usd": liq, "gas_sol": entry_gas,
                           "slippage_sol": NOTIONAL * slip},
                entry_fill={
                    "seq": 0, "kind": "entry", "ts": now, "qty": entry_qty,
                    "price": entry_price_sol,
                    # Current pool/spot responses do not expose reserves. Keep
                    # NULL and let the archive writer mark the trade degraded.
                    "reserves_base": info.get("reserves_base"),
                    "reserves_quote": info.get("reserves_quote"),
                    "base_fee": info.get("base_fee", 0),
                    "priority_fee": info.get("priority_fee", 0),
                    "native_usd": usd,
                    "gas_sol": entry_gas,
                    "slippage": NOTIONAL * slip,
                    "amm_model": info.get("amm_model") or "unknown",
                },
            )
        except LedgerIntegrityError as exc:
            con.execute("UPDATE wallet_signals SET our_action='entry_ledger_error' WHERE id=?",
                        (sig["sig"],))
            print(f"[trade] {mint[:12]} entry ledger error: {exc}")
            continue

        con.execute("UPDATE wallet_signals SET our_action='paper_traded', our_entry_ts=? WHERE id=?",
                    (now, sig["sig"]))
        opened += 1
        print(f"[trade] OPEN {mint[:12]} from {sig['wallet'][:10]} liq=${liq:,.0f}")

    con.commit()
    n_open = con.execute("SELECT COUNT(*) FROM paper_trades WHERE state='open'").fetchone()[0]
    con.close()
    print(f"[done] opened={opened}, total open positions={n_open}")