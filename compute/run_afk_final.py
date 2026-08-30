#!/usr/bin/env python3
"""Final AFK + Holder re-backtest runner (run after backfill completes).

Re-runs both backtests on the fully-cached dataset and prints a summary.
Run manually after cron/backfill_ohlcv.py finishes:
    python3 compute/run_afk_final.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, "/home/hermes/project-theia")

from compute.afk_backtest import (
    load_dataset, run_afk_backtest, run_holder_backtest,
    run_peakprox_backtest, fmt_result,
)


def main():
    print("Loading dataset (cached OHLCV only)...", flush=True)
    ds = load_dataset(only_smart=True, min_cached_candles=35)
    print(f"mints_total={ds['mints_total']} mints_usable={ds['mints_usable']} "
          f"dropped_no_cache={ds['dropped_no_cache']}", flush=True)

    print("\n=== AFK (anti-falling-knife) backtest ===", flush=True)
    afk = run_afk_backtest(ds, sweep=[0.30, 0.50, 0.70])
    print(fmt_result(afk), flush=True)

    print("\n=== Peak-proximity (momentum-intact) backtest ===", flush=True)
    peak = run_peakprox_backtest(ds, max_dd_from_peak=[0.10, 0.20, 0.30])
    b = peak["baseline"]
    print(f"  baseline: n={b['n']} exp={b['expectancy']:.4f} PF={b['profit_factor']:.2f} "
          f"WR={b['win_rate']*100:.1f}%", flush=True)
    for k, v in peak["sweep"].items():
        m = v["metrics"]
        print(f"  {k}: n={v['n']} exp={m['expectancy']:.4f} PF={m['profit_factor']:.2f} "
              f"WR={m['win_rate']*100:.1f}%", flush=True)

    print("\n=== Holder-concentration backtest ===", flush=True)
    holder = run_holder_backtest(ds, top10_caps=[0.50, 0.90, 0.95, 0.99])
    print(f"baseline n={holder['baseline_n']} (mints_with_holder={holder['mints_with_holder_data']})",
          flush=True)
    b = holder["baseline"]
    print(f"  baseline: exp={b['expectancy']:.4f} PF={b['profit_factor']:.2f} "
          f"WR={b['win_rate']*100:.1f}%", flush=True)
    for k, v in holder["sweep"].items():
        m = v["metrics"]
        print(f"  {k}: n={v['n']} exp={m['expectancy']:.4f} PF={m['profit_factor']:.2f} "
              f"WR={m['win_rate']*100:.1f}%", flush=True)

    out = {"afk": afk, "peak": peak, "holder": holder}
    Path("/home/hermes/project-theia/artifacts").mkdir(exist_ok=True)
    Path("/home/hermes/project-theia/artifacts/afk_holder_final.json").write_text(
        json.dumps(out, indent=1, default=str))
    print("\n[final] saved artifacts/afk_holder_final.json", flush=True)


if __name__ == "__main__":
    main()
