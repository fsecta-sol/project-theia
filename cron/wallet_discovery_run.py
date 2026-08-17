#!/usr/bin/env python3
"""Wallet discovery + revalidation runner — scheduled daily.

Stage 1: scrape GMGN leaderboard (winrate + pnl, 7d/30d) -> discovered_wallets.json
Stage 2: profile NEW wallets (already-known skipped) with latency-tolerance
         gate (train/test split, n>=20) -> wallet_profiles.is_smart_money updated.
Stage 3: prune tracked wallets that have gone stale (no trades for N days) so the
         tracked list stays live, not a frozen snapshot.

Wraps existing discover_wallets + profile_discovered logic with a shared lock
(no overlap with the 10-min track pipeline) and prints a digest for Telegram.
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
sys.path.insert(0, str(HERE))

# wallet_common loader (lock + cache)
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

with script_lock("wallet_discovery", timeout_wait=30):
    print("[discovery] started (single instance)")
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

    print("[discovery] stage1: scrape GMGN leaderboard...")
    r = subprocess.run([
        "/home/hermes/.hermes/theia/mcp/theia-webscraper/.venv/bin/python",
        str(discover_script)
    ], capture_output=True, text=True, timeout=900)
    if r.returncode != 0:
        print(f"[discovery] stage1 failed rc={r.returncode}: {r.stderr[-500:]}")
    else:
        print("[discovery] stage1 ok")

    # ── Stage 2: profile new candidates (latency-tolerant gate) ─────────────
    print("[discovery] stage2: profile new wallet candidates...")
    profile_script = HERE / "profile_discovered.py"
    if not profile_script.exists():
        profile_script = Path("/home/hermes/project-theia/cron/profile_discovered.py")
    if not profile_script.exists():
        profile_script = Path("/home/hermes/theia-gate/profile_discovered.py")

    if profile_script.exists():
        r = subprocess.run([
            "/home/hermes/.hermes/theia/mcp/theia-chainrpc/.venv/bin/python",
            str(profile_script)
        ], capture_output=True, text=True, timeout=3600)
        if r.returncode != 0:
            print(f"[discovery] stage2 failed rc={r.returncode}: {r.stderr[-500:]}")
        else:
            print("[discovery] stage2 ok")
            print(r.stdout[-2000:])
    else:
        print("[discovery] stage2 skipped (profile_discovered.py missing)")

    # ── Stage 3: prune stale tracked wallets ────────────────────────────────
    con = sqlite3.connect(DB)
    now = int(time.time())
    # 14-day tracker stores last_active_ts; unflag if no activity in 14 days
    stale = con.execute("""
        SELECT wallet FROM wallet_profiles
        WHERE is_smart_money=1 AND last_active_ts IS NOT NULL
          AND last_active_ts < ?
    """, (now - 14 * 86400,)).fetchall()
    pruned = 0
    for (w,) in stale:
        con.execute("UPDATE wallet_profiles SET is_smart_money=0 WHERE wallet=?", (w,))
        print(f"[discovery] prune stale: {w[:14]}")
        pruned += 1

    n_tracked = con.execute("SELECT COUNT(*) FROM wallet_profiles WHERE is_smart_money=1").fetchone()[0]
    con.commit()
    con.close()

    # ── Digest ──────────────────────────────────────────────────────────────
    print("\n=== WALLET DISCOVERY DIGEST ===")
    print(f"pruned: {pruned}, tracked now: {n_tracked}, took {time.time()-t0:.0f}s")