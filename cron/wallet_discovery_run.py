#!/usr/bin/env python3
"""Wallet discovery + revalidation runner — GMGN-FIRST (v2, 2026-08-27).

Stage 1: scrape GMGN leaderboard -> discovered_wallets.json (FULL fields).
Stage 2 (BARU): GMGN-DIRECT selection — pakai winrate GMGN (bukan hitung ulang)
         + konsistensi 7d/30d + txs + holding + tag filter. Langsung upsert ke
         wallet_profiles dgn is_smart_money=1/0 sesuai gate. TIDAK ada lagi
         fetch swaps / profile_wallet / latency backtest (buang hitung ulang).
Stage 3: prune stale tracked wallets (no activity 14d) -> unflag.

Rasional: GMGN leaderboard sudah menghitung winrate/PnL/distribution dgn sample
besar. Hitung ulang dari ~20 txs (profile_wallet + sim OHLCV) menyesatkan
(contoh: winrate_7d=1.0 tapi 5 txs & hold 9.9 hari) dan mahal (Gecko rate-limit).
Gate pakai: winrate_7d >= 0.6, txs_7d >= 20, winrate_30d >= 0.5 (konsistensi),
holding median < 6 jam, tanpa tag bot/wash.
"""
import importlib.util
import json
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

DEPLOY = Path("/home/hermes/.hermes/theia/mcp")
DB = Path("/home/hermes/.hermes/theia/theia.db")
HERE = Path(__file__).resolve().parent
DATA = Path("/home/hermes/theia-gate/data")

# ── GMGN selection gate (GMGN-FIRST) ────────────────────────────────────────
# Diturunkan dari distribusi LIVE leaderboard GMGN (2026-08-27):
#  - top trader punya ribuan txs (txs7>=300), sample kecil (<20) = noise
#  - wr7>=0.60 realistis (top leaderboard winrate 7d umumnya 0.60-0.65)
#  - wr30>=0.50 = konsistensi lintas periode (anti 1-week-wonder)
#  - avg_holding GMGN dihitung dari SEMUA txs; trader top umumnya 25-45h,
#    jadi hold<6h hampir pasti 0 lolos. hold<12h = toleransi masuk akal.
# 2026-08-27: TXS_7D_MIN 300 -> 150 (relaxed; universe 77 -> ~200 dengan
# limit=100 + orderby baru). Distribusi live: txs7>=150 & wr7>=0.6 & wr30>=0.5
# = 9 wallet vs 8 di >=300; dengan universe lebih besar efeknya signifikan.
WR_7D_MIN = 0.60       # winrate 7d minimal
WR_30D_MIN = 0.50      # winrate 30d minimal (konsistensi, anti 1-run-wonder)
TXS_7D_MIN = 150       # minimal aktivitas 7d (anti sample kecil)
HOLD_MAX_S = 48 * 3600 # avg holding < 48 jam (top trader SOL memecoin pegang 1-3 hari;
                       # 6-12h terlalu ketat — 0 lolos di leaderboard live)
BAD_TAGS = {"wash_trader", "bot"}


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
script_lock = wc.script_lock


def _f(v, default=0.0):
    if v is None:
        return default
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _fn(v):
    """float atau None — untuk kolom nullable di wallet_scan_history."""
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def gmgn_pass(w: dict) -> tuple[bool, str]:
    """Return (pass, reason). Trust GMGN data; no recompute."""
    tags = {str(t).lower() for t in (w.get("tags") or [])}
    if tags & BAD_TAGS:
        return False, f"bad_tag:{sorted(tags & BAD_TAGS)}"
    wr7 = _f(w.get("winrate_7d"))
    wr30 = _f(w.get("winrate_30d"))
    txs = _f(w.get("txs_7d"))
    hold = _fn(w.get("avg_holding_period_7d"))
    if hold is None:
        hold = 0.0
    if wr7 < WR_7D_MIN:
        return False, f"wr7={wr7:.2f}"
    if wr30 < WR_30D_MIN:
        return False, f"wr30={wr30:.2f}"
    if txs < TXS_7D_MIN:
        return False, f"txs7={txs:.0f}"
    if hold > HOLD_MAX_S:
        return False, f"hold={hold/3600:.1f}h"
    return True, "ok"


def _subprocess_run(cmd):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
        if r.returncode != 0:
            return f"[discovery] stage1 failed rc={r.returncode}: {r.stderr[-500:]}"
        return r.stdout[-2000:]
    except subprocess.TimeoutExpired:
        return "[discovery] stage1 TIMEOUT after 900s"


