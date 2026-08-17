---
name: theia-delegate
description: Delegate focused subtasks to Hermes subagents with precise specs, isolated context, and deterministic verification before accepting results back into Theia's main flow. Full Hermes-native; no external coding agents.
---

# Theia — Delegate Task (Hermes Subagent Only)

Theia's own model is small (`deepseek-v4-flash`). For heavy or parallel work, **delegate**
to Hermes subagents. The harness verifies every delegated result before it re-enters Theia's pipeline.

## Delegation targets

| Target | Model / Role | Best for | How Theia invokes |
|--------|-------------|----------|-------------------|
| **Hermes subagent** | Custom scoped profile | Parallel research, data enrichment, backtest replay, wallet PnL batch | Hermes native `subagent` or `execute_code` with isolated context |
| Future swarm worker | TBD (placeholder) | Horizontal scaling: multiple pool screens in parallel | Queue-based task dispatch via `theia-store.tasks` |

## Procedure

### 1. Decide what to delegate

Delegate when the task is:
- **Compute-heavy** — backtesting 1000+ tokens (parallelizable)
- **Data-heavy** — enriching a large wallet list with PnL + X profiles
- **Independent** — does not need Theia's real-time context to proceed

**Do NOT delegate** when the task needs Theia's qualitative judgment (promote/reject
a hypothesis, interpret a rug pattern, decide emergency exit).

### 2. Write a precise spec

A spec must include:
- **Inputs:** exact data/parameters needed
- **Outputs:** exact format and schema expected back
- **Budget:** max tokens / API calls / time allowed
- **Escalation triggers:** what should stop the subagent and return to Theia

**CRITICAL — Batch execution mode:**
When the subagent must perform the same operation N times (e.g., call `wallet_pnl` for 100 wallets),
the spec MUST instruct the subagent to use **`execute_code`** — generate a single Python block
that loops and calls the tools deterministically. **Never** let the subagent call tools one-by-one
through LLM reasoning (that burns N LLM shots).

| Pattern | Cost | Speed | When |
|---------|------|-------|------|
| `execute_code` Python loop | 1 LLM shot + N HTTP calls | Fast | Batch enrichment, backtest, screening |
| Serial LLM tool reasoning | N LLM shots + N HTTP calls | Slow | Interactive debugging only |

**Wrong spec:** "For each wallet, call theia-chainrpc.wallet_pnl"
**Right spec:** "Run execute_code: loop wallets, call wallet_pnl() inside Python, write results to DB"

### 3. Invoke the Hermes subagent

**Hermes subagent (research / enrichment / batch compute):**
```
Use Hermes native subagent capability:
  1. Create a scoped task in theia-store.tasks (type='delegate', payload={...})
  2. Hermes subagent picks up the task, runs with its own context window
  3. Subagent writes result back to tasks.result_ref
  4. Theia reads result_ref, harness verifies, merges
```

**Swarm worker (parallel backtest — future):**
```
For each hypothesis window, spawn N workers via theia-store.task queue:
  worker-1: backtest window A
  worker-2: backtest window B
  ...
Workers write partial results to backtests table with shared hypothesis_id.
Theia aggregates when all workers complete.
```

### 4. Verify before merging

Subagent result is a **proposal** until verified:

- **Data:** spot-check 3–5 samples against primary source. Mismatch → reject, retry.
- **Research:** check that every claim in the subagent output has a source citation.
  Missing sources → flag `[NEEDS-SOURCE]`.

### 5. Merge and record

After verification:
- Data: merge into theia-store (tokens, screens, backtests)
- Research: merge into vault inbox (`00-Inbox/_knowledge/...`)

Record in theia-store:
```python
theia-store.set_state(f"delegate:{task_id}", json.dumps({
  "target": "hermes-subagent",
  "spec_hash": hash_of_spec,
  "verified": True,
  "merged_at": now_ts,
}))
```

## Guardrails

- **Never trust subagent output blindly.** The harness applies the same grounding + policy
  checks to delegated work as to Theia's own LLM calls.
- **Keep subagents in isolated task scopes.** A broken subagent must not crash
  Theia's main loop.
- **Secrets stay in `~/.hermes/.env`.** Never pass API keys inside a delegation spec text.
- **Parallel workers write to separate rows / temp tables.** Aggregate only after all finish
  to avoid race conditions.

## Hermes capabilities (confirmed)

From ARCHITECTURE.md v2:
- Hermes native: `cron` · `subagents` · `FTS5 memory` · `execute_code` · `Hermes channels`
- Subagents are first-class — can run scoped tasks with their own context windows
- `execute_code` runs deterministic Python (compute libs) without LLM invocation
- Theia's harness stores context in SQLite, not in Hermes memory, so subagents can
  reconstruct state independently from the DB.

## Subagent profiles (defined in `profile/`)

| Profile | File | Role | Model |
|---------|------|------|-------|
| `theia-batch-enricher` | `SUBAGENT_BATCH.md` | Batch IO worker (discovery, wallet PnL, labeling) | `deepseek-v4-pro` @ high |
| `theia-builder` | `SUBAGENT_BUILDER.md` | Coding agent (compute libs, MCP tools, scripts) | `deepseek-v4-pro` @ high |

## Example pipeline: Wallet batch PnL enrichment

**Context:** Theia discovers 50 new tokens via `theia-dexdata.new_pools()`. Each token has
top traders from Birdeye. Theia wants to score every trader wallet (FIFO PnL, win-rate)
before screening tokens. Doing this serially = 50 wallet PnL calls = too slow.

