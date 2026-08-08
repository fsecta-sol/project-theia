# CLAUDE.md

This file provides guidance to Claude Code when working with code in this repository.

## What this repository is

**Project Theia** — a single-VPS, Hermes-Agent-driven paper-trading agent for the
**Solana memecoin market**. Runs under a Hermes profile named **"Theia"**. All code
lives in repo root — MCP servers, compute libs, skills, cron, deploy.

## Success metric

Target is **expectancy > 0 AND profit_factor > 1**, net of latency + fees. Win-rate >= 50%
is a milestone, not the target. Route every P&L/screening number through deterministic
`compute/` libs, never the LLM.

## Non-negotiable principles

1. **VERIFY, DON'T SPECULATE.** No fact without corroboration and a reconstructable source.
2. **THE LLM NEVER DOES MONEY MATH.** PnL, expectancy, sizing, screening → compute libs only.
3. **PAPER ONLY.** No signing keys anywhere; fills simulated off live reserves/gas/fees.
4. **STAY WITHIN FREE BUDGET.** All 6 MCPs use free API tiers only. 28/29 tools tested.
5. **EARNED AUTONOMY.** Scope widens only on audited, out-of-sample results.

## Architecture — implemented

### MCP servers (L1 — data boundary)

| MCP | Source | Key tools | Auth | Status |
|-----|--------|-----------|------|--------|
| `theia-store` | SQLite | token/pool/screen/hypothesis/trade CRUD, budget, heartbeat, **llm_shots**, **context_windows**, **knowledge_links** | none | 12/12 |
| `theia-chainrpc` | Helius 4-key | wallet_swaps, wallet_pnl (own FIFO), creator_tokens, creator_history, gas_oracle, **token_creator** | API keys | 6/6 |
| `theia-dexdata` | GeckoTerminal + Dexscreener | new_pools, trending_pools, pool_ohlcv, token_pools, pairs_by_token | keyless | 5/5 |
| `theia-birdeye` | Birdeye free | token_list, top_traders, gainers_losers (wallet_pnl needs paid) | API key | 3/4 |
| `theia-security` | GoPlus | token_security (honeypot/mint/freeze/LP) | keyless | 1/1 |
| `theia-xscraper` | X.com | profile_lookup (keyless), search_tweets, user_tweets, user_by_login (cookie) | keyless/cookie | 5/5 |

Shared infrastructure: `mcp/common/theia_net.py` — DiskCache, ApiKeyRotator (round-robin multi-key), request_json (jittered-backoff HTTP), get_secret/get_secrets (env → .env → .secret).

### Compute libs (L2 — deterministic math)

| Lib | What |
|-----|------|
| `pnl.py` | FIFO realized/unrealized wallet P&L — `fifo_trade_pnls()`, `wallet_pnl_summary()` |
| `expectancy.py` | Expectancy, profit_factor, Sharpe-like |
| `wilson.py` | Wilson score confidence intervals |
| `gas_sim.py` | Solana fee estimation |
| `amm_sim.py` | Constant-product AMM swap sim |
| `exit_engine.py` | Stops, TP ladder, trail, time exits |
| `screen_score.py` | Rug/wash/screen scoring |
| **harness.py** | **Agent harness — grounding verifier, policy gate (ALLOW/DENY/ESCALATE), context window tracker, budget breaker** |
| **knowledge_graph.py** | **Auto-discovery red-string graph — follow related concepts from web content (AMM→DLMM→Meteora)** |
| `costs.py` | Fee & slippage model (conservative round-trip estimates) |
| `corpus.py` | Token labeling — graduated / dead / bonding detection |
| `creator_reputation.py` | Creator blacklist analysis |
| `time_regime.py` | Launch-time regime classification (descriptive) |
| `discovery_filter.py` | Optimize liq/vol thresholds to separate grads from deads |
| `backtest_engine.py` | **Walk-forward backtest engine — point-in-time entry/exit sim, wallet filter, gas+slippage** |
| `run_hypotheses.py` | Phase 1 backtest orchestrator (H1/H5/H6) |
| **reconcile.py** | **Boot reconciler — recover open trades, interrupted tasks, draft hypotheses from DB on crash** |

