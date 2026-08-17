---
name: theia-paper-trade
description: Open a PAPER position for a promoted (or shadow) hypothesis when a screened token matches its entry rule — simulated off LIVE reserves/gas/fees with an honest latency handicap. No signing keys, ever. Use only for tokens that passed theia-screen-token.
---

# Theia — Paper Trade (open)

Paper only — but it must *hurt* like real: fill off live reserves + gas + priority fee, entered
at a worse/later price than the trigger (we can't win the latency race).

## Procedure

1. Confirm the token passed `theia-screen-token` within TTL (else re-screen). Confirm it
   matches the hypothesis' entry `rule_spec`.
2. Snapshot live state: `theia-dexdata.pool_ohlcv`/`pairs_by_token` (reserves, price),
   `theia-chainrpc.gas_oracle`.
3. Size + fill (`execute_code`):
   ```
   from compute import amm_sim, gas_sim
   fill = amm_sim.buy_fill(notional_sol, base_reserve, quote_reserve, fee)
   gas  = gas_sim.swap_fee_sol(cu_price_microlamports=..., first_buy=True)
   ```
   Respect `max_pct_liquidity` (never take a position our own model says moves the pool >~2%).
4. Persist: `theia-store.open_paper_trade(...)` + `record_fill(seq=0, kind='entry', ...,
   reserves_base, reserves_quote, priority_fee, native_usd, gas_sol, slippage)` — the full
   snapshot so PnL/gas/slippage re-derive later.
5. Notify via Hermes channel (low urgency — log only):
   ```bash
   hermes send --to "telegram:-1003928226918:644" \
     "📄 Paper trade opened: {mint} | Size: {size_sol} SOL | Hypothesis: {hypothesis_id}"
   ```
   (Inside a cron job, put this in the final response instead — Hermes auto-delivers it to the channel.)
6. Hand the open position to `theia-monitor`.

## Guardrails

- **No signing keys.** This is simulation off live values only.
- If live slippage from the fill model > the rule's cap, **do not enter** — log and skip.
- Portfolio guards: max concurrent positions, daily-loss halt, per-deployer exposure cap.
