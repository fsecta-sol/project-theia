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

## Rollout phases

Theia rolls out in gated phases — **knowledge first, trading later.** This encodes the
EARNED-AUTONOMY principle: each phase is gated by the previous phase's **Exit** criterion,
and cron jobs are enabled **one at a time** (in `~/.hermes/profiles/theia/cron/jobs.json`)
only after that phase's smoke test. **Empty trading tables are expected until their phase —
they mean "not yet," not "broken."** Do not switch a later phase on early.

- **Phase 0 — Foundation & deploy — ✅ DONE.** L1 MCP + L2 compute built & unit-tested;
  deployed to Hermes (profile `theia`); cron token-burn hygiene fixed (`theia-heartbeat`
  disabled; `theia-task-runner` runs as a `no_agent` 0-LLM script).
- **Phase 1 — Knowledge-first ("week 1") — 🟢 CURRENT.** Only `theia-learn` (2h) +
  `theia-task-runner` (infra) run; trading crons stay off. Work the 10 `docs/SEED_QUESTIONS.md`
  → auto-discovery red-string graph. **Exit:** all 10 seed questions answered (each note ≥1
  source); notes promoted `draft → verified` (define the rule this phase); graph spans the 5
  knowledge modules; screening primitives covered (LP burn/lock, mint/freeze authority,
  rug/honeypot, graduation).
- **Phase 2 — Discovery + screening (read-only, no trades).** Enable `theia-discover-screen`
  (+ `label-corpus`); fill `tokens`/`pools`/`screens`/`token_corpus`. Tune
  `discovery_filter.py`; validate `screen_score.py` against a known rug/grad corpus.
  **Exit:** target N tokens screened; grad/dead separation measured; every screen reconstructable.
- **Phase 3 — Hypothesis + backtest (API-free).** Enable `theia-form-hypothesis` +
  `theia-backtest` (`run_hypotheses.py` / `backtest_engine.py`); walk-forward on stored
  `price_snapshots`, gas + slippage applied. **Exit:** ≥1 hypothesis passing
  **expectancy > 0 AND profit_factor > 1** out-of-sample.
- **Phase 4 — Harness + guardrails live (the money-action gate).** Wire `harness.py`
  (`verify_grounding` + `policy_gate`) into the live loop; populate `llm_shots` +
  `context_windows` (both 0 today — built but never called); turn on the budget breaker
  (`budget_ledger`). Harden the regex-based grounding before trusting it to gate money.
  **Exit:** `llm_shots` logs every shot; `policy_gate` demonstrably DENY/ESCALATE on a test;
  `budget_ledger` tracks per-source spend.
- **Phase 5 — Paper trade + monitor.** Enable `theia-paper-trade` + `theia-monitor` +
  `theia-archive`; simulated fills off live reserves/gas/fees; `exit_engine.py` for exits.
  **Exit:** the success metric — **expectancy > 0 AND profit_factor > 1 net of latency + fees**,
  out-of-sample, over a meaningful sample.
- **Phase 6 — Scale via delegation (only when volume demands it).** Register subagent
  profiles (`theia-batch-enricher`, `theia-builder`) in Hermes config (only `theia` today);
  implement the `cron/task_runner.py` placeholder handlers; wire `_handle_delegate` → real
  subagent dispatch. **Trigger:** only when serial throughput is the bottleneck — not before.

## Theia v3 — smart-money pivot (research 2026-08-09)

**Why v3.** The v2 "static screening edge" was tested and is **weak**: fresh pump.fun tokens
are almost all clean at t0 (mint/freeze revoked by default, no honeypot flags, holders
un-indexed), so `screen_score` acts as little more than a **liquidity gate** — the rug is a
**forward** event (LP pull / dump), not a static launch-time flag. New edge candidate:
**follow verified-profitable Solana wallets, latency-tolerant (≤30 min)** — distinct from the
dead copy-trade thesis (which needed instant fills). Screening demotes to a **safety veto**,
not the edge.

### GMGN — the smart-money data source (verified working)

GMGN.ai already computes full per-wallet PnL / win-rate / PnL-distribution / tags for Solana
— it **collapses** the hardest part (a verified smart-wallet DB) from a build into a **scrape**.
- **Access:** Cloudflare-gated. `theia-webscraper` **Tier 2 (`tier="browser"`, StealthyFetcher)**
  bypasses the Turnstile challenge on the VPS (confirmed). Tier 1 (curl_cffi) gets 403 on the API.
  Response body is under the `content` key (not `text`).
- **Endpoints (verified):**
  - Smart-money leaderboard (ranked wallets + **full PnL distribution buckets** +
    `tags`): `/defi/quotation/v1/rank/sol/wallets/{period}?orderby=pnl_{period}&direction=desc&limit=N`
  - Per-wallet stats: `/defi/quotation/v1/smartmoney/sol/walletNew/{addr}?period=30d` (account-level
    `realized_profit`/`pnl` always populated; `winrate`/`token_num`/distribution only for
    GMGN-tracked wallets — else use the leaderboard, whose buckets ARE populated).
- **Key finding:** GMGN's account-level `realized_profit` is the correct **denominator** —
  it revealed a Birdeye `top_traders` "winner" (+32,725 SOL across winner tokens) is actually
  net **−742 SOL** (a losing high-freq bot, 700 trades/30d). Birdeye `top_traders` =
  volume-ranked → surfaces bots/MMs; GMGN = true account PnL. Use GMGN, not top_traders, to score wallets.
