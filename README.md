# Project Theia — Solana Memecoin Paper-Trading Agent

**Theia** is a Hermes-driven, single-VPS paper-trading agent for the **Solana memecoin market**. It hunts a *mechanical, retail-reachable* edge through smart-wallet following (latency-tolerant ≤30 min), survival screening as a safety veto, disciplined exits, and slow-timing selectivity — not speed.

> Target: **expectancy > 0 AND profit_factor > 1**, net of latency + fees.  
> Win-rate ≥ 50% is a milestone, never the goal.

> **Current state (2026-08-28):** Phase 5 operational — forward paper validation — **not promoted.** Full status in AUDIT.md.

---

## What Theia Is (and Isn't)

| What Theia Does | What Theia Does NOT Do |
|-----------------|------------------------|
| Discover smart-money wallets via GMGN leaderboard (free scrape) | ❌ Launch sniping / front-running / same-block fills |
| Follow their new buys within ≤30 min (slow timing) | ❌ Latency arbitrage / MEV (speed — we lose) |
| Screen tokens for rug/honeypot/wash signals (safety veto) | ❌ Insider info / pre-announcement advantage |
| Backtest on stored history (deterministic compute) | ❌ Market-making at size / moving the book |
| Paper-trade with simulated fills (live gas + slippage + reserves) | ❌ Real money / signing keys anywhere |
| Record OHLCV into forward corpus for out-of-sample backtest | ❌ LLM does money math (PnL, sizing, expectancy) |

---

## Architecture (4 Layers)

```
L4  HERMES AGENT (profile "theia")
    ├─ orchestrates via skills + no-agent cron scripts
    ├─ cron · subagents · FTS5 memory · execute_code · Hermes channels
    └─ harness: grounding verifier + policy gate + budget breaker

L3  SKILLS (playbooks — named, auditable procedures)
    Repo (project-theia/skills/): 12 playbooks
    theia-learn-solana · theia-screen-token · theia-form-hypothesis
    theia-backtest · theia-paper-trade · theia-monitor · theia-archive
    theia-evaluate-expectancy · theia-build-tool · theia-xscraper
    theia-harness · theia-delegate
    (Profile adds theia-task-runner, theia-heartbeat, theia-cron-optimization,
     theia-dashboard-troubleshooting, theia-wallet-pipeline-audit + community skills)

L2  COMPUTE LIBS (deterministic math — execute_code only, in compute/)
    pnl.py (FIFO) · expectancy.py · wilson.py · gas_sim.py · amm_sim.py
    exit_engine.py · vol_exit_engine.py · screen_score.py · costs.py
    corpus.py · creator_reputation.py · creator_resolve.py · creator_veto.py
    discovery_filter.py · time_regime.py · harness.py · knowledge_graph.py
    backtest_engine.py · backtest_patched_wallet.py · run_hypotheses.py
    reconcile.py · wallet_profiler.py · paper_ledger.py

L1  MCP SERVERS (data boundary — secrets, rate-limit, cache; all 8 enabled)
    theia-store      → SQLite (only DB writer) — trades, screens, hypotheses, budget
    theia-chainrpc   → Helius RPC — wallet_swaps, wallet_pnl (own FIFO), gas
    theia-dexdata    → GeckoTerminal + DexScreener — pools, OHLCV, dex_bars
    theia-birdeye    → Birdeye free tier — token_ohlcv, token lists, top traders
    theia-security   → GoPlus — honeypot, mint/freeze, LP flags
    theia-xscraper   → X.com — profile lookup, tweets (keyless + cookie)
    theia-obsidian   → Vault gateway — read/write Obsidian notes
    theia-webscraper → Tiered web fetch — curl_cffi → StealthyFetcher (CF bypass)

L0  INFRA
    └─ VPS · SQLite WAL · DiskCache · token-bucket · .env secrets
```

### OHLCV data sources (three-tier fallback in `cron/wallet_common.py::ohlcv_for()`)

