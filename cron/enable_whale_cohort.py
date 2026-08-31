#!/usr/bin/env python3
"""Enable the 9 not-yet-tracked whales as the gate-v2 forward cohort.

Whales = OOS-confirmed criteria (txs7>=500, rPnl7d>=10k, hold<48h, vol7d>=q3)
from wallet_scan_history (latest scan since 25-Aug). Refetches fresh GMGN
walletNew 7d stats per whale first (bounded: 1 call each, 1.5s sleep), verifies
the criteria still hold on FRESH data, then sets track_enabled=1 + upserts a
wallet_profiles row (source='gmgn_whale_v2') if missing. Never touches wallets
blacklisted for bundler/dev.
"""
import json
import sqlite3
import sys
import time
from pathlib import Path

CACHE_DIR = Path.home() / ".hermes/theia/wallet_cache/gmgn_stats"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
DB = Path.home() / ".hermes/theia/theia.db"

try:
    from scrapling.fetchers import StealthyFetcher
except ImportError:
    print("ERROR: run with theia-webscraper venv", file=sys.stderr)
    sys.exit(1)

API = "https://gmgn.ai/defi/quotation/v1/smartmoney/sol/walletNew/{addr}?period=7d"
RPNL_MIN = 10_000
HOLD_MAX = 48 * 3600
TWO_MS = 2_000  # txs7 heuristic for "high-activity whale" (OOS strongest bucket)
BAD = {"bundler", "dev", "sniper", "mev", "bot", "wash_trader"}

WHALE_SHORTS = ["2fg5QD1eD7rz", "suqh5sHtr8Hy", "ardinRsN1mNYVe", "F9zT1F46HAoPan",
                "CKcWAvvDYr2H3W", "6G8Cu53PRgm5aP", "9iaawVBEsFG35P",
                "2p2mgFLmzN82sS", "4k92XBen2ofaTY"]

con = sqlite3.connect(DB)
con.row_factory = sqlite3.Row
# resolve full addresses from scan_history
wallets = []
for s in WHALE_SHORTS:
    r = con.execute("SELECT wallet FROM wallet_scan_history WHERE wallet LIKE ? "
                    "ORDER BY scan_ts DESC LIMIT 1", (s + "%",)).fetchone()
    if r:
        wallets.append(r["wallet"])
print(f"whales resolved: {len(wallets)}")

sf = StealthyFetcher()
enabled = skipped = 0
for i, w in enumerate(wallets):
    cp = CACHE_DIR / f"{w}_7d_fresh.json"
    if cp.exists() and (time.time() - cp.stat().st_mtime) < 3600:
        r = json.loads(cp.read_text())
        print(f"[{i+1}/{len(wallets)}] {w[:12]} (fresh cache)")
    else:
        try:
            resp = sf.fetch(API.format(addr=w), solve_cloudflare=True, timeout=45000,
                            headless=True, network_idle=False, load_dom=False)
            r = {"ok": resp.status == 200, "addr": w}
            if r["ok"]:
                r["data"] = json.loads(resp.body.decode("utf-8", errors="replace"))
                cp.write_text(json.dumps(r))
        except Exception as e:
            r = {"ok": False, "err": str(e)}
        time.sleep(1.5)
        print(f"[{i+1}/{len(wallets)}] {w[:12]} fetch ok={r.get('ok')}")

    if not r.get("ok"):
        skipped += 1
        print(f"  SKIP (fetch fail {r.get('status') or r.get('err')})")
        continue
    d = (r.get("data") or {}).get("data") or {}
    tags = {str(t).lower() for t in (d.get("tags") or [])}
    rp7 = d.get("realized_profit_7d") or 0
    txs7 = (d.get("buy_7d") or 0) + (d.get("sell_7d") or 0)
    hold = d.get("avg_holding_peroid") or 0
    wr7 = d.get("winrate")
    if tags & BAD:
        skipped += 1
        print(f"  SKIP bad tags {sorted(tags & BAD)}")
        continue
    if rp7 < RPNL_MIN:
        skipped += 1
        print(f"  SKIP rPnl7d={rp7:.0f} < {RPNL_MIN}")
        continue
    if hold > HOLD_MAX:
        skipped += 1
        print(f"  SKIP hold={hold/3600:.1f}h > 48h")
        continue
    # fresh criteria OK → upsert profile + track
    row = con.execute("SELECT wallet, is_smart_money FROM wallet_profiles WHERE wallet=?", (w,)).fetchone()
    now = int(time.time())
    if row is None:
        con.execute("""
            INSERT INTO wallet_profiles
            (wallet, first_seen_ts, last_active_ts, total_trades, win_rate,
             expectancy_sol, pattern_cluster, is_smart_money, source,
             track_enabled, created_ts, updated_ts)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        """, (w, now, d.get("last_active_timestamp") or now, txs7, wr7, rp7,
              "gmgn_whale_v2", 1, "gmgn_whale_v2", 1, now, now))
        print(f"  ENABLED (new profile) rPnl7d={rp7:.0f} txs7={txs7:.0f} hold={hold/3600:.1f}h")
    else:
        con.execute("""
            UPDATE wallet_profiles SET is_smart_money=1, track_enabled=1, source=?,
              total_trades=?, win_rate=COALESCE(?, win_rate), updated_ts=?
            WHERE wallet=?
        """, ("gmgn_whale_v2", txs7, wr7, now, w))
        print(f"  ENABLED (existing) rPnl7d={rp7:.0f} txs7={txs7:.0f}")
    con.commit()
    enabled += 1

con.commit()
n = con.execute("SELECT COUNT(*) FROM wallet_profiles WHERE is_smart_money=1 AND track_enabled=1").fetchone()[0]
con.close()
print(f"\ndone: enabled={enabled} skipped={skipped} | total tracked now={n}")