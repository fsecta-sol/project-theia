---
name: theia-form-hypothesis
description: Turn a documented Solana mechanic or wallet signal into a testable, deterministic selection/screening rule (a strategy hypothesis). Supports any token source (not just pump.fun) filtered by high-conviction wallet signals + standard security screens. Writes a rationale note in the vault and a machine-checkable rule_spec in theia-store.
---

# Theia — Form Hypothesis (generalized token source)

An edge idea is worthless until it is a **testable rule**. A hypothesis has two halves linked
by an id: the *why* (prose note in the vault) and the *what* (a deterministic `rule_spec` in
`theia-store`).

## Rule

The edge must be **reachable for us** (no capital/speed/info advantage) — a selection or
screening rule, not a timing race. If it needs to be fast, reject it.

**Token source is platform-agnostic:** any token is eligible if it passes security screening
AND is backed by a high-conviction wallet signal. No restriction to pump.fun.

## Procedure

1. State the hypothesis in one sentence + *why* it should work.
   Write it to the vault: `02-Projects/theia-hypotheses/H-<nnnn>.md`.

2. Encode the rule as JSON `rule_spec` — **no free parameters left to the LLM**.

   **Expanded rule_spec (v2):**
   ```json
   {
     "entry": {
       "min_liquidity_usd": 30000,
       "screen_verdict": "pass",
       "max_buy_tax": 0.05,
       "max_sell_tax": 0.05,
       "graduated": false,
       "min_age_min": 0,
       "max_age_min": 60
     },
     "wallet_filter": {
       "enabled": true,
       "min_wallet_winrate": 0.55,
       "min_wallet_pf": 1.2,
       "min_wallet_trades": 10,
       "max_wallet_age_days": 30,
       "source": "birdeye_top_traders"
     },
     "size": {
       "notional_sol": 0.5,
       "max_pct_liquidity": 0.02
     },
     "exit": {
       "hard_stop": -0.35,
       "tp_ladder": [[2,0.5],[4,0.25]],
       "trail_drop": 0.25,
       "time_stop_secs": 14400
     }
   }
   ```

   Wallet filter fields:
   - `enabled`: whether to require a high-conviction wallet buy signal
   - `min_wallet_winrate`: minimum win-rate (from `theia-chainrpc.wallet_pnl`)
   - `min_wallet_pf`: minimum profit factor
   - `min_wallet_trades`: minimum number of closed trades for statistical significance
   - `max_wallet_age_days`: how recent the wallet's track record must be
   - `source`: where to discover the wallet (`birdeye_top_traders`, `manual`, etc.)

3. `theia-store.upsert_hypothesis(id, title, note_path, rule_spec, status='draft')`.
   The store auto-persists `wallet_signals` if present in rule_spec.

4. Hand off to `theia-backtest`. Never promote a hypothesis on the reasoning alone.

## How to populate wallet_filter

If `wallet_filter.enabled` is true:

1. Discover candidate wallets:
   - `theia-birdeye.top_traders(token)` for a related token in the same niche, OR
   - `theia-birdeye.gainers_losers(want='gainers')` for globally strong wallets.
2. Filter by conviction:
   - `theia-chainrpc.wallet_pnl(wallet)` → win_rate, profit_factor, n_trades.
   - Keep wallets where `win_rate >= min_wallet_winrate` AND `pf >= min_wallet_pf` AND `n_trades >= min_wallet_trades`.
3. Store the filtered wallet list in the hypothesis note (NOT in rule_spec — rule_spec stays small).
4. At backtest time, the backtest engine checks: "was this token bought by any wallet in the filtered list within the entry window?"

## Guardrails

- One hypothesis = one falsifiable rule. If you can't say what result would kill it, it's not
  a hypothesis.
- Guard against survivorship: the rule must be evaluable point-in-time (only pre-decision data).
- Wallet PnL is our own FIFO compute (`theia-chainrpc.wallet_pnl`), not Birdeye paid tier.
- A wallet with 10 trades and 55% win-rate is thin; require `n_trades >= 20` for promotion.
- **No platform lock-in:** the hypothesis must work conceptually on any token that meets the
  entry + wallet + screen criteria, not just pump.fun mechanics.
