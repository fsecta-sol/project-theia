#!/usr/bin/env python3
"""Wallet pipeline runner v4 — VARIAN dari wallet_pipeline_v3.py (M-01 sync).

PERUBAHAN vs v3:
  1. universe wallet: dibaca dari wallet_profiles WHERE is_smart_money=1
     (sekarang 12 wallet latency-tolerant hasil sync M-01; sebelumnya 9).
  2. entry price: PRICE USD / SOL_USD — bukan price_usd/150 hardcode.
     sol_usd() dari wallet_common (cached 15m) — fix harga entry.
  3. RECORD OHLCV: setiap mint yang discreen (action 'ok') di-rekam ke
     price_snapshots (forward corpus utk backtest OOS) + dicatat kv_state
     'forward_corpus_mints' — inilah yg bikin OOS ≥50 bisa tercapai nanti.
  4. signal captured: TIDAK skip yg di luar window — TANDAI 'missed_window'
     (tetap direkam utk corpus, tidak di-paper-trade).
  5. exit params tetap (30m) utk kompatibilitas; exit di-handle wallet_monitor_v3.

0 LLM. Flock single-instance (sama seperti v3).
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
ohlcv_for = wc.ohlcv_for
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
MAX_OPEN_PER_WALLET = 5
ENTRY_WINDOW = 30 * 60
DETECT_GRACE = 5 * 60


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {name} from {path}")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def record_ohlcv(con, mint, pool_addr, rows):
    """Append 1-min OHLCV rows into price_snapshots (forward corpus).

    Schema price_snapshots: (pool_addr, ts, o, h, l, c, currency, v, mcap).
    v1.1: also captures per-candle volume (index 5) and mcap (index 6) when the
    source provides them (needed for volume-confirmed dip-reversal backtests).
    """
    n = 0
    for r in rows:
        try:
            ts = int(r[0])
            o, h, l, c, v = float(r[1]), float(r[2]), float(r[3]), float(r[4]), float(r[5])
            mcap = float(r[6]) if len(r) > 6 and r[6] is not None else 0.0
        except (TypeError, ValueError, IndexError):
            continue
        cur = con.execute(
            "SELECT 1 FROM price_snapshots WHERE pool_addr=? AND ts=?",
            (pool_addr, ts),
        ).fetchone()
        if cur:
            continue
        con.execute(
            "INSERT OR IGNORE INTO price_snapshots (pool_addr, ts, o, h, l, c, currency, v, mcap)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            (pool_addr, ts, o, h, l, c, "token", v, mcap),
        )
        n += 1
    if n:
        # track corpus mints in kv_state for the forward backtest
        cur = con.execute("SELECT v FROM kv_state WHERE k='forward_corpus_mints'").fetchone()
        mints = set(json.loads(cur[0])) if cur else set()
        mints.add(mint)
        con.execute(
            "INSERT OR REPLACE INTO kv_state (k, v, updated_ts) VALUES ('forward_corpus_mints',?,?)",
            ("forward_corpus_mints", json.dumps(sorted(mints)), int(time.time())),
        )
    return n


with script_lock("wallet_pipeline"):
    print("[pipeline] started (single instance) — v4 M-01 sync")
    chainrpc = load("chainrpc", DEPLOY / "theia-chainrpc" / "server.py")
    dexdata = load("dexdata", DEPLOY / "theia-dexdata" / "server.py")
    birdeye = load("birdeye", DEPLOY / "theia-birdeye" / "server.py")

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
            "SELECT wallet FROM wallet_profiles WHERE is_smart_money=1 AND track_enabled=1").fetchall()]

    # ── 1. TRACK ────────────────────────────────────────────────────────────
    now = int(time.time())
    seen = {r[0] for r in con.execute("SELECT id FROM wallet_signals")}
    tracked = get_tracked()
    new_signals = []
    window_cutoff = now - ENTRY_WINDOW - DETECT_GRACE

    from concurrent import futures
    def _fetch(w):
        try:
            # pages=1: cukup utk deteksi sinyal dalam window 35 menit; history
            # lebih dalam = replay sampah (fix: 983 missed_window dari history)
            return w, chainrpc.wallet_swaps(w, pages=1)
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
                # SKIP sinyal di luar window — jangan di-INSERT sama sekali.
                # (v3 behavior; merekam missed_window = korpus kacau + sampah)
                if ts < window_cutoff:
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

    # ── 1b. PENDING signals still inside entry window ──
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

    # ── 2+3. SCREEN + PAPER TRADE + RECORD OHLCV ───────────────────────────
    # FIX sol_usd: wallet_common.sol_usd() bisa kena pair salah-label
    # (FOGO dgn address WSOL + quote USDC.s -> price 0.0095). Ambil SOL/USD
    # dgn filter ketat: quote symbol PERSIS 'USDC'/'USDT' + price 50-250.
    try:
        usd = sol_usd(dexdata)
        if not (50.0 <= usd <= 250.0):
            raise ValueError(f"sol_usd implausible: {usd}")
    except Exception as _e:
        usd = None
        try:
            pairs = dexdata.pairs_by_token([WSOL]) or []
            for p in pairs:
                qs = (p.get("quoteToken", {}) or {}).get("symbol") or ""
                if p.get("baseToken", {}).get("address") == WSOL and qs in ("USDC", "USDT"):
                    px = float(p.get("priceUsd") or 0)
                    if 50.0 <= px <= 250.0:
                        usd = px
                        break
        except Exception:
            pass
    if not usd:
        usd = 150.0
        print("[screen] WARN: sol_usd fallback 150 (sumber SOL/USD tidak valid)")
    print(f"[screen] sol_usd={usd}")

    all_signals = new_signals + pending_signals

    def _screen(sig):
        mint = sig["mint"]
        try:
            info = resolve_pool(dexdata, mint)
        except Exception:
            info = None
        if not info or info.get("liq_usd", 0) < LIQ_MIN:
            return "skip_low_liq", info
        cur_price = info.get("price_usd", 0)
        exec_usd = sig["exec_price"] * usd
        if exec_usd > 0 and cur_price > exec_usd * PRICE_CAP:
            return "skip_chase", info
        return "ok", info

    screened = parallel_map(_screen, all_signals, workers=3)
    opened = 0
    recorded_mints = 0
    for item, result in screened:
        if result is None:
            continue  # screen raised — leave signal pending for next run
        sig = item
        action, info = result
        mint = sig["mint"]
        if action != "ok":
            con.execute("UPDATE wallet_signals SET our_action=? WHERE id=?", (action, sig["sig"]))
            continue

        # RECORD OHLCV for forward corpus (biar OOS bisa dibacktest nanti)
        try:
            pool_addr = (info or {}).get("pool")
            rows, src = ohlcv_for(dexdata, birdeye, mint, before_ts=0, ttl=300)  # cached 5m
            if pool_addr and rows:
                recorded = record_ohlcv(con, mint, pool_addr, rows)
                recorded_mints += 1
                if recorded:
                    print(f"[record] {mint[:12]} +{recorded} snapshots (src={src})")
        except Exception as e:
            print(f"[record] {mint[:12]} ohlcv err {e}")

        # dedup: already open?
        existing = con.execute(
            "SELECT COUNT(*) FROM paper_trades WHERE mint=? AND state='open'", (mint,)
        ).fetchone()[0]
        if existing:
            con.execute("UPDATE wallet_signals SET our_action='skipped_duplicate' WHERE id=?",
                        (sig["sig"],))
            continue

        # per-wallet exposure cap
        n_wallet_open = con.execute(
            "SELECT COUNT(*) FROM paper_trades WHERE state='open' AND opened_by LIKE ?",
            (f'%"{sig["wallet"]}"%',)
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
        print(f"[trade] OPEN {mint[:12]} from {sig['wallet'][:10]} liq=${liq:,.0f} entry_sol={entry_price_sol:.8f}")

    con.commit()
    n_open = con.execute("SELECT COUNT(*) FROM paper_trades WHERE state='open'").fetchone()[0]
    con.close()
    print(f"[done] opened={opened}, recorded_mints={recorded_mints}, total open positions={n_open}")
