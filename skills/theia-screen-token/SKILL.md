---
name: theia-screen-token
description: Decide whether a Solana token is safe/sellable enough to consider — the survival-screening edge. Combines GoPlus static flags + market signals into deterministic rug/wash/screen scores and a verdict. Use before any token enters a hypothesis test or paper trade.
---

# Theia — Screen Token (survival edge)

Most memecoins die to zero. Rejecting the −100% tail (rug/honeypot/wash/mint-live) raises
expectancy without needing speed — this is a slow edge we CAN win. No token is considered
without passing this.

## Procedure

1. **Static** — `theia-security.token_security(mint)` → mint/freeze authority, tax, honeypot,
   LP & holder concentration.
2. **Market** — `theia-dexdata.pairs_by_token([mint])` + `pool_trades(pool)` → liquidity, 24h
   volume, unique buyers vs total buys, top-wallet volume share.
3. **Score (deterministic, never eyeball)** — `execute_code`:
   ```
   from compute import screen_score
   res = screen_score.screen(sig, mkt)   # → verdict pass|watch|reject + rug/wash/screen scores
   ```
4. **Persist** — `theia-store.record_screen(mint, verdict, ...scores..., reject_reason)`.
   Cache is 24h but **re-screen on entry** (authorities/tax can change post-launch).
5. Only `verdict == "pass"` tokens proceed. `watch` = eligible for study, not trading.

## Guardrails

- Static flags describe the contract; they are **not proof**. Where a live sell-simulation is
  available, require it too before a real (paper) entry.
- Solana GoPlus coverage is partial → treat **mint/freeze-authority-revoked** as a hard gate
  even if other flags are missing.
- The scoring lives in `compute/screen_score.py` — never let the LLM invent a score.