- **`winrate` = compute from distribution buckets:** `pnl_gt_5x_num`, `pnl_2x_5x_num`,
  `pnl_lt_2x_num` (wins) vs `pnl_minus_dot5_0x_num`, `pnl_lt_minus_dot5_num` (losses). Filter
  bots/wash via `tags` (drop `wash_trader`, `bot`) + trade-count.
- GMGN is **provider data** (like GoPlus) — a wallet-ranking *signal*, not reconstructable by
  us; our own trade PnL still comes from `pnl.py` FIFO on paper fills. Cache aggressively
  (browser tier is slow). Auth tokens are per-session and **never** committed.

### Fomo (fomo.family) — evaluated, DROPPED

Real API `prod-api.fomo.family` (Privy-JWT auth, no hard CF). But it's an **EVM-focused**
consumer social-trading/payments app (Base/BSC/ETH/Monad; Solana present but not the focus) —
its leaderboard is not Solana wallet-PnL analytics. **Not a fit** for Theia's Solana thesis;
GMGN stays primary. Reconsider only for cross-validation if it exposes Solana wallet PnL.

### v3 pipeline & build order

```
harvest GMGN smart wallets → filter (tags + distribution, drop wash/bot) → DB smart_wallets
  → watch their new early buys → SAFETY screen (screen_score = veto) → paper-enter ≤30min
  → exit_engine → expectancy → archive
```
New: `theia-gmgn` MCP (`smart_wallets`, `wallet_stats`), `smart_score.py` (skill from buckets +
tag filter), theia-store `smart_wallets`/`wallet_signals` tables, `theia-harvest-wallets` /
`theia-watch-wallets` skills, harvest (daily) + watch (<30 min) crons. Reuse: `exit_engine`,
`expectancy`, `amm_sim`, `backtest_engine`, `theia-webscraper`. Not needed: a Helius
`wallet_pnl_full` (GMGN provides). Demoted: `screen_score` → safety veto.

**Validate-first GATE (do this before building the live loop):** backtest "follow 30-min-late"
on GMGN smart wallets' *past* buys (Birdeye `txs asc` genesis + OHLCV via webscraper) →
out-of-sample expectancy. **+EV → build. ≤0 → thesis dead, stop.** All the pieces for this
gate are already proven working this session; it is one backtest, not a build. Maps to
rollout Phase 3.

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
| `theia-obsidian` | Filesystem | read_note, write_note, append_to_note, batch_read_notes, search_notes, get_backlinks | none | 7/7 |
| `theia-webscraper` | Web | fetch_page (tiered), fetch_pages, extract_text, detect_protection | none | 4/4 |

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

### Wallet Pipeline (built 2026-08-17 — persistent forward paper trading)

A 24/7 smart-money follow loop. Discovery finds **latency-tolerant** wallets (edge
survives a 30-min copy delay), then tracks/paper-trades them continuously. Deployed as
`no_agent` (0-LLM) cron scripts under the `theia` profile.

| Script | What | Schedule |
|--------|------|----------|
| `theia-wallet-pipeline.py` | Poll tracked wallets → capture new buys in T+25m to T+35m window → screen (liq>$5k + price cap) → open paper trades | every 5 min |
| `theia-wallet-monitor.py` | Apply `exit_engine` (stop -35% / TP 2x-4x / 60m time stop) to open positions → archive PnL | every 5 min |
| `theia-wallet-discovery.py` | Scrape GMGN leaderboard → profile wallets with latency-tolerance test (train/test split) → flag `is_smart_money=1` | every 6h |
| `theia-wallet-report.py` | Aggregate forward stats (expectancy/PF/win-rate) for the daily digest | daily 07:00 |

**Key timing fix (post-v3):** Pipeline now enters only in T+25m to T+35m window (instead of ASAP within 30min)
to match the backtest timing (T+30m simulated entry). Cron changed from every 10min to every 5min to
ensure precise window capture without missing signals. Time stop extended from 30min to 60min (proved
better in M-04: E +0.0122 improvement).

**Key learning (the discriminator):** wallet win-rate/PnL is the *wrong* filter — high
win-rate wallets are speed-scalpers whose edge evaporates <30 min. The correct filter is
**latency tolerance** (`latency_exp > 0` when followed 30-min late). Verified wallets
flagged `is_smart_money=1` in `wallet_profiles`.

**Safety mechanisms:** screening veto (liquidity <$5k, price cap 1.5x wallet exec, honeypot
flags) · per-wallet exposure cap (max 3 concurrent open positions) · dedup (one paper entry
per mint). **Data sources:** GMGN (wallet PnL/winrate/tags) · Helius RPC (swap history) ·
DexScreener (pool liq/price/volume) · Gecko OHLCV (forward price for exit sim) · local SQLite
(signals/trades/profiles/PnL). All pipeline jobs run `no_agent: true` (0 LLM tokens).

**Validation state:** in-sample cluster backtest n=16, win 62.5%, +0.015 SOL/trade, PF 1.57 —
NOT yet significant. Forward paper trading is the only way to prove it out-of-sample. Gate:
≥50 forward trades, then expect `expectancy > 0 AND profit_factor > 1` net of fees or kill.

Supporting compute: `compute/wallet_profiler.py` (FIFO round-trip matching + pattern
classification), `compute/tests/test_wallet_profiler.py`. DB tables: `wallet_profiles`,
`wallet_trades`, `wallet_clusters`, `wallet_signals`.

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