with script_lock("wallet_discovery", timeout_wait=30):
    print("[discovery] started (single instance) — GMGN-FIRST v2")
    t0 = time.time()

    # ── Stage 1: scrape GMGN leaderboard ───────────────────────────────────
    discover_script = HERE / "discover_wallets.py"
    if not discover_script.exists():
        discover_script = Path("/home/hermes/project-theia/cron/discover_wallets.py")
    if not discover_script.exists():
        discover_script = Path("/home/hermes/theia-gate/discover_wallets.py")
    if not discover_script.exists():
        print("[discovery] FATAL: discover_wallets.py not found")
        sys.exit(1)

    # Stage 1 needs the webscraper venv (CF Turnstile bypass). If the current
    # interpreter already IS that venv (e.g. manual smoke test), reuse sys.executable.
    import os
    if os.path.basename(sys.executable).startswith("python") and "theia-webscraper" in sys.executable:
        stage1_py = sys.executable
    else:
        stage1_py = "/home/hermes/.hermes/theia/mcp/theia-webscraper/.venv/bin/python"
    print("[discovery] stage1: scrape GMGN leaderboard...")
    r = _subprocess_run([
        stage1_py,
        str(discover_script),
    ])
    if r:
        print(r)

    # ── Stage 2: GMGN-DIRECT selection (no recompute) ──────────────────────
    disc_file = DATA / "discovered_wallets.json"
    if not disc_file.exists():
        print("[discovery] FATAL: discovered_wallets.json missing")
        sys.exit(1)
    disc = json.loads(disc_file.read_text())
    wallets = disc.get("gmgn") or []
    print(f"[discovery] stage2: GMGN-direct gate on {len(wallets)} wallets")

    con = sqlite3.connect(DB)
    now = int(time.time())
    # Tabel scan-history: simpan SEMUA hasil scan (pass + fail) dengan field
    # GMGN lengkap — bahan backtest rule seleksi (yang lolos vs yang gak,
    # lalu bandingkan outcome). Diisi tiap run, append-only.
    con.execute("""
        CREATE TABLE IF NOT EXISTS wallet_scan_history (
            wallet TEXT NOT NULL,
            scan_ts INTEGER NOT NULL,
            winrate_7d REAL, winrate_30d REAL, txs_7d INTEGER,
            buy_7d INTEGER, sell_7d INTEGER, avg_holding_period_7d REAL,
            volume_7d REAL, realized_profit_7d REAL, pnl_7d REAL,
            tags TEXT, gate_pass INTEGER, gate_reason TEXT,
            pnl_gt_5x_num_7d INTEGER, pnl_2x_5x_num_7d INTEGER,
            pnl_lt_2x_num_7d INTEGER, pnl_minus_dot5_0x_num_7d INTEGER,
            pnl_lt_minus_dot5_num_7d INTEGER, last_active INTEGER,
            nickname TEXT, twitter_username TEXT,
            PRIMARY KEY (wallet, scan_ts)
        )
    """)
    # keep field semantics stable: reuse wallet_profiles columns
    n_pass = n_fail = n_new = n_update = 0
    reasons = {}
    for w in wallets:
        addr = w.get("address")
        if not addr:
            continue
        ok, reason = gmgn_pass(w)
        reasons[reason.split(":")[0]] = reasons.get(reason.split(":")[0], 0) + 1
        # Scan history — append-only, full GMGN fields, every wallet
        # (distribution buckets + last_active/nickname/twitter added 2026-08-28
        # so backtests can use PnL-shape data that previously got dropped)
        try:
            con.execute("""
                INSERT OR IGNORE INTO wallet_scan_history
                (wallet, scan_ts, winrate_7d, winrate_30d, txs_7d, buy_7d,
                 sell_7d, avg_holding_period_7d, volume_7d, realized_profit_7d,
                 pnl_7d, tags, gate_pass, gate_reason,
                 pnl_gt_5x_num_7d, pnl_2x_5x_num_7d, pnl_lt_2x_num_7d,
                 pnl_minus_dot5_0x_num_7d, pnl_lt_minus_dot5_num_7d,
                 last_active, nickname, twitter_username)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (addr, now, _fn(w.get("winrate_7d")),
                  _fn(w.get("winrate_30d")), int(_f(w.get("txs_7d"))),
                  int(_f(w.get("buy_7d"))), int(_f(w.get("sell_7d"))),
                  _fn(w.get("avg_holding_period_7d")),
                  _fn(w.get("volume_7d")), _fn(w.get("realized_profit_7d")),
                  _fn(w.get("pnl_7d")), json.dumps(w.get("tags") or []),
                  1 if ok else 0, reason,
                  int(_f(w.get("pnl_gt_5x_num_7d"))),
                  int(_f(w.get("pnl_2x_5x_num_7d"))),
                  int(_f(w.get("pnl_lt_2x_num_7d"))),
                  int(_f(w.get("pnl_minus_dot5_0x_num_7d"))),
                  int(_f(w.get("pnl_lt_minus_dot5_num_7d"))),
                  _fn(w.get("last_active")), w.get("nickname") or None,
                  w.get("twitter_username") or None))
        except Exception as e:
            print(f"[scan_history] {addr[:10]} insert err: {e}")
        row = con.execute("SELECT wallet, is_smart_money, first_seen_ts FROM wallet_profiles WHERE wallet=?",
                          (addr,)).fetchone()
        is_sm = 1 if ok else 0
        if ok:
            n_pass += 1
        else:
            n_fail += 1
        # source: tetap 'gmgn_winrate' (konsisten dgn riwayat); simpan alasan
        # gate via updated_ts + catatan di kolom source.
        src = "gmgn_winrate" + ("" if ok else ":rejected")
        if row is None:
            n_new += 1
            con.execute("""
                INSERT INTO wallet_profiles
                (wallet, first_seen_ts, last_active_ts, total_trades, total_buys,
                 total_sells, unique_tokens, median_buy_sol, mean_buy_sol,
                 median_hold_min, median_pnl_pct, win_rate, profit_factor,
                 expectancy_sol, pattern_cluster, is_smart_money, source,
                 created_ts, updated_ts)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (addr, now, _f(w.get("last_active")) or now, int(_f(w.get("txs_7d"))),
                  int(_f(w.get("buy_7d"))), int(_f(w.get("sell_7d"))),
                  0, None, None, (_f(w.get("avg_holding_period_7d")) or 0) / 60.0,
                  None, _f(w.get("winrate_7d")), None,
                  _f(w.get("realized_profit_7d")), "gmgn_direct", is_sm,
                  src, now, now))
        else:
            # update only if gate status berubah atau profil lama (hitung ulang)
            n_update += 1
            # Muncul di leaderboard = aktif sekarang. Refresh last_active_ts
            # pakai nilai GMGN (epoch detik) atau now, biar stage-3 prune 14d
            # gak salah-hapus wallet yang masih aktif (fix 2026-08-27).
            la_ts = _f(w.get("last_active"))
            la_ts = int(la_ts) if (la_ts and la_ts > 1e9) else now
            # track_enabled=0 (manual exclusion) memaksa is_smart_money=0 agar
            # pipeline (WHERE track_enabled=1) tidak mem-poll wallet yang
            # sengaja dimatikan (verified-6 filter, 2026-08-31).
            forced_off = con.execute(
                "SELECT track_enabled FROM wallet_profiles WHERE wallet=?",
                (addr,)).fetchone()
            forced_off = (forced_off[0] == 0) if forced_off else False
            if forced_off:
                is_sm = 0
            con.execute("""
                UPDATE wallet_profiles SET
                  is_smart_money=?, win_rate=?, total_trades=?,
                  median_hold_min=?, expectancy_sol=?, source=?, updated_ts=?,
                  first_seen_ts=MIN(first_seen_ts, ?),
                  last_active_ts=MAX(last_active_ts, ?)
                WHERE wallet=?
            """, (is_sm, _f(w.get("winrate_7d")), int(_f(w.get("txs_7d"))),
                  (_f(w.get("avg_holding_period_7d")) or 0) / 60.0,
                  _f(w.get("realized_profit_7d")), src, now, now, la_ts, addr))
    con.commit()

    # ── Stage 3: prune stale tracked wallets ───────────────────────────────
    # Hanya prune wallet yang masih track_enabled=1 — wallet yang sengaja
    # dimatikan (track_enabled=0, verified-6 filter) tidak disentuh.
    stale = con.execute("""
        SELECT wallet FROM wallet_profiles
        WHERE is_smart_money=1 AND track_enabled=1 AND last_active_ts IS NOT NULL
          AND last_active_ts < ?
    """, (now - 14 * 86400,)).fetchall()
    pruned = 0
    for (w,) in stale:
        con.execute("UPDATE wallet_profiles SET is_smart_money=0, track_enabled=0 WHERE wallet=?", (w,))
        print(f"[discovery] prune stale: {w[:14]}")
        pruned += 1
    con.commit()

    n_tracked = con.execute(
        "SELECT COUNT(*) FROM wallet_profiles WHERE is_smart_money=1 AND track_enabled=1").fetchone()[0]
    con.close()

    print("\n=== WALLET DISCOVERY DIGEST (GMGN-FIRST) ===")
    print(f"pass={n_pass} fail={n_fail} new={n_new} updated={n_update} "
          f"pruned={pruned} tracked now={n_tracked} took={time.time()-t0:.0f}s")
    print("reject reasons:", reasons)
