#!/usr/bin/env python3
"""Recovery predictability — can any on-chart feature lift the ~26% base rate?

Question: of all dip events (close >= 30% below rolling 180-high), which
features at dip time predict recovery (close back above 0.70*high within 60m)?
If a cheap, point-in-time feature separates 26% → much higher, we have a
selectivity signal for a future entry rule. If nothing separates, the market is
effectively random at dip time and every chart rule is capped at ~26%.

Method (deterministic, API-free, on stored OHLCV):
  - features at dip candle i: drawdown depth, volume ratio (vol[i]/avg20),
    candle range (h-l)/c, gap from previous close, time since pool start
    (index-based), recent momentum (close[i] vs close[i-30]).
  - label: recovered=1 if any candle in [i, i+60] closes >= 0.70*ath[i].
  - report: recovery rate overall, then per feature-bucket (quartiles) so we
    can see monotonic separation without fitting a model.
"""
from __future__ import annotations

import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, "/home/hermes/project-theia")

from compute.volume_lowbuy_backtest import load_mints  # noqa: E402

LOOKBACK = 180
W = 60
DIP = 0.30
RECOVER = 0.70  # fraction of running high to "recover"


def bucket(v, qs, labels):
    for i, q in enumerate(qs):
        if v <= q:
            return labels[i]
    return labels[-1]


def main():
    mints = load_mints(min_candles=120)
    feats = defaultdict(list)  # feature -> list of (value, recovered)
    for mint, rows in mints.items():
        n = len(rows)
        highs = [r[2] for r in rows]
        closes = [r[4] for r in rows]
        lows = [r[3] for r in rows]
        vols = [max(r[5], 0.0) if len(r) > 5 else 0.0 for r in rows]
        ath = [0.0] * n
        for i in range(n):
            ath[i] = max(highs[max(0, i - LOOKBACK):i + 1])
        vol20 = [0.0] * n
        for i in range(n):
            w = vols[max(0, i - 20):i]
            vol20[i] = (sum(w) / len(w)) if w else 0.0
        suf = [0.0] * (n + 1)
        for i in range(n - 1, -1, -1):
            suf[i] = max(closes[i], suf[i + 1])

        for i in range(n):
            if ath[i] <= 0:
                continue
            dd = 1 - closes[i] / ath[i]
            if dd < DIP:
                continue
            # recovered within W? (close back above RECOVER*ath within 60m)
            end = min(n, i + W + 1)
            rec = any(closes[k] >= RECOVER * ath[i] for k in range(i, end))
            r = 1 if rec else 0
            feats["drawdown_depth"].append((dd, r))
            if vol20[i] > 0:
                feats["volume_ratio"].append((vols[i] / vol20[i], r))
            else:
                feats["volume_ratio"].append((0.0, r))
            rng = (highs[i] - lows[i]) / closes[i] if closes[i] > 0 else 0
            feats["candle_range"].append((rng, r))
            if i >= 1:
                gap = (closes[i] - closes[i - 1]) / closes[i - 1] if closes[i - 1] > 0 else 0
                feats["gap_prev_close"].append((gap, r))
            if i >= 30 and closes[i - 30] > 0:
                mom = closes[i] / closes[i - 30] - 1
                feats["momentum_30"].append((mom, r))
            # time since pool start (index proxy)
            feats["pool_age_idx"].append((i, r))

    print(f"pools: {len(mints)}")
    for fname, vals in feats.items():
        n = len(vals)
        rec_rate = 100.0 * sum(v for _, v in vals) / n
        vals_sorted = sorted(v for v, _ in vals)
        qs = [vals_sorted[int(n * q)] for q in (0.25, 0.5, 0.75)]
        labels = ["q1", "q2", "q3", "q4"]
        print(f"\n{fname}: n={n} overall_recovery={rec_rate:.1f}%")
        # per quartile recovery
        buckets = {l: [0, 0] for l in labels}  # (rec, tot)
        for v, r in vals:
            b = bucket(v, qs, labels)
            buckets[b][0] += r
            buckets[b][1] += 1
        for l in labels:
            tot = buckets[l][1]
            if not tot:
                continue
            if l == "q4":
                bound = f">{qs[2]:.3g}"
            else:
                bound = f"<={qs[labels.index(l)]:.3g}"
            print(f"  {l} ({bound}): recovery={100.0*buckets[l][0]/tot:.1f}%  (n={tot})")


if __name__ == "__main__":
    main()