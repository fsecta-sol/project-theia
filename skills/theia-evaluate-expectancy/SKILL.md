---
name: theia-evaluate-expectancy
description: Judge whether a hypothesis (from backtests + paper trades) clears the success gate — expectancy>0 AND profit_factor>1 net of latency+fees — vs baselines, and decide promote / keep-testing / reject. Use on a schedule and whenever a hypothesis accumulates new closed results.
---

# Theia — Evaluate Expectancy (the gate)

The single decision that matters. Win-rate is a milestone, never the verdict.

## Procedure

1. Gather closed results for the hypothesis: `theia-store` `backtests` + `archives` (paper).
2. `execute_code`: `expectancy.evaluate(trade_pnls)` → expectancy, profit_factor, wilson_low,
   win_rate, max_dd, `passes`.
3. Compare against **baselines** over the same tokens/window (a strategy that can't beat these
   proves nothing):
   - hold-SOL (0 in SOL terms), buy-every-screened, random-entry into the same tokens.
4. Decide:
   - **promote** → only if `passes` AND beats random-entry AND on a **fresh out-of-sample**
     window with enough trades (n≥20). Set hypothesis `status='promoted'`.
   - **keep-testing** → positive but thin/among-sample. Needs more forward data.
    - **reject** → fails the gate or doesn't beat random. Set `status='rejected'`, append the
      lesson to the vault inbox via `theia-obsidian.append_to_note(path="00-Inbox/_knowledge/hypothesis-lessons.md", content=..., section="<hypothesis-id>")` so the knowledge compounds.
 5. Escalate a promotion to the human via Telegram before it changes any live behavior:
    ```python
    from compute.telegram_notify import hypothesis_promoted
    hypothesis_promoted(hypothesis_id, expectancy, profit_factor, n_trades)
    ```
    Human must approve before the hypothesis is enabled for live paper trading.

## Guardrails

- Never promote on win-rate, on in-sample data, or on a sample that beats no baseline.
- Report the number honestly, including "inconclusive" — a null result is a real result.
- All math via `compute/expectancy.py`; the LLM only reads the verdict.
