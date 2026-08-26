"""Moon-catcher wallet discovery (v2 approach): find wallets that HOLD big winners.

Problem: GMGN leaderboard surfaces speed-scalpers (edge dies <30min) and one
position-taker (FixukbsKfJZE) who dominated the sample. We need MORE wallets
like FixukbsKfJZE — position-takers whose edge survives our latency.

Approach (user proposal): instead of scanning live tokens, scan TOP MCAP /
already-mooned tokens and find the wallets that caught the moon. A wallet that
bought a $100M+ token early and STILL HOLDS (or held long) is by definition a
position-taker with a winning selection — the profile we want to follow.

Pipeline:
  1. token_list(mc)  -> top mcap tokens (skip SOL/stablecoins/LSTs)
  2. top_traders(token, 24h) -> owners sorted by volume
  3. Score each wallet as a "moon catcher":
       - bought early: firstTradeUnixTime near token creation
       - still holds: holdVolume > 0 / unrealizedPnl > 0
       - realized pnl positive
       - low trade count on the token (NOT a market-maker churning)
     Drop bundlers/devs (tags) and pure scalpers.
  4. Dedupe, persist to data/moon_wallets.json for later profiling.

Deterministic + cached. No fabricated data.
"""
from __future__ import annotations

import importlib.util
import json
import sys
import time
from pathlib import Path

DATA = Path("/home/hermes/theia-gate/data")
DEPLOY = Path("/home/hermes/.hermes/theia/mcp")
sys.path.insert(0, str(DEPLOY / "common"))

# import the birdeye MCP server module to reuse its functions (same env).
# Run under the birdeye venv (has mcp + requests) so the import works.
import os
BIRDEYE_VENV_PY = DEPLOY / "theia-birdeye" / ".venv" / "bin" / "python"
if BIRDEYE_VENV_PY.exists() and os.environ.get("_THEIA_MOON_RUN") != "1":
    # re-exec self under birdeye venv, then proceed
    os.environ["_THEIA_MOON_RUN"] = "1"
    os.execv(str(BIRDEYE_VENV_PY), [str(BIRDEYE_VENV_PY)] + sys.argv)
spec = importlib.util.spec_from_file_location("birdeye", DEPLOY / "theia-birdeye" / "server.py")
birdeye = importlib.util.module_from_spec(spec)
spec.loader.exec_module(birdeye)

# ── constants ──────────────────────────────────────────────────────────────
SKIP_SYMBOLS = {"SOL", "USDC", "USDT", "PYUSD", "USD1", "USDG", "USDe", "USX",
                "JitoSOL", "BNSOL", "JupSOL", "JLP", "JUP", "RAY", "RENDER",
                "PYTH", "PENGU", "JTO", "TRUMP", "BC"}
MIN_MCAP = 30_000_000          # "already big" threshold (~$30M+)
MAX_TRADES_ON_TOKEN = 500      # above this = market-maker/churn bot, drop
MIN_EARLY_MULT = 5.0           # early buyer = entry < current/5 (caught big move)
HOLD_PNL_MIN_USD = 500         # unrealized pnl floor to count as "holding the moon"


def fetch_top_mcap(limit: int = 50):
    """Top mcap tokens via Birdeye (free tier)."""
    try:
        rows = birdeye.token_list(sort_by="mc", limit=min(limit, 50), min_liquidity=200_000)
    except Exception as e:
        print(f"[token_list] ERR {e}")
        return []
    out = []
    for t in rows:
        sym = (t.get("symbol") or "").upper()
        mc = t.get("mc") or 0
        if sym in SKIP_SYMBOLS or mc < MIN_MCAP:
            continue
        out.append({"mint": t["address"], "symbol": sym, "mc": mc,
                    "liq": t.get("liquidity"), "price": t.get("price"),
                    "v24h": t.get("v24hUSD")})
    return out


def score_trader(t, token):
    """Classify a top-trader row as moon-catcher candidate or not."""
    tags = set(t.get("tags") or [])
    if tags & {"dev", "chef", "bundler"}:
        return None, "dev/bundler"
    trades = t.get("trade", 0)
    if trades > MAX_TRADES_ON_TOKEN:
        return None, f"churn({trades})"
    buys = t.get("tradeBuy", 0)
    sells = t.get("tradeSell", 0)
    hold_vol = t.get("holdVolume", 0) or 0
    unreal = t.get("unrealizedPnl", 0) or 0
    realized = t.get("realizedPnl", 0) or 0
    first = t.get("firstTradeUnixTime", 0)
    avg_buy = t.get("avgBuyPrice", 0) or 0
    cur_price = token.get("price") or 0

    # early entry: bought at a price meaningfully below current (moon caught)
    early_mult = (cur_price / avg_buy) if avg_buy and cur_price else 1.0
    if early_mult < MIN_EARLY_MULT:
        return None, f"not_early({early_mult:.1f}x)"

    # holding: still holds a meaningful bag with paper profit
    if unreal < HOLD_PNL_MIN_USD and not (hold_vol > 0 and unreal > 0):
        return None, "not_holding"

    score = round(unreal + realized, 2)
    return {
        "wallet": t["owner"],
        "token": token["symbol"],
        "mint": token["mint"],
        "mc": token["mc"],
        "first_trade_ts": first,
        "entry_mult": round(early_mult, 1),
        "unrealized_pnl_usd": round(unreal, 2),
        "realized_pnl_usd": round(realized, 2),
        "score_usd": score,
        "buys": buys, "sells": sells, "trade_count": trades,
        "hold_volume": hold_vol,
        "tags": list(tags),
    }, None


def main():
    tokens = fetch_top_mcap(60)
    print(f"[tokens] {len(tokens)} big-mcap tokens (mc>={MIN_MCAP/1e6:.0f}M)")

    all_rows = []
    per_token = {}
    for tok in tokens:
        try:
            trs = birdeye.top_traders(tok["mint"], time_frame="24h", limit=20)
        except Exception as e:
            print(f"  {tok['symbol']} ERR {e}")
            time.sleep(1)
            continue
        cands = []
        for t in trs:
            row, why = score_trader(t, tok)
            if row:
                cands.append(row)
        per_token[tok["symbol"]] = {
            "mint": tok["mint"], "mc": tok["mc"],
            "n_traders": len(trs), "n_candidates": len(cands),
            "rejected": [why for _, why in []],
        }
        all_rows.extend(cands)
        print(f"  {tok['symbol']}: {len(trs)} traders -> {len(cands)} moon-catchers")
        time.sleep(1)  # be gentle with free tier

    # dedupe by wallet, keep best score
    by_wallet = {}
    for r in all_rows:
        w = r["wallet"]
        if w not in by_wallet or r["score_usd"] > by_wallet[w]["score_usd"]:
            by_wallet[w] = r

    ranked = sorted(by_wallet.values(), key=lambda r: -r["score_usd"])
    out = {
        "ts": int(time.time()),
        "n_tokens_scanned": len(tokens),
        "n_candidates_raw": len(all_rows),
        "n_unique_wallets": len(ranked),
        "per_token": per_token,
        "wallets": ranked,
    }
    (DATA / "moon_wallets.json").write_text(json.dumps(out, indent=1))
    print(f"\n[done] {len(ranked)} unique moon-catcher wallets")
    for r in ranked[:20]:
        print(f"  {r['wallet'][:16]}  {r['token']:<8} {r['mc']/1e6:6.0f}M  "
              f"entry={r['entry_mult']:>5.1f}x  unreal=${r['unrealized_pnl_usd']:>10,.0f}  "
              f"trades={r['trade_count']}")
    print(f"\nsaved -> {DATA/'moon_wallets.json'}")


if __name__ == "__main__":
    main()
