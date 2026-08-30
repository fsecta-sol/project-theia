#!/usr/bin/env python3
"""Survival & base-rate analysis on the stored OHLCV universe (API-free).

Answers the question every rule-to-date has implicitly failed:
   "Does the memecoin market, as observed by us, ever RECOVER?"
Quantify the base rate of recovery so future edge hypotheses can be judged
against reality instead of the LLM's priors.

Metrics per pool (1-min candles), computed deterministically:
  1. recovery_rate(X, W): of all candles that first dip >= X% below the running
     180-candle high, how many subsequently close >= (1-Xfear)*(dip-level-up) ...
     simplified: within W minutes after dipping X%, does price close back to
     ~50% of the high?  For X in (20,30,40,50).
  2. distribution of max-drawdown from running high for every candle.
  3. share of pools that EVER make a new high after a 30% dip.
  4. median "distance to death": given a dip, do prices keep falling (P(t+30 < t)?).
Output feeds any future entry rule with an honest prior. No trading.
"""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, "/home/hermes/project-theia")

from compute.volume_lowbuy_backtest import load_mints  # noqa: E402

LOOKBACK = 180  # running-high window (candles)
W = 60  # recovery window (minutes)


def analyze(mints: dict[str, list]) -> dict:
    # 1) recovery base rate + continued-fall rate after a dip
    rec = {x: {"dip_events": 0, "recovered": 0, "kept_falling": 0} for x in (0.20, 0.30, 0.40, 0.50)}
    # 2) made-new-high-after-dip per pool
    pools_new_high = 0
    pools_with_dip30 = 0
    n_pools = len(mints)
    # 3) every-candle drawdown distribution accumulator
    dd_buckets = {"<20%": 0, "20-40%": 0, "40-60%": 0, "60-80%": 0, ">80%": 0}
    dd_total = 0

    for mint, rows in mints.items():
        n = len(rows)
        highs = [r[2] for r in rows]
        closes = [r[4] for r in rows]
        ath = [0.0] * n
        for i in range(n):
            ath[i] = max(highs[max(0, i - LOOKBACK):i + 1])

        made_new_high_after_dip30 = False
        has_dip30 = False
        someday_new_high = max(closes[-1], highs[-1])
        # track future max close for each candle lazily via suffix max
        suf = [0.0] * (n + 1)
        for i in range(n - 1, -1, -1):
            suf[i] = max(closes[i], suf[i + 1])

        i = 0
        while i < n:
            if ath[i] <= 0:
                i += 1
                continue
            dd = 1 - closes[i] / ath[i]
            dd_total += 1
            if dd < 0.20:
                dd_buckets["<20%"] += 1
            elif dd < 0.40:
                dd_buckets["20-40%"] += 1
            elif dd < 0.60:
                dd_buckets["40-60%"] += 1
            elif dd < 0.80:
                dd_buckets["60-80%"] += 1
            else:
                dd_buckets[">80%"] += 1

            # for each threshold, measure recovery independently (count each candle
            # per threshold it crosses; no break so 30/40/50 msg bukan selalu 0)
            for x in (0.20, 0.30, 0.40, 0.50):
                if dd < x:
                    continue
                rec[x]["dip_events"] += 1
                # recovery: within W min a candle CLOSES back to <= X' drawdown,
                # i.e. price recovers above (1 - X) * high. Use same X. (A dip-30
                # "recovers" when it closes above 0.70*high.)
                end = min(n, i + W + 1)
                rec_win = any(closes[k] >= (1 - x) * ath[i] for k in range(i, end))
                if rec_win:
                    rec[x]["recovered"] += 1
                future = suf[min(i + 30, n - 1)]
                if future < closes[i] * 0.98:
                    rec[x]["kept_falling"] += 1
            if dd >= 0.30:
                has_dip30 = True
                # did any LATER candle close above a level that is 1.5x current (recovery)?
                if aten := (0.30 * ath[i]):
                    if suf[i + 1] >= 1.5 * closes[i]:
                        made_new_high_after_dip30 = True
            i += 1
        if has_dip30:
            pools_with_dip30 += 1
            if made_new_high_after_dip30:
                pools_new_high += 1

    def rp(r):
        return (100.0 * r["recovered"] / r["dip_events"]) if r["dip_events"] else None

    out = {
        "n_pools": n_pools,
        "n_pools_with_dip30": pools_with_dip30,
        "n_pools_recover_50pct_after_dip30": pools_new_high,
        "pct_pools_recover": round(100.0 * pools_new_high / max(pools_with_dip30, 1), 1),
        "recovery": {f"dip_{int(100*x)}": {"dip_events": rec[x]["dip_events"],
                                            "recovered": rec[x]["recovered"],
                                            "kept_falling": rec[x]["kept_falling"],
                                            "recover_pct": rp(rec[x])} for x in (0.20, 0.30, 0.40, 0.50)},
        "drawdown_distribution": dd_buckets,
        "candle_total": dd_total,
    }
    return out


if __name__ == "__main__":
    mints = load_mints(min_candles=120)
    print(f"pools analyzed: {len(mints)}")
    res = analyze(mints)
    print(json.dumps(res, indent=2))
    json.dump(res, open("/home/hermes/project-theia/compute/_survival.json", "w"), indent=2)