1. **Birdeye** (`token_ohlcv`) — primary for actively-traded tokens; USD quote; flat-candle filter rejects dead tokens.
2. **GeckoTerminal** (`pool_ohlcv`) — fallback for micro-caps / quiet pools; token quote (matches swap base).
3. **Dexscreener bars** (`dex_bars` MCP tool) — last resort for live windows; frontend binary endpoint, `res>=15` returns full history from pool creation; CF-bypassed via urllib (curl_cffi fallback).

---

## Non-Negotiable Principles

1. **VERIFY, DON'T SPECULATE.** No fact without corroboration and a reconstructable source.
2. **THE LLM NEVER DOES MONEY MATH.** PnL, expectancy, sizing, screening → `compute/` libs only.
3. **PAPER ONLY.** No signing keys. Fills simulated off live reserves/gas/fees. Fill-time reserve snapshots make archives reconstructable.
4. **STAY WITHIN FREE BUDGET.** All 8 MCPs use free API tiers; rate-limited + cached at the MCP boundary.
5. **EARNED AUTONOMY.** Scope widens only on audited, out-of-sample results.

---

## Quick Start

### Run Tests

```bash
# All golden tests (compute + MCP + obsidian + webscraper)
uv run --with pytest python -m pytest compute/tests/ \
  mcp/tests/test_mcp_servers.py mcp/tests/test_archive_integrity.py \
  mcp/theia-obsidian/tests/test_obsidian.py \
  mcp/theia-webscraper/tests/test_webscraper.py -q
```

As of 2026-08-28: 61 compute tests + 30 MCP/integration tests. The bare `python3` env has no pytest; use `uv run --with pytest`.

### Deploy to Hermes Server

```bash
# Dry run (prints plan, changes nothing)
./deploy/deploy.sh

# Deploy with backups
./deploy/deploy.sh --apply
```

**Deploy does:**
1. rsync repo root (`mcp/`, `compute/`, `profile/`, `cron/`) → `~/.hermes/theia/`
2. Copy skills → profile skills dir
3. Build per-MCP `.venv` + `pip install`
4. Append missing secrets from local `.secret` → `~/.hermes/.env`
5. Merge cron jobs (additive, backup first)

**Manual post-deploy:**
- Runtime scripts live in `~/.hermes/profiles/theia/scripts/` (deployed separately; repo `cron/` is the source of truth — verify hash after deploy)
- MCP servers register via `~/.hermes/profiles/theia/config.yaml` (`mcp_servers`)
- Smoke-test per layer → THEN enable cron jobs one at a time

---

## Workflow Loop (active no-agent pipeline)

```text
GMGN leaderboard discovery (hourly)
   ↓
wallet_profiles / wallet_scan_history (append-only scan corpus)
   ↓
qualified wallets (is_smart_money=1)
   ↓
wallet_swaps → new wallet buys (every 5 min, pages=1, 35m window)
   ↓
wallet_signals
   ↓
screen: liquidity ≥ $5k + price-cap ≤1.5x + wallet cap ≤5 open
   ↓
paper_trades + trade_fills (entry reserves snapshot)
   ↓
monitor: OHLCV / spot → exit_engine (hard stop -35%, TP 2x/4x, time stop 60m)
   ↓
archives + realized PnL (FIFO, reconstructable when reserves present)
```

### Active cron jobs (2026-08-28)

| Job | Schedule | Mode | Role |
|---|---:|---|---|
| `theia-wallet-pipeline` | every 5 min | no-agent | capture buys, screen, open paper trades (v4) |
| `theia-wallet-monitor` | every 5 min | no-agent | monitor, close/archive positions (v3, time60) |
| `theia-wallet-discovery` | hourly | no-agent | scrape/filter GMGN leaderboard wallets |
| `theia-source2-discovery` | every 6h | no-agent | trending→top_traders→GMGN-7d-gate wallet discovery (source 2) |
| `theia-pipeline-health` | every 5 min | no-agent | read-only freshness watchdog |

Disabled: `theia-discover-screen`, `theia-monitor`, `theia-backtest`, `theia-learn`, `theia-evaluate`, `theia-heartbeat`, `theia-label-corpus`, `theia-task-runner`, `theia-wallet-report`.

### Source-2 discovery (2026-08-29)

