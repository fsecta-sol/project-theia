---
name: theia-archive
description: On full exit of a paper trade, compute final realized P&L (FIFO, net gas/priority/slippage) deterministically, write the immutable archive row, and feed the result back into the hypothesis' expectancy. Use immediately after a position goes flat.
---

# Theia — Archive Trade (close the loop)

The immutable ledger. Every closed trade must be fully reconstructable from stored fills.

## Procedure

1. Load the trade's fills: `theia-store` (entry + all exits, with reserve/fee snapshots).
2. `execute_code`: compute realized P&L (FIFO, net gas+priority+slippage) with
   `compute/pnl.py` + `compute/expectancy.py` — never by hand.
3. `theia-store.close_trade(trade_id, exit_ts, realized_pnl_sol, roi, expectancy_contrib,
   gas_sol_total, slippage_total, exit_reason)` → writes the append-only `archives` row and
   marks the paper trade archived.
4. Trigger `theia-evaluate-expectancy` for the hypothesis so its verdict reflects the new
   closed result.
5. If the trade revealed a new failure pattern (a rug type, a bad assumption):
   - Drop a sourced lesson into the vault inbox via `theia-obsidian.append_to_note(...)`.
   - Notify the human via Hermes channel:
     ```bash
     hermes send --to "telegram:-1003928226918:644" \
       "🧵 New failure pattern detected in trade {trade_id}: {reason}"
     ```

## Guardrails

- `archives` is **append-only** — never update a closed row.
- Paper P&L is an upper-ish bound on live (we model latency/gas/slippage, not adversarial fill
  denial or MEV). State that; don't imply paper == live.