### Profiles (Hermes identity)

| Profile | File | Role | Model |
|---------|------|------|-------|
| `theia` | `profile/IDENTITY.md` | Main orchestrator | `deepseek-v4-flash` |
| `theia-batch-enricher` | `profile/SUBAGENT_BATCH.md` | Batch IO worker | `deepseek-v4-pro` |
| `theia-builder` | `profile/SUBAGENT_BUILDER.md` | Coding agent | `deepseek-v4-pro` |

### Cron / Infra

| Script | What |
|--------|------|
| `cron/task_runner.py` | **Persistent queue worker — poll tasks, resolve deps, retry, execute handlers, 0 LLM** |
| `cron/theia-jobs.json` | Hermes cron schedule (8 jobs, all `enabled=false` until smoke test) |
| `deploy/deploy.sh` | Additive deploy to VPS with backups |

### Skills (L3 — Theia's playbooks)

`theia-learn-solana`, `theia-screen-token`, `theia-form-hypothesis`, `theia-backtest`,
`theia-evaluate-expectancy`, `theia-paper-trade`, `theia-monitor`, `theia-archive`,
`theia-build-tool`, `theia-xscraper`, **theia-harness**, **theia-delegate**

### Creator/wallet P&L pipeline (the edge)

```
Birdeye top_traders(token) → wallet
  → theia-chainrpc.wallet_pnl(wallet)     # own FIFO — realized + unrealized
  → theia-chainrpc.creator_tokens(wallet) # what did they create?
  → theia-xscraper.profile_lookup(handle) # who are they on X?
  → theia-store: track wallet reputation over time
```

`wallet_pnl` is our own deterministic P&L: Helius swaps (free) + Dexscreener prices (free) + FIFO compute. No Birdeye paid tier needed.

## Known limitations

- `theia-birdeye.wallet_pnl()` needs paid tier → use `theia-chainrpc.wallet_pnl()` instead
- `creator_tokens()` detects direct SPL creates only, not pump.fun CPI creates
- `theia-xscraper.search_tweets()` without cookies returns 0 tweets (JS-rendered page)
- OHLCV pool addresses from gecko listings have `solana_` prefix → `_strip_net()` handles it
- StealthyFetcher/Playwright needs system deps (not yet sudo-installed on VPS)

## Secrets

Keys in repo-root `.secret`. Current: `HELIUS_API_KEY=key1,key2,key3,key4` (4-key round-robin),
`ALCHEMY_API_KEY`, `BIRDEYE_API_KEY`, `GOPLUS_APP_KEY`/`GOPLUS_APP_SECRET`.
Optional: `X_AUTH_TOKEN` + `X_CT0` for cookie-based X.com.

## Working conventions

- Rate-limit + cache at the MCP boundary, not in skills
- Every MCP server has its own `.venv` with `mcp>=1.2.0,<2.0.0`
- Theia-store is the only DB writer (`~/.hermes/theia/theia.db`, SQLite WAL)
- Skills define procedures; the LLM orchestrates, never invents money math
- **Batch = `execute_code`, never serial LLM.** A task repeated N times (e.g., wallet PnL for 100 wallets) must be wrapped in a single `execute_code` Python block. `execute_code` = deterministic interpreter, 0 LLM tokens. Serial LLM reasoning = N shots, expensive and slow.
- **Secrets in repo-root `.secret` — must be in `.gitignore` (`.secret`, `.env`, `*.db`). Never commit keys.**
- Test before declaring done — 38 golden tests pass (compute + backtest + runner/reconcile + MCP), 28/29 tools verified with real API calls
- Compute libs imported via `compute.xxx` (theia root on sys.path)
