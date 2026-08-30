#!/usr/bin/env python3
"""Run the anti-falling-knife backtest baseline to audit the blind-entry gap."""
import json
import sys
sys.path.insert(0, "/home/hermes/project-theia")

from compute import afk_backtest

print("Loading dataset (smart-money wallets, API-free on caches)...")
ds = afk_backtest.load_dataset(only_smart=True, min_cached_candles=35)
print(f"dataset: mints_total={ds['mints_total']} mints_usable={ds['mints_usable']} "
      f"dropped_no_cache={ds['dropped_no_cache']}")

res = afk_backtest.run_afk_backtest(ds, sweep=[0.30, 0.50, 0.70])
print("\n=== BASELINE (blind T+30m entry, no chart filter) ===")
print(json.dumps(res["baseline"], indent=2))
print(f"n={res['baseline_n']} dominant_wallet={res['dominant_wallet']} "
      f"dominant_pct={res['dominant_pct']}")
print("\n=== AFK sweep (skip trade if entry close < (1-x)*peak_high) ===")
for k, v in res["sweep"].items():
    print(f"\n{k}: n={v['n']} skipped={v['n_skipped']}")
    print(f"  metrics={json.dumps(v['metrics'])}")
    print(f"  avg_drawdown_from_peak={v['avg_drawdown_from_peak']}")

# Save full result
with open("/home/hermes/project-theia/compute/_afk_result.json", "w") as f:
    json.dump(res, f, indent=2, default=str)
print("\nSaved to compute/_afk_result.json")