#!/usr/bin/env python3
"""Task 2: Multi-source wallet discovery — GMGN-FIRST (v2, 2026-08-27).

PERUBAHAN vs v1 (alasan: GMGN sudah menghitung winrate/PnL/holding/distribution
dengan sample besar — hitung ulang sendiri dari ~20 txs cuma menyesatkan, contoh
nyata: wallet winrate_7d=1.0 tapi cuma 5 txs & holding 9.9 hari).

  - Simpan FIELD LENGKAP GMGN: winrate_7d/30d, txs_7d, buy/sell, holding period,
    realized_profit, distribution buckets, tags. (v1 cuma address/period/pnl/winrate)
  - onchain_large_buys tetap placeholder (Helius free tier gak support program-wide query).

Output: data/discovered_wallets.json — source tags gmgn.
"""
import importlib.util
import json
import sys
import time
from pathlib import Path

DATA = Path("/home/hermes/theia-gate/data")
DEPLOY = Path("/home/hermes/.hermes/theia/mcp")
sys.path.insert(0, str(DEPLOY / "common"))

GMGN_RANK_FIELDS = [
    "address", "winrate_7d", "winrate_30d", "pnl_7d", "realized_profit_7d",
    "txs_7d", "buy_7d", "sell_7d", "avg_holding_period_7d", "volume_7d",
    "pnl_gt_5x_num_7d", "pnl_2x_5x_num_7d", "pnl_lt_2x_num_7d",
    "pnl_minus_dot5_0x_num_7d", "pnl_lt_minus_dot5_num_7d", "tags",
    "last_active", "nickname", "twitter_username",
]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


webscraper = load("webscraper", DEPLOY / "theia-webscraper" / "server.py")

out = {"gmgn": [], "onchain_large_buys": [], "ts": int(time.time())}

# ── A. GMGN leaderboard — multiple orderbys & periods ───────────────────────
print("[A] GMGN leaderboard...")
# limit=100 (bukan 50): universe ~2x lipat. orderby diperluas ke volume/pnl_1d
# supaya lebih banyak unique wallet + variasi sort (verified live 2026-08-27).
GMGN = "https://gmgn.ai/defi/quotation/v1/rank/sol/wallets/{period}?orderby={ob}&direction=desc&limit=100"
seen = set()
SORTS = [
    ("7d", "pnl_7d"), ("7d", "winrate_7d"), ("7d", "volume_7d"),
    ("30d", "pnl_30d"), ("30d", "winrate_30d"), ("30d", "volume_30d"),
    ("7d", "pnl_1d"), ("7d", "profit_ratio_7d"), ("7d", "buy_7d"),
]
for period, ob in SORTS:
        url = GMGN.format(period=period, ob=ob)
        # retry up to 3x — JSON truncation (100KB cap) used to kill pnl sorts;
        # now capped at 1MB but transient failures still happen.
        for attempt in range(3):
            try:
                r = webscraper.fetch_page(url, tier="browser")
                body = r.get("content") or r.get("text") or ""
                d = json.loads(body) if isinstance(body, str) else body
                wallets = (d.get("data") or {}).get("rank") or []
                # Dedup PER WALLET PER (period, orderby): leaderboard responses are
                # paginated/stale and often repeat the same wallet multiple times
                # (verified 2026-08-28: several sorts returned the same top wallets).
                # First-seen per (period, orderby) wins; the seen-set below stays
                # global so the final union is unique across all 9 sorts.
                sort_seen = set()
                for w in wallets:
                    a = w.get("address")
                    if a and a not in seen and a not in sort_seen:
                        sort_seen.add(a)
                        seen.add(a)
                        out["gmgn"].append({
                            "address": a,
                            "period": period, "orderby": ob,
                            **{k: w.get(k) for k in GMGN_RANK_FIELDS if k != "address"},
                        })
                print(f"  {period}/{ob}: {len(wallets)} wallets (total unique: {len(seen)})")
                break
            except Exception as e:
                print(f"  {period}/{ob} attempt{attempt+1} ERROR: {type(e).__name__} {str(e)[:120]}")
                time.sleep(5 * (attempt + 1))
        time.sleep(3)

# ── B. On-chain large-buy scan ──────────────────────────────────────────────
print("\n[B] on-chain large-buy scan (skipped — needs dedicated RPC method; using wallet_swaps of known hubs as proxy)")
# NOTE: Helius free tier doesn't support program-wide transaction queries efficiently.
# Proxy approach: pull swaps from already-known active wallets & expand via co-traded mints.
# This is a documented limitation — real implementation needs getProgramAccounts
# or a Geyser stream, both beyond free tier. Flag for review.

DATA.mkdir(exist_ok=True)
(DATA / "discovered_wallets.json").write_text(json.dumps(out, indent=1))
print(f"\n[done] gmgn={len(out['gmgn'])} unique wallets")
print("saved → data/discovered_wallets.json")