**Delegation:**
1. Theia writes a scoped task to `theia-store.tasks`:
   ```json
   {
     "id": "batch-pnl-2026-08-07",
     "type": "delegate",
     "payload": {
       "wallets": ["wallet_abc...", "wallet_def...", ...],
       "min_trades": 10,
       "output_schema": "wallet_pnl_summary",
       "budget": {"max_api_calls": 60, "max_time_sec": 300}
     },
     "state": "ready"
   }
   ```

2. Hermes subagent (profile `theia-batch-enricher`) picks up the task.
   Its context window receives:
   - The task payload (wallets, min_trades)
   - Read-only access to `theia-store` (for caching)
   - No access to open paper trades or hypothesis state

3. Subagent runs `execute_code` with a Python loop calling `theia-chainrpc.wallet_pnl(wallet)`
   for each wallet, caches results, and writes back to `tasks.result_ref` as JSON array.

4. Theia reads `result_ref`, harness verifies 3 spot-checks against primary source,
   then merges the PnL data into `theia-store` for use by `theia-screen-token`.

**Result:** 50 wallets enriched in ~2 minutes via parallel subagents vs. ~10 minutes serial.

## Example pipeline: Parallel hypothesis backtesting with rich context

**Context:** Theia has 3 draft hypotheses (H-A, H-B, H-C) and wants to backtest each
against 3 different time windows (week-1, week-2, week-3). Total = 9 backtest runs.
Serial execution would take ~45 minutes. Delegating to 3 Hermes subagents cuts this
to ~15 minutes.

**How context is given to each subagent:**

1. **Theia prepares the shared context** (written to `theia-store` so all subagents read the same source of truth):
   ```python
   # Theia writes once — DB is the single source of truth
   theia-store.upsert_hypothesis("H-A", ..., rule_spec={...})
   theia-store.upsert_hypothesis("H-B", ..., rule_spec={...})
   theia-store.upsert_hypothesis("H-C", ..., rule_spec={...})
   # Price snapshots already cached in price_snapshots table
   ```

2. **Theia dispatches 3 scoped tasks**, each subagent gets only the slice it needs:
   ```json
   {
     "id": "backtest-H-A",
     "type": "delegate",
     "payload": {
       "hypothesis_id": "H-A",
       "windows": ["week-1", "week-2", "week-3"],
       "compute_libs_path": "~/.hermes/theia/compute",
       "output_table": "backtests",
       "constraints": {
         "max_positions_per_window": 100,
         "entry_lag_sec": 30
       }
     },
     "deps": [],
     "state": "ready"
   }
   ```
   (Similar tasks for H-B and H-C dispatched in parallel.)

3. **Hermes subagent (`theia-backtest-worker`) picks up its task.**
   Its context window is loaded with:
   - **Hypothesis rule_spec** (read from `theia-store.get_hypothesis(id)`)
   - **Cached price history** (`theia-store.get_price_path` per pool)
   - **Screen results** (`theia-store.get_latest_screen` per mint)
   - **Compute libs** imported via `execute_code` (deterministic, no LLM)
   - **NO access to:** open paper trades, Hermes channels (no notifications), budget ledger, other hypotheses' private data

4. **Subagent executes deterministically:**
   ```python
   # execute_code block inside the subagent
   from compute import amm_sim, gas_sim, exit_engine, pnl, expectancy
   # ... run backtest over the 3 windows, write results to backtests table
   ```

5. **Theia monitors task completion** via `theia-store.tasks` state polling.
   When all 3 subagents mark `state='done'`:
   - Theia runs `theia-evaluate-expectancy` on the aggregated backtests.
   - Harness verifies: check that every backtest row references a real `hypothesis_id`
     and that `expectancy` was computed by `compute/expectancy.py` (not LLM).

**Why this works:**
- The **DB is the shared context** — subagents don't need Theia's LLM memory.
- Each subagent is **scoped** to one hypothesis — no cross-contamination.
- `execute_code` inside subagents runs **pure compute libs** — fast, cheap, deterministic.
- If one subagent crashes, the others finish; Theia restarts the failed task from the DB.

## Example pipeline: Wallet conviction scoring for hypothesis entry

**Context:** Theia formed a hypothesis that requires "wallet conviction filter"
(min win-rate 55%, profit factor > 1.2). Before the hypothesis can enter backtest,
Theia needs to build the filtered wallet list from Birdeye top traders.

**Delegation:**
1. Theia dispatches task to subagent (`theia-wallet-screener`):
   ```json
   {
     "id": "wallet-conviction-build",
     "type": "delegate",
     "payload": {
       "token_mints": ["mint_A", "mint_B", ...],
       "discovery_source": "birdeye_top_traders",
       "filters": {
         "min_winrate": 0.55,
         "min_pf": 1.2,
         "min_trades": 10
       },
       "output": "filtered_wallets_json"
     }
   }
   ```

2. Subagent receives:
   - Token list (from Theia's discovery)
   - Filter thresholds (from hypothesis rule_spec)
   - Read access to `theia-store` for caching wallet PnL results

3. Subagent workflow:
   a. `theia-birdeye.top_traders(mint)` per token → raw wallet list
   b. Deduplicate wallets across tokens
   c. `theia-chainrpc.wallet_pnl(wallet)` per unique wallet (FIFO deterministic)
   d. Apply filters: win-rate ≥ 55%, PF ≥ 1.2, trades ≥ 10
   e. Write filtered list + metadata back to `tasks.result_ref`

4. Theia reads result, harness verifies:
   - Spot-check 3 wallets: re-run `wallet_pnl` directly, confirm numbers match.
   - Verify no wallet has `n_trades < 10` in the result.

5. Theia stores the filtered list in the hypothesis note, then hands off to `theia-backtest`.

**Result:** Wallet list built in parallel, verified, and ready for hypothesis testing
without Theia's main loop being blocked by 50+ API calls.
