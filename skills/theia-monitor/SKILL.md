---
name: theia-monitor
description: Watch open paper positions on a tight timer and exit on hard-stop / take-profit ladder / trailing / time-stop, plus an emergency exit on rug/LP-pull/mint-live during the hold. Deterministic exit decisions via compute/exit_engine. Runs while any position is open.
---

# Theia — Monitor Positions

The exit rules are where the discipline edge lives. Every exit decision is deterministic —
the LLM never decides to hold/sell on a feeling.

## Procedure (each tick, e.g. 15–30s while positions open)

1. `theia-store.get_open_trades()`.
2. For each: refresh price (`theia-dexdata.pool_ohlcv` latest) → evaluate exits (`execute_code`
   `exit_engine.simulate_exit` against the live path so far, using the trade's exit params).
3. **Emergency exit (bypass ladder/stop)** if during the hold:
   - liquidity drops sharply in one block (LP pull), sell-sim starts failing / effective tax↑,
     mint authority becomes active / supply jumps, or deployer/top-holder dumps.
   Re-screen via `theia-security.token_security` on suspicion.
   - Immediately notify via Telegram:
     ```python
     from compute.telegram_notify import emergency_exit
     emergency_exit(trade_id, mint, reason="LP pull / authority change", pnl=realized_pnl)
     ```
4. On any exit: `theia-store.record_fill(kind='tp|stop|trail|time_stop|emergency', ...full
   snapshot...)`. When flat, hand to `theia-archive`.

## Guardrails

- **Data-health:** if the price feed is stale/RPC down → keep monitoring open positions, pause
  new entries; never strand a position because discovery went down.
- A modeled bad exit beats a paper bag that pretends it could have sold — always take the
  emergency exit at whatever the fill model says is left.
