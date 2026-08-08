---
name: theia-backtest
description: Test a hypothesis' rule_spec against STORED history (API-free) using the deterministic fill + exit + expectancy libs, point-in-time to avoid survivorship. Writes a backtest row and updates the hypothesis' best metrics. Use after form-hypothesis and to re-test on new data.
---

# Theia — Backtest (API-free)

Runs entirely on cached history in `theia-store` — so it works even when every API is
rate-limited. Point-in-time: select on data before each decision, evaluate forward.

## Procedure

1. Load the hypothesis: `theia-store.get_hypothesis(id)` → `rule_spec`.
2. Pull the candidate set + their stored `price_snapshots` / `screens` from `theia-store`
   (data fetched earlier by discovery/screen skills; do not fetch live here).
3. For each candidate that passes the rule's entry+screen filter **using only pre-entry data**:
   `execute_code`:
   ```
   from compute import amm_sim, gas_sim, exit_engine, pnl, expectancy
   # entry fill (amm_sim) at detection lag → exit_engine over the forward path → per-trade PnL
   ```
   Model **detection latency** honestly (fill at entry_ts + N; sweep N). Subtract gas (gas_sim).
4. `metrics = expectancy.evaluate(trade_pnls)` → expectancy, profit_factor, win_rate, max_dd.
5. `theia-store.record_backtest(id, hypothesis_id, window, params, n_trades, expectancy,
   profit_factor, win_rate, max_dd)` (auto-updates the hypothesis' best metrics).
6. Report the latency curve. If even at 0-lag it fails the gate, the hypothesis is dead — say so.

## Guardrails

- **Leakage guard:** assert no post-decision data touches the entry/selection step.
- Minute-OHLCV can't resolve sub-minute latency — state that; don't over-claim a latency result.
- The verdict is expectancy>0 AND profit_factor>1 — never win-rate alone.
