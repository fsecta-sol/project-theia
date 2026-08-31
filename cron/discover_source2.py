#!/usr/bin/env python3
"""Source-2 wallet discovery: Dexscreener trending → Birdeye top_traders → GMGN 7d gate.

Second discovery source (ADDITIVE to GMGN leaderboard):
  1. trending_pools (Dexscreener) — pick tokens up in h24/h6, decent liq, small mcap
  2. top_traders (Birdeye 24h) per token — pre-filter: no bad tags, realizedPnl>0, trade>=5
  3. GATE WAJIB: gmgn_wallet_stats (7d) — realized_profit_7d > 0 AND not high-freq churn
     (buy_30d+sell_30d < 5000). This kills churn bots that win on 1 pump but bleed fees.
  4. Upsert wallet_profiles (source='dex_trending', is_smart_money=1) + scan_history.

RUNS WITH THE WEBSCRAPER VENV (has scrapling for CF bypass):
  /home/hermes/.hermes/theia/mcp/theia-webscraper/.venv/bin/python cron/discover_source2.py

Budget/run: ~1-3 trending + ~10 top_traders + ~5-10 gmgn_stats ≈ 20 calls. Free-tier safe.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path("/home/hermes/.hermes/profiles/theia/scripts")))
from wallet_common import ohlcv_for  # noqa: E402

DEPLOY = Path("/home/hermes/.hermes/theia/mcp")
DB = Path.home() / ".hermes/theia/theia.db"
GATE_DIR = Path.home() / "theia-gate/data"

# ── thresholds ──────────────────────────────────────────────────────────────
H24_MIN = 50.0        # h24 price change >= 50%
H6_MIN = 50.0         # h6 price change >= 50%
LIQ_MIN = 30_000      # reserve_in_usd >= $30k
MCAP_MAX = 50e6       # mcap < $50M (skip blue chips)
TRADE_MIN = 5         # top_trader min trades
# GATE V2 (2026-08-31, OOS-confirmed): rp7 floor 10k (was >0), churn cap removed
RPNL_7D_MIN = 10_000  # wallet must already print (OOS >=10k → +4,454/85%)
HOLD_MAX_S = 48 * 3600  # OOS: >48h → +19/54%
BAD_TAGS = {"bundler", "dev", "sniper", "chef", "fresh", "smart_trader",
            "bot", "wash_trader", "mev"}
# Persistent blacklist: wallets seen tagged bundler/dev on ANY token. Birdeye
# tags are per-token inconsistent (MRiYA4oN: clean on moonkey, bundler on
# PINK/OTC), so a wallet once flagged must stay flagged.
BLACKLIST_TABLE = "dex_trending_blacklist"
MAX_TOKENS = 12
PERIOD = "7d"
GMGN_API = ("https://gmgn.ai/defi/quotation/v1/smartmoney/sol/"
            "walletNew/{addr}?period={period}")
GMGN_CACHE = Path.home() / ".hermes/theia/wallet_cache/gmgn_stats"


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(name)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _f(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def token_passes(pool) -> tuple[bool, str]:
    attrs = pool.get("attributes") or {}
    pct = attrs.get("price_change_percentage") or {}
    h24, h6 = _f(pct.get("h24")), _f(pct.get("h6"))
    if h24 < H24_MIN and h6 < H6_MIN:
        return False, f"h24={h24:.0f} h6={h6:.0f}"
    liq = _f(attrs.get("reserve_in_usd"))
    if liq < LIQ_MIN:
        return False, f"liq=${liq:.0f}"
    mcap = attrs.get("market_cap_usd")
    if mcap is not None and _f(mcap) > MCAP_MAX:
        return False, f"mcap=${_f(mcap)/1e6:.0f}M"
    rel = pool.get("relationships") or {}
    quote_id = ((rel.get("quote_token") or {}).get("data") or {}).get("id", "")
    if "So11111111111111111111111111111111111111112" not in quote_id and \
       "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v" not in quote_id:
        return False, "quote_not_sol_usdc"
    return True, "ok"


def trader_prefilter(t) -> tuple[bool, str]:
    tags = {str(tg).lower() for tg in (t.get("tags") or [])}
    if tags & BAD_TAGS:
        return False, f"tag:{sorted(tags & BAD_TAGS)}"
    if _f(t.get("realizedPnl")) <= 0:
        return False, f"rpnl={_f(t.get('realizedPnl')):.1f}"
    if int(t.get("trade") or 0) < TRADE_MIN:
        return False, f"trade={int(t.get('trade') or 0)}"
    return True, "ok"


def gmgn_stats(addr: str, timeout_ms: int = 45000, use_cache: bool = True,
               cache_ttl: int = 86400) -> dict | None:
    """Fetch GMGN 7d wallet analytics (CF-bypass via standalone StealthyFetcher)."""
    GMGN_CACHE.mkdir(parents=True, exist_ok=True)
    cp = GMGN_CACHE / f"{addr}_{PERIOD}.json"
    if use_cache and cp.exists():
        try:
            age = time.time() - cp.stat().st_mtime
            if age < cache_ttl:
                return json.loads(cp.read_text())
        except Exception:
            pass
    try:
        from scrapling.fetchers import StealthyFetcher
    except ImportError:
        print("  [gmgn] ERROR: scrapling not available — run with webscraper venv")
        return None
    try:
        sf = StealthyFetcher()
        resp = sf.fetch(GMGN_API.format(addr=addr, period=PERIOD),
                        solve_cloudflare=True, timeout=timeout_ms,
                        headless=True, network_idle=False, load_dom=False)
        if resp.status != 200:
            return None
        body = resp.body if hasattr(resp, "body") else b""
        data = json.loads(body.decode("utf-8", errors="replace"))
        out = {"ok": True, "addr": addr, "period": PERIOD, "data": data}
        if use_cache:
            cp.write_text(json.dumps(out))
        return out
    except Exception as e:
        print(f"  [gmgn] {addr[:12]} err: {type(e).__name__} {str(e)[:80]}")
        return None


def gmgn_gate(stats) -> tuple[bool, str]:
    """GATE V2 (2026-08-31, OOS-confirmed): profit floor + wallet-momentum.

    Changes vs v1 (validated 2026-08-31 via gate_persistence sweep, n=269):
    - rp7 floor raised 0 -> 10_000 (OOS: rPnl7d>=10k → +4,454 fwd/85%+ve;
      >=50k → +16,302/89%; near-zero PnL wallets are the random mass).
    - churn cap tx30<5000 REMOVED (OOS: txs>=2000 → +6,431/95% monotonic;
      high-frequency whales were the BEST forward performers, e.g. our own
      +105k/7d whales were rejected by the old churn cap).
    - scalper guard: wr7>0.8 AND txs7<500 → reject (small-sample scalper,
      wr7>=0.80 was the WORST OOS bucket).
    Hold<48h retained (OOS: >48h → +19/54%).
    """
    if not stats or not stats.get("ok"):
        return False, "gmgn_unavailable"
    d = (stats.get("data") or {}).get("data") or {}
    rp7 = _f(d.get("realized_profit_7d"))
    if rp7 < RPNL_7D_MIN:
        return False, f"rPnl7d={rp7:.0f}"
    wr7 = _f(d.get("winrate"))
    txs7 = _f(d.get("buy_7d")) + _f(d.get("sell_7d"))
    if wr7 > 0.80 and txs7 < 500:
        return False, f"scalper_wr7={wr7:.2f}+txs7={txs7:.0f}"
    hold = _f(d.get("avg_holding_peroid"))
    if hold > HOLD_MAX_S:
        return False, f"hold={hold/3600:.1f}h"
    return True, f"rPnl7d={rp7:.0f} txs7={txs7:.0f}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pages", type=int, default=2)
    ap.add_argument("--max-tokens", type=int, default=MAX_TOKENS)
    ap.add_argument("--no-cache", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    # webscraper venv required for gmgn_stats (scrapling)
    try:
        import scrapling  # noqa: F401
    except ImportError:
        print("FATAL: run with webscraper venv:\n"
              "  /home/hermes/.hermes/theia/mcp/theia-webscraper/.venv/bin/python",
              file=sys.stderr)
        sys.exit(1)

    dexdata = load("dexdata", DEPLOY / "theia-dexdata" / "server.py")
    birdeye = load("birdeye", DEPLOY / "theia-birdeye" / "server.py")

    t0 = time.time()
    # ── 1. trending pools ───────────────────────────────────────────────────
    pools = []
    for page in range(1, args.pages + 1):
        try:
            batch = dexdata.trending_pools(network="solana", page=page) or []
            pools.extend(batch)
            if len(batch) < 20:
                break
        except Exception as e:
            print(f"[trending] page {page} err: {e}")
    print(f"[source2] trending: {len(pools)} pools", flush=True)

    # ── 2. token filter ─────────────────────────────────────────────────────
    toks = []
    for p in pools:
        ok, why = token_passes(p)
        if ok:
            toks.append(p)
    toks = toks[: args.max_tokens]
    print(f"[source2] token pass (h24>={H24_MIN} h6>={H6_MIN} liq>={LIQ_MIN}): {len(toks)}",
          flush=True)
    if not toks:
        print("[source2] no tokens — exit")
        return

    con = sqlite3.connect(DB)
    now = int(time.time())
    con.execute(f"""
        CREATE TABLE IF NOT EXISTS {BLACKLIST_TABLE} (
            wallet TEXT PRIMARY KEY,
            reason TEXT,
            first_seen_ts INTEGER
        )
    """)
    con.commit()

    # ── 3+4. top_traders per token → prefilter → gmgn gate → upsert ────────
    n_tok_err = 0
    n_prepass = 0
    n_gate_pass = 0
    n_gate_fail = 0
    n_new = 0
    n_dup = 0
    wallets_seen = {}
    reject_reasons = {}

    for i, p in enumerate(toks):
        mint = ((p.get("relationships") or {}).get("base_token") or {}).get("data", {}).get("id", "")
        mint = mint.replace("solana_", "")
        name = (p.get("attributes") or {}).get("name", "?")
        if not mint:
            continue
        # ── pool bookkeeping: upsert pool + record OHLCV (universe corpus) ──
        # Fixes: `pools` table was never updated by source2 (last pool 2026-08-21),
        # so no fresh-pool OHLCV corpus existed for universe-wide backtests.
        try:
            pool_addr = (p.get("relationships") or {}).get("base_token", {}).get("data", {}).get("id", "")
            pool_addr = pool_addr.replace("solana_", "")
            pool_id = (p.get("relationships") or {}).get("base_token", {}).get("data", {}).get("id", "")
            # pool_addr from the pair relationship if present, else fall back to base token id
            pair_rel = (p.get("relationships") or {}).get("base_token", {})
            pool_addr = (pair_rel.get("data") or {}).get("id", "") or mint
            pool_addr = pool_addr.replace("solana_", "")
            if pool_addr:
                con.execute(
                    "INSERT OR REPLACE INTO pools(pool_addr, mint, dex, amm_model, liquidity_usd,"
                    " reserves_base, reserves_quote, price, updated_ts) VALUES (?,?,?,?,?,?,?,?,?)",
                    (pool_addr, mint, (p.get("attributes") or {}).get("dex", "") or "unknown",
                     "v2", (p.get("attributes") or {}).get("liquidity_usd") or 0,
                     0.0, 0.0, (p.get("attributes") or {}).get("price_usd") or 0, now))
                con.commit()
                # record OHLCV (birdeye→gecko→dex ladder; v/mcap captured when present)
                try:
                    rows, src = ohlcv_for(dexdata, birdeye, mint, before_ts=0, ttl=300)
                    if rows:
                        n_rec = 0
                        for r in rows:
                            try:
                                ts = int(r[0])
                                o, h, l, c = float(r[1]), float(r[2]), float(r[3]), float(r[4])
                                v = float(r[5]) if len(r) > 5 and r[5] is not None else 0.0
                                mcap = float(r[6]) if len(r) > 6 and r[6] is not None else 0.0
                            except (TypeError, ValueError, IndexError):
                                continue
                            if con.execute("SELECT 1 FROM price_snapshots WHERE pool_addr=? AND ts=?",
                                           (pool_addr, ts)).fetchone():
                                continue
                            con.execute(
                                "INSERT OR IGNORE INTO price_snapshots"
                                "(pool_addr,ts,o,h,l,c,currency,v,mcap) VALUES (?,?,?,?,?,?,?,?,?)",
                                (pool_addr, ts, o, h, l, c, "token", v, mcap))
                            n_rec += 1
                        con.commit()
                        if n_rec:
                            print(f"  [corpus] {mint[:10]} +{n_rec} OHLCV rows (src={src})", flush=True)
                except Exception as e:
                    print(f"  [corpus] {mint[:10]} ohlcv err {type(e).__name__}", flush=True)
        except Exception as e:
            print(f"  [corpus] {mint[:10]} pool err {type(e).__name__}", flush=True)
        try:
            traders = birdeye.top_traders(token_addr=mint, time_frame="24h", limit=10)
        except Exception as e:
            n_tok_err += 1
            print(f"  [{i+1}/{len(toks)}] {name[:12]} top_traders err: {type(e).__name__}")
            continue
        clean = []
        for tr in traders or []:
            tags = {str(tg).lower() for tg in (tr.get("tags") or [])}
            if tags & BAD_TAGS:
                # persist blacklist: tagged bad on ANY token → never tracked
                owner_bad = tr.get("owner")
                if owner_bad:
                    con.execute(
                        f"INSERT OR IGNORE INTO {BLACKLIST_TABLE} (wallet, reason, first_seen_ts) "
                        "VALUES (?,?,?)",
                        (owner_bad, f"tag:{sorted(tags & BAD_TAGS)}", now))
                continue
            ok, why = trader_prefilter(tr)
            if ok:
                clean.append(tr.get("owner"))
        con.commit()
        n_prepass += len(clean)
        print(f"  [{i+1}/{len(toks)}] {name[:14]:<14} prefilter clean={len(clean)}/{len(traders or [])}",
              flush=True)
        for owner in clean:
            wallets_seen[owner] = wallets_seen.get(owner, 0) + 1
        time.sleep(0.4)

    print(f"\n[source2] prefilter clean wallets: {len(wallets_seen)}", flush=True)

    # ── GMGN 7d gate on prefilter-passed wallets ────────────────────────────
    for owner in sorted(wallets_seen):
        # blacklist check: once tagged bad anywhere, never track
        bl = con.execute(f"SELECT 1 FROM {BLACKLIST_TABLE} WHERE wallet=?",
                         (owner,)).fetchone()
        if bl:
            n_gate_fail += 1
            print(f"  [gate] {owner[:14]} REJECT blacklisted")
            con.execute("""
                INSERT OR IGNORE INTO wallet_scan_history
                (wallet, scan_ts, gate_pass, gate_reason)
                VALUES (?,?,0,?)
            """, (owner, now, "dex_trending_reject:blacklisted"))
            continue
        stats = gmgn_stats(owner, use_cache=not args.no_cache)
        ok, why = gmgn_gate(stats)
        if not ok:
            n_gate_fail += 1
            reject_reasons[why.split("=")[0]] = reject_reasons.get(why.split("=")[0], 0) + 1
            print(f"  [gate] {owner[:14]} REJECT {why}")
            # record rejection in scan_history
            con.execute("""
                INSERT OR IGNORE INTO wallet_scan_history
                (wallet, scan_ts, gate_pass, gate_reason)
                VALUES (?,?,0,?)
            """, (owner, now, f"dex_trending_reject:{why}"))
            continue
        n_gate_pass += 1
        print(f"  [gate] {owner[:14]} PASS {why}")
        con.execute("""
            INSERT OR IGNORE INTO wallet_scan_history
            (wallet, scan_ts, gate_pass, gate_reason)
            VALUES (?,?,1,?)
        """, (owner, now, f"dex_trending_pass:{why}"))

        if args.dry_run:
            continue
        # upsert wallet_profiles
        row = con.execute("SELECT wallet, is_smart_money FROM wallet_profiles WHERE wallet=?",
                          (owner,)).fetchone()
        if row and row[1] == 1:
            n_dup += 1
            continue
        d = ((stats or {}).get("data") or {}).get("data") or {}
        rp7 = _f(d.get("realized_profit_7d"))
        wr = d.get("winrate")
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
            """, (owner, now, now, int(_f(d.get("buy_7d"))) + int(_f(d.get("sell_7d"))),
                  int(_f(d.get("buy_7d"))), int(_f(d.get("sell_7d"))), 0,
                  None, None, None, None,
                  _f(wr) if wr is not None else None, None,
                  rp7, "dex_trending", 1, "dex_trending", now, now))
        else:
            con.execute("""
                UPDATE wallet_profiles SET is_smart_money=1, source=?,
                  win_rate=COALESCE(?, win_rate), expectancy_sol=?,
                  last_active_ts=MAX(last_active_ts, ?), updated_ts=?
                WHERE wallet=?
            """, ("dex_trending", _f(wr) if wr is not None else None, rp7, now, now, owner))
            n_new += 1
    con.commit()

    n_tracked = con.execute(
        "SELECT COUNT(*) FROM wallet_profiles WHERE is_smart_money=1").fetchone()[0]
    con.close()

    print("\n=== SOURCE-2 DISCOVERY DIGEST ===")
    print(f"tokens={len(toks)} tok_err={n_tok_err} prefilter_clean={n_prepass} "
          f"gmgn_pass={n_gate_pass} gmgn_fail={n_gate_fail} "
          f"new={n_new} dup={n_dup} tracked_total={n_tracked} "
          f"took={time.time()-t0:.0f}s")
    print("reject reasons:", reject_reasons)
    print("saved scan_history rows; wallet_profiles upserted.")


if __name__ == "__main__":
    main()