Second wallet-discovery source, additive to the GMGN leaderboard:
1. `trending_pools` (Dexscreener) — h24>=50 & h6>=50, liq>=30k, mcap<50M, SOL/USDC
2. `top_traders` (Birdeye 24h) — pre-filter: no bundler/dev/sniper/bot tags, realizedPnl>0, trade>=5
3. **GMGN 7d gate (mandatory)** — `realized_profit_7d>0` AND `tx30d<5000`, persistent bundler blacklist
4. Upsert `wallet_profiles` (is_smart_money=1, source='dex_trending')

Why the GMGN gate is mandatory: top_traders 24h alone passes churn bots that win on one pump but
bleed fees (validated: 7DyzpBs -$5.1k/7d, 6XPyYm -$9.2k/7d passed top_traders, failed GMGN 7d).
Scripts: `cron/discover_source2.py`, `cron/gmgn_wallet_stats.py` (run with webscraper venv).

### Pipeline parameters (deployed `wallet_pipeline_v4.py`)

| Param | Value |
|---|---:|
| `NOTIONAL` (size per trade) | 0.5 SOL |
| `LIQ_MIN` (liquidity gate) | $5,000 |
| `PRICE_CAP` (vs wallet exec price) | 1.5x |
| `MAX_OPEN_PER_WALLET` | 5 (raised 3→5 on 2026-08-28) |
| `ENTRY_WINDOW` | 30 min |
| `DETECT_GRACE` | 5 min |
| Exit: hard stop / TP ladder / time stop | -35% / 2x+4x (50/50) / 60 min |

---

## Project Structure

| Directory | What |
|-----------|------|
| `mcp/` | 8 MCP servers + `common/theia_net.py` (shared cache/rotator) |
| `compute/` | 23 deterministic libs + `tests/` (61 tests) |
| `skills/` | 12 skill playbooks (SKILL.md each) |
| `profile/` | Hermes identity prompts (theia, batch-enricher, builder) |
| `cron/` | Wallet pipeline scripts + wallet_common helpers |
| `deploy/` | `deploy.sh`, `deploy_sync.sh`, `env.additions` |

---

## Secrets

Store in repo-root `.secret` (gitignored):
- `HELIUS_API_KEY=key1,key2,key3,key4` (4-key round-robin)
- `BIRDEYE_API_KEY`, `ALCHEMY_API_KEY`
- `GOPLUS_APP_KEY` / `GOPLUS_APP_SECRET`
- Optional: `X_AUTH_TOKEN` + `X_CT0` for X.com cookies

Deploy copies values to server `.env` without ever printing them.

---

## Runtime DB (audited 2026-08-28)

| Table | Rows | Meaning |
|---|---:|---|
| `archives` | 11 | closed/archive records (all `reconstructable=0` — historical backlog) |
| `backtests` | 5 | stored backtest results (in-sample reference only) |
| `paper_trades` | 11 | paper trade lifecycle rows |
| `trade_fills` | 14 | entry/exit fill rows |
| `wallet_signals` | 29 | detected wallet buy signals |
| `wallet_profiles` | 315 | wallet profiles |
| `wallet_scan_history` | 6577 | append-only GMGN scan history |
| `wallet_trades` | 561 | wallet swap/trade history |
| `screens` | 86 | screening records |
| `tokens` / `pools` / `token_corpus` | 86 each | registry |
| `price_snapshots` | 14532 | OHLCV snapshots (forward corpus) |
| `price_snapshots_v2` | 0 | newer mint-level schema; empty |

**Paper-trade states:** archived 6, closed 5, open 0. **Archive PnL:** sum +0.626 SOL, naive PF 1.892 — **not a promotion result** (non-reconstructable backlog + small sample).

**2026-08-28 fixes:** new fills now carry reserve snapshots → `reconstructable=1` (verified); OHLCV three-tier fallback; `MAX_OPEN_PER_WALLET` 3→5.

---

## See Also

- AUDIT.md — full audit: phase gates, drifts, worklist, promotion contract
- ARCHITECTURE.md — full design, layer rules, storage split
- CLAUDE.md — MCP table, compute libs, known limitations, v3 pivot notes
