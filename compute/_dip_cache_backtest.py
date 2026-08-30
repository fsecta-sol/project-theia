#!/usr/bin/env python3
"""Dip-reversal backtest over the FULL disk OHLCV cache (hundreds of mints).

afk_backtest.load_ohlcv_rows reads per-mint OHLCV caches from
~/.hermes/theia/wallet_cache/ohlcv/*  (~627 files). Unlike price_snapshots
(only pools the smart-wallet pipeline touched), the cache covers many mints the
wallet pipeline screened — a much larger, less selection-biased pool set.

Same dip-reversal rule as compute/dip_reversal_backtest.py but driven from the
cache, with per-candle volume (index 5) available for a volume-confirmed variant.
Output = expectancy metrics per config + per-mint attribution + robustness.
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, "/home/hermes/project-theia")

from compute import expectancy
from compute import afk_backtest  # reuses load_ohlcv_rows

OHLCV_CACHE = Path.home() / ".hermes/theia/wallet_cache/ohlcv"
HARD_STOP = 0.55
NOTIONAL = 0.5


def load_all_mints(min_candles: int = 120) -> dict[str, list]:
    mints = {}
    for f in OHLCV_CACHE.iterdir():
        if not f.is_file():
            continue
        try:
            data = json.loads(f.read_text())
        except Exception:
            continue
        rows = data.get("rows", data) if isinstance(data, dict) else data
        # canonicalize: [[ts,o,h,l,c,(v),(mcap)],[...]]
        clean = []
        for r in rows:
            try:
                clean.append([int(r[0]), float(r[1]), float(r[2]),
                              float(r[3]), float(r[4])] +
                             ([float(r[5])] if len(r) > 5 and r[5] is not None else []))
            except (TypeError, ValueError, IndexError):
                continue
        if len(clean) >= min_candles:
            mints[f.stem] = sorted(clean, key=lambda x: x[0])
    return mints


def sim_mint(rows, dip, confirm_pct, exit_mult, time_stop, lookback=360,
             confirm_n=5, volume_gate=False):
    n = len(rows)
    highs = [r[2] for r in rows]
    lows = [r[3] for r in rows]
    closes = [r[4] for r in rows]
    has_v = len(rows[0]) > 5
    ath = [0.0] * n
    for i in range(n):
        ath[i] = max(highs[max(0, i - lookback):i + 1])

    sims = []
    i = 0
    while i < n:
        if not (closes[i] <= (1 - dip) * ath[i] and ath[i] > 0):
            i += 1
            continue
        entry_level = confirm_pct * ath[i]
        j = i + 1
        while j < min(n, i + 1 + confirm_n):
            vol_ok = (not volume_gate) or (has_v and rows[j][5] > 0)
            if vol_ok and closes[j] >= confirm_pct * ath[j] and lows[j] <= entry_level <= highs[j]:
                break
            j += 1
        if j >= min(n, i + 1 + confirm_n):
            i += 1
            continue
        entry_price = max(lows[j], entry_level)
        entry_price = min(entry_price, highs[j])
        if entry_price <= 0:
            i += 1
            continue
        exit_price = exit_ts = None
        reason = None
        for k in range(j + 1, n):
            if closes[k] <= HARD_STOP * entry_price:
                exit_price, exit_ts, reason = lows[k], rows[k][0], "hard_stop"
                break
            if closes[k] >= exit_mult * entry_price:
                exit_price, exit_ts, reason = lows[k], rows[k][0], "tp"
                break
            if rows[k][0] - rows[j][0] >= time_stop * 60:
                exit_price, exit_ts, reason = lows[k], rows[k][0], "time_stop"
                break
        if exit_price is None:
            exit_price, exit_ts, reason = closes[-1], rows[-1][0], "data_end"
        sims.append({"mint": "", "entry_ts": rows[j][0], "pnl": (exit_price / entry_price - 1.0) * NOTIONAL,
                     "reason": reason, "dip": dip})
        i = j + 1
    return sims


def main():
    mints = load_all_mints(min_candles=120)
    print(f"mints with >=120 candles: {len(mints)}")
    # how many have volume
    hasv = sum(1 for r in mints.values() if len(r[0]) > 5)
    print(f"mints with per-candle volume: {hasv}")

    # baseline
    for dip in (0.20, 0.30, 0.40):
        for cf in (0.85, 0.90, 0.95):
            sims = [s for r in mints.values() for s in sim_mint(r, dip, cf, 1.30, 120)]
            m = expectancy.evaluate([s["pnl"] for s in sims])
            print(f"dip={dip:.2f} cf={cf:.2f}: n={len(sims):4d} exp={m['expectancy']:+.4f} "
                  f"pf={m['profit_factor']:.3f} win={m['win_rate']:.3f}")

    # volume-gated variant on subset that has volume
    vg_mints = {k: r for k, r in mints.items() if len(r[0]) > 5}
    print(f"\n-- volume-gated (only mints w/ volume, n_mints={len(vg_mints)}) --")
    for vg in (False, True):
        for dip in (0.20, 0.30):
            sims = [s for r in vg_mints.values() for s in sim_mint(r, dip, 0.90, 1.30, 120, volume_gate=vg)]
            m = expectancy.evaluate([s["pnl"] for s in sims])
            print(f"dip={dip:.2f} volgate={vg}: n={len(sims):4d} exp={m['expectancy']:+.4f} "
                  f"pf={m['profit_factor']:.3f} win={m['win_rate']:.3f}")

    # outlier: drop top winners on baseline config
    sims = [s for r in mints.values() for s in sim_mint(r, 0.30, 0.90, 1.30, 120)]
    pnls = sorted([s["pnl"] for s in sims], reverse=True)
    print(f"\n-- outlier (dip=0.30 cf=0.90 exit=1.3) n={len(pnls)} --")
    for k in (1, 2, 5):
        m = expectancy.evaluate(pnls[k:])
        print(f"  drop top-{k}: n={len(pnls)-k} exp={m['expectancy']:+.4f} pf={m['profit_factor']:.3f} win={m['win_rate']:.3f}")


if __name__ == "__main__":
    main()