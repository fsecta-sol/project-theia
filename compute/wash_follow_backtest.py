#!/usr/bin/env python3
"""What-if backtest: follow wash-tagged whale wallets (pipeline-style simulation).

Question (user): "mungkin kita harus backtest what if we follow wash trader
wallet, hasilnya gimana?"

Data reality check first: Helius enhanced API returns:
  - 6G8: 229 swaps / 122 buys / 36 mints (usable — trades via decoded routes)
  - 2fg5: only SELL rows decoded (buys hidden in un-decoded CPI routes)
  - suqh: txs are INITIALIZE_ACCOUNT/TRANSFER (non-SWAP; buys not visible)
  - ardin: 100% PUMP_FUN UNKNOWN with empty tokenTransfers (bonding-curve
    internal accounts — un-decoded by our transfer parser)
So the backtest runs on whatever decode coverage we have per wallet and the
result is per-wallet, honestly labeled (coverage = fraction of wallet buys we
can even see).

Method (mirrors pipeline v4 + source2 backtest, deterministic):
  - entry: for each visible buy, first 1-min cached candle at/after ts+30m
    (T+30m entry, like profile_discovered._compute) with liq/screen skip.
  - exit: candle +30 (30m hold) — the pipeline's live behavior — with
    hard-stop, TP2x ladder replaced by single exit at +30 candles.
  - costs: gas first_buy + gas + slippage (costs lib), notional 0.5 SOL.
  - provenance split: only candles the OHLCV cache has (all retro-fetched or
    organic — labeled by cache-file date).
Output: per-wallet expectancy/PF from compute/expectancy.py, with coverage note.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, "/home/hermes/project-theia")

from compute import costs, expectancy, gas_sim  # noqa: E402
from compute.volume_lowbuy_backtest import load_mints  # noqa: E402

WSOL = "So11111111111111111111111111111111111111112"
NOTIONAL = 0.5
ENTRY_LAG = 30 * 60
HOLD_CANDLES = 30

SWAPS = Path("/home/hermes/project-theia/compute/_wash_follow_swaps.json")


def sim_buy(buy_ts: int, rows: list, usd: float = 150.0) -> dict | None:
    entry_target = buy_ts + ENTRY_LAG
    ce = next((r for r in rows if r[0] >= entry_target), None)
    if not ce or ce[4] <= 0:
        return None
    entry_ts, entry_price = ce[0], ce[4]
    fwd = [r for r in rows if r[0] > entry_ts]
    if not fwd:
        return None
    ei = min(HOLD_CANDLES, len(fwd) - 1)
    exit_price = fwd[ei][4]
    if exit_price <= 0:
        return None
    slip = costs.slippage_estimate(NOTIONAL * usd, 5000, False)
    cost = gas_sim.swap_fee_sol(first_buy=True) + gas_sim.swap_fee_sol() + NOTIONAL * slip
    pnl = (NOTIONAL / entry_price) * exit_price - NOTIONAL - cost
    return {"entry_ts": entry_ts, "pnl_net": pnl}


def main():
    data = json.loads(SWAPS.read_text())
    mints = load_mints(min_candles=30)
    print(f"swap files loaded: {len(data)} wallets; mints cached: {len(mints)}\n")

    results = {}
    for w, swaps in data.items():
        tag = {"2fg5QD1eD7rzNNCsvnhmXFm5hqNgwTTG8p7kQ6f3rx6f": "2fg5[wash-tag,decode:SELL-only]",
               "suqh5sHtr8HyJ7q8scBimULPkPpA557prMG47xCHQfK": "suqh[clean-tag,decode:0-swap]",
               "ardinRsN1mNYVeoJWTBsWeYeXvuR9UUDGMsCDKpb6AT": "ardin[wash-tag,decode:0-swap]",
               "6G8Cu53PRgm5aPHxMaZRguYHJfaNxmnmgoR129cKMvJk": "6G8[wash-tag,decode:OK]"}.get(w, w[:8])
        buys = [s for s in swaps if s.get("side") == "buy" and s.get("quote_mint") == WSOL
                and s.get("base_mint")]
        sims, skipped = [], 0
        seen_mints = set()
        for b in buys:
            mint = b["base_mint"]
            rows = mints.get(mint)
            if not rows:
                skipped += 1
                continue
            r = sim_buy(int(b.get("ts") or 0), rows)
            if r:
                r["mint"] = mint
                sims.append(r)
        pnls = [s["pnl_net"] for s in sims]
        m = expectancy.evaluate(pnls) if pnls else {"n": 0}
        total_visible = len(buys)
        cov = (len(sims) / total_visible * 100) if total_visible else 0
        results[tag] = {"buys_visible": total_visible, "simulated": len(sims),
                        "no_chart": skipped, "coverage_pct": round(cov, 1), **m}
        print(f"== {tag} ==")
        print(f"   buys visible={total_visible}, simulated={len(sims)}, no-chart={skipped}, "
              f"coverage={cov:.0f}%")
        if pnls:
            print(f"   exp={m['expectancy']:+.4f} pf={m['profit_factor']:.3f} "
                  f"win={m['win_rate']:.2f} total={m['total']:+.3f}")
        else:
            print("   — no sim trades (decode/coverage limits)")

    json.dump(results, open("/home/hermes/project-theia/compute/_wash_follow_result.json", "w"),
              indent=2, default=str)
    print("\nsaved _wash_follow_result.json")


if __name__ == "__main__":
    main()