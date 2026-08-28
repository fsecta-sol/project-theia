# Theia Full Project Audit

**Audit date:** 2026-08-28 (Asia/Jakarta / UTC+7)  
**Repository:** `/home/hermes/project-theia`  
**Runtime DB audited:** `/home/hermes/.hermes/theia/theia.db`  
**Purpose:** reconcile the documented phase plan with the deployed system, explain drift, and define the exact next work.

> This audit separates three things that were previously mixed together: **intended design**, **operational state**, and **promotion evidence**. A system can be operational without having passed the gate for the next phase.

## 1. Executive conclusion

### Where we are

The actual system is currently in:

> **Phase 5 operational — forward paper trade and monitoring — not promoted.**

The system is not still only in Phase 1, and Phase 5 is not complete. The deployed no-agent wallet pipeline has already created and closed paper trades, but the evidence is not yet clean or large enough to promote the strategy.

### What is working

- GMGN-first wallet discovery is running.
- Qualified-wallet tracking and signal capture are running.
- The pipeline opens paper trades from passing signals.
- The monitor applies deterministic exit rules and archives outcomes.
- The DB has real forward paper-trade records.
- The process is paper-only; no signing keys or real transactions are involved.

### What is not yet proven

- The strategy edge is not proven out-of-sample.
- The current archive rows are not fully reconstructable.
- The entry-price provenance is incomplete.
- The runtime/dashboard/docs have drifted from one another.
- The original Phase 3/4 gate path is not the same path as the active v3 wallet pipeline.

## 2. Goal and phase gates

The project goal is **not** merely to run a bot or maximize win rate. The goal is to determine whether a disciplined, retail-reachable Solana memecoin selection strategy has positive expectancy after latency and costs.

### Success metric

A strategy is promoted only when both conditions hold on a meaningful out-of-sample/forward sample:

```text
expectancy > 0
AND
profit_factor > 1
```

The result must be net of modeled latency, gas, priority fees, slippage, and other applicable costs. Win rate >= 50% is a milestone, not the objective.

### Phase definitions

#### Phase 0 — Foundation and deploy

**Goal:** build the data boundary, deterministic compute layer, storage, deployment path, and basic tests.

**Exit evidence:** MCP/compute infrastructure exists, tests pass, deployment is usable, secrets are protected.

**Current:** ✅ complete.

#### Phase 1 — Knowledge-first

**Goal:** learn Solana mechanics and create a sourced second brain covering accounts, SPL tokens, fees, AMMs/DEXs, pump.fun lifecycle, graduation, and failure modes.

**Exit evidence:** seed questions are answered with sources, notes are promoted according to a clear verification rule, and the knowledge graph spans the required modules.

**Current:** ✅ baseline complete, but knowledge maintenance continues. This is no longer the only active phase because the wallet pipeline was deployed later.

#### Phase 2 — Discovery and screening

**Original goal:** discover pools/tokens, enrich them, screen safety properties, label the corpus, and measure graduated/dead separation without trading.

**Actual v3 role:** GMGN wallet discovery and signal capture are active through the wallet pipeline. Token screening is a **safety veto**, not the edge. The legacy `theia-discover-screen` and `theia-label-corpus` cron jobs remain disabled.

**Current:** ✅ operational through the v3 wallet path; legacy Phase 2 path is parked.

#### Phase 3 — Hypothesis and backtest

**Goal:** define a falsifiable rule specification and evaluate it on stored, point-in-time history using deterministic computation and modeled costs.

**Current evidence:** the DB contains five backtest rows. The active wallet-cluster row reports `n=16`, expectancy `+0.015 SOL/trade`, PF `1.57`, win rate `62.5%`; this is explicitly an in-sample/reference result and is not a promotion decision. Other historical rows belong to different/older smart-wallet-follow variants, including a dead-end hypothesis.

**Current:** ⚠️ validation in progress. The active hypothesis has not passed a clean, fresh, out-of-sample promotion gate.

#### Phase 4 — Harness and guardrails

**Goal:** ensure consequential actions have grounding, policy decisions, budget accounting, and auditability.

**Actual state:** deterministic guardrails in the no-agent pipeline are active: entry timing, liquidity gate, price-cap gate, deduplication, exposure cap, and deterministic exits. The original LLM-oriented harness path is not active in the wallet loop.

**Current:** ⚠️ partial. Pipeline guardrails are live; `llm_shots`, `context_windows`, and `budget_ledger` are currently empty in the audited runtime DB.

#### Phase 5 — Forward paper trade and monitor

**Goal:** run paper entries from live signals, monitor positions, apply exits, archive every result, and accumulate clean forward evidence.

**Current:** 🟢 operational, not promoted. Active jobs are the wallet pipeline and wallet monitor. The runtime DB contains 11 paper trades and 11 archive rows. There are no open positions at audit time.

**Promotion gate:** the current sample is only 11 trades and every archive row is marked non-reconstructable, so Phase 5 is not complete as an evidence gate.

#### Phase 6 — Scale via delegation

**Goal:** add subagents only when serial throughput is demonstrably the bottleneck.

**Current:** ⏸ not started and should remain off.

## 3. Actual runtime architecture

```text
GMGN leaderboard discovery
        ↓
wallet_profiles / wallet_scan_history
        ↓
qualified wallets (is_smart_money=1)
        ↓
wallet_swaps / new wallet buys
        ↓
wallet_signals
        ↓
pool lookup + liquidity / price-cap screening
        ↓
paper_trades + trade_fills   (entry reserves snapshot from DexScreener/Gecko)
        ↓
OHLCV or spot monitor        (exit reserves snapshot best-effort)
        ↓
exit_engine
        ↓
archives + realized PnL
```

**OHLCV data sources (2026-08-28 upgrade):** three-tier fallback in `wallet_common.ohlcv_for()`:
1. **Birdeye** (`token_ohlcv`) — primary for actively-traded tokens (USD quote, 1000 candles/req, flat-candle filter rejects dead tokens);
2. **GeckoTerminal** (`pool_ohlcv`) — fallback for micro-caps / quiet pools (token quote);
3. **Dexscreener bars** (`dex_bars` MCP tool, new) — last resort for live windows only; frontend binary endpoint (`io.dexscreener.com/dex/chart/amm/v3/...`) with `res>=15` returning full history from pool creation (CF-bypassed via urllib, curl_cffi fallback). 1m history is limited (~100 bars); 15m+ is full-from-launch.

### Active cron jobs at audit time

| Job | Schedule | Mode | Role |
|---|---:|---|---|
| `theia-wallet-pipeline` | every 5 min | no-agent | capture buys, screen, open paper trades |
| `theia-wallet-monitor` | every 5 min | no-agent | monitor and close/archive paper positions |
| `theia-wallet-discovery` | hourly | no-agent | scrape/filter GMGN leaderboard wallets |
| `theia-source2-discovery` | every 6h | no-agent | trending→top_traders→GMGN-7d-gate wallet discovery (source 2) |
| `theia-pipeline-health` | every 5 min | no-agent | read-only freshness watchdog |

Present but disabled: `theia-wallet-report`, legacy `theia-discover-screen`, `theia-label-corpus`, `theia-backtest`, `theia-learn`, `theia-evaluate`, `theia-task-runner`, legacy `theia-monitor`, and heartbeat.

### Source-2 discovery (2026-08-29)

Additive wallet-discovery source, separate from the GMGN leaderboard. Pipeline:
1. `trending_pools` (Dexscreener) — h24>=50 & h6>=50, liq>=30k, mcap<50M, SOL/USDC quote
2. `top_traders` (Birdeye 24h, limit 10) — pre-filter: no bundler/dev/sniper/bot tags, realizedPnl>0, trade>=5
3. **GMGN 7d gate (mandatory)** — `realized_profit_7d > 0` AND `buy_30d+sell_30d < 5000`, plus persistent `dex_trending_blacklist` for wallets tagged bundler/dev on ANY token
4. Upsert `wallet_profiles` (is_smart_money=1, source='dex_trending') + `wallet_scan_history`

Rationale (validated): top_traders alone is misleading — churn bots win on 1 pump but bleed fees
(7DyzpBs -$5.1k/7d, 6XPyYm -$9.2k/7d passed top_traders but failed GMGN 7d). The GMGN gate
separates real smart money (DgPFb2 +$21.4k, 13VK7Zr +$31.4k). Requires the webscraper venv
(scrapling for GMGN CF-bypass). Scraper: `cron/discover_source2.py`, `cron/gmgn_wallet_stats.py`.

## 4. Audited runtime database

Database table counts at audit time:

| Table | Rows | Meaning |
|---|---:|---|
| `archives` | 11 | closed/archive records |
| `backtests` | 5 | stored backtest results |
| `paper_trades` | 11 | paper trade lifecycle rows |
| `trade_fills` | 14 | entry/exit fill rows |
| `wallet_signals` | 29 | detected wallet buy signals |
| `wallet_profiles` | 309 | wallet profiles |
| `wallet_scan_history` | 5066 | append-only GMGN scan history |
| `wallet_trades` | 561 | wallet swap/trade history |
| `screens` | 86 | screening records |
| `tokens` | 86 | token registry |
| `pools` | 86 | pool registry |
| `token_corpus` | 86 | labeled token corpus |
| `price_snapshots` | 14532 | OHLCV snapshots |
| `price_snapshots_v2` | 0 | newer mint-level snapshot schema; empty |
| `llm_shots` | 0 | LLM audit shots; empty |
| `context_windows` | 0 | LLM context state; empty |
| `budget_ledger` | 0 | budget accounting; empty |
| `tasks` | 0 | persistent task queue; empty |
| `wallet_clusters` | 0 | wallet clusters; empty |

### Paper-trade states

```text
archived: 6
closed:   5
open:     0
```

This is a lifecycle inconsistency: all 11 trades have archive rows, but only six are marked `archived` and five remain `closed`. The archival primitive is designed to set state to `archived`, so the five `closed` rows need reconciliation/audit before the ledger can be treated as canonical.

### Archive result

- Rows: `11`
- Sum of stored realized PnL: `+0.626241 SOL`
- Average stored PnL: `+0.056931 SOL/trade`
- Positive rows: `5`
- Gross positive: `+1.328356 SOL`
- Gross non-positive: `-0.702114 SOL`
- Naive stored PF: `1.892`

The naive result is **not a promotion result** because the rows are not reconstructable and the sample is small.

### Archive integrity

All 11 rows have `reconstructable=0`:

| Integrity marker | Rows |
|---|---:|
| `entry price invalid: sol_usd=0.0095 bug` | 2 |
| `missing_reserve_snapshot` | 6 |
| `missing_trade_fills` | 3 |

The `voided_invalid_sol_usd` rows are correctly retained as audit records, but they must not be treated as normal strategy wins/losses.

The six `missing_reserve_snapshot` rows are not necessarily numerically unusable for a conservative spot-based paper result, but they are not fully AMM-reconstructable. The three `missing_trade_fills` rows have a more serious lineage problem and need separate treatment.

**2026-08-28 fix (new fills):** `resolve_pool()` now snapshots `reserves_base`/`reserves_quote` (DexScreener `liquidity.base/quote`, or Gecko `reserve_in_usd` constant-product backout), and `wallet_monitor_v3.py` writes best-effort exit reserves. Verified end-to-end: entry+exit fills with reserves → archive `reconstructable=1`, `integrity_error=None`. All 8 existing entry fills predate the fix (`reserves=None`); new trades are reconstructable. Historical rows remain immutable by design.

### Signal outcomes

Current signal actions:

- `paper_traded`: 6
- `pending`: 2
- `skip_low_liq`: 3
- `skip_wallet_cap`: 13
- `skipped_duplicate`: 5

This shows that the signal table includes not only entries but also duplicates, wallet-cap skips, low-liquidity skips, and pending signals. That is useful, but the dashboard must distinguish **signal**, **candidate**, **entry**, **blocked**, and **closed trade** instead of counting them as the same thing.

## 5. Main drift sources

### Drift A — documentation phase plan vs deployed wallet pipeline

The original documents describe a strict sequence where Phase 1 is current and Phase 5 is parked. Later work deployed a separate no-agent v3 wallet pipeline and enabled its cron jobs. The phase list was updated in `CLAUDE.md`, but `ARCHITECTURE.md`, `README.md`, dashboard static copy, and runtime state were not updated as one atomic change.

**Result:** different files truthfully describe different historical moments.

**Fix:** maintain a single operational status section and explicitly separate legacy phase gates from the active v3 lane.

### Drift B — duplicate strategy lanes

There are two conceptual systems:

1. legacy phase-gated discovery/screen/backtest/paper-trade skills;
2. active v3 no-agent wallet pipeline.

The active lane bypasses some original L3/L4 gates. This is not automatically wrong, but it must be explicit. Otherwise “Phase 5 locked” in the dashboard conflicts with real paper trades in the DB.

### Drift C — price provenance is incomplete

Wallet swap data carries an execution price (`exec_price`) in native quote units. The pipeline keeps it transiently for the price-cap test, but paper entry uses the current pool `price_usd` converted by `sol_usd`:

```text
entry_price_sol = pool_price_usd / sol_usd
```

`resolve_pool()` currently returns `price_usd` and does not return/use a native `priceNative` field. Therefore the system does not have one canonical price representation with source and timestamp.

This is conceptually correct for a delayed paper fill — entry should use market price at simulated entry, not the wallet’s historical execution price — but it is poorly documented and incompletely stored.

### Drift D — hardcoded SOL/USD in monitor fallback

The monitor fallback currently contains:

```python
spot_sol = info["price_usd"] / 150.0
```

That does not use the shared validated `sol_usd()` resolver. It can create an inconsistent exit price whenever SOL/USD differs from 150. This is a real implementation defect and must be removed or explicitly marked as invalid fallback.

### Drift E — incomplete reserve snapshots are intentionally degraded, but not operationally surfaced

`compute/paper_ledger.py` deliberately does not fabricate reserves. It marks an archive as `missing_reserve_snapshot`. That is good integrity behavior, but the current active pipeline still archives many such records, so the promotion report must exclude or separately classify them.

**2026-08-28 status:** reserves are now captured at fill time for new trades (entry + best-effort exit). The remaining exposure is the **backlog** — the 11 historical rows stay non-reconstructable.

### Drift F — weak entry traceability

`paper_trades.opened_by` stores wallet, liquidity, gas, and slippage, while `wallet_signals` stores signal metadata and `screens` stores safety results. The schema does not provide a direct signal ID/screen ID/price-snapshot ID on the trade row. Joins rely on mint/time or JSON contents, which is fragile.

### Drift G — runtime/repository synchronization risk

The repository contains many uncommitted changes and newly added dashboard/API files at audit time. Runtime scripts are copied/deployed separately. A repo file being fixed does not prove the runtime wrapper is using that exact version. Hash checking and deploy verification must be part of every operational change.

## 6. What must be focused on now

### Priority 0 — freeze interpretation of historical results

Do not promote, optimize, or compare the strategy using the current naive aggregate as if it were clean evidence.

Keep every historical record. Do not delete the two invalid records. Label them and exclude them from the primary strategy metric until the inclusion rule is documented.

### Priority 1 — fix price handling for new trades

1. Inspect the actual `wallet_swaps` response contract and record native execution price explicitly as `signal_exec_price_sol` when quote mint is WSOL.
2. Extend pool resolution to return, when available:
   - `price_native`;
   - `price_usd`;
   - quote mint/symbol;
   - source;
   - source timestamp;
   - pool address.
3. Use `price_native` directly only when the pair quote is WSOL/SOL. Otherwise use USD conversion through a validated SOL/USD value.
4. Replace monitor fallback `/ 150.0` with the validated resolver, or refuse to close when no trustworthy native conversion exists.
5. Persist price provenance in the entry/exit fill snapshot.

### Priority 2 — reconcile and classify the old ledger

Produce a deterministic audit report with one row per trade:

- trade ID and mint;
- signal timestamp;
- detected timestamp and latency;
- entry timestamp;
- signal execution price;
- simulated entry price and source;
- SOL/USD source/value;
- entry fill quantity;
- exit fills and quantity sum;
- exit reason;
- gas/slippage;
- reserve availability;
- archive state;
- inclusion class: `valid`, `degraded`, `voided`, or `unrecoverable`.

Do not mutate historical values without a migration record.

### Priority 3 — make Positions read the real ledger

The dashboard must stop showing “Phase 5 locked” while the active pipeline is running. Positions should read real paper-trade/archive data and distinguish:

- pending signal;
- parked/blocked signal;
- open position;
- closed but not archived;
- archived and reconstructable;
- archived but degraded;
- voided.

Entry rationale must link wallet signal, wallet qualification, screen result, hypothesis, price source, and costs.

### Priority 4 — make the promotion metric deterministic

Create one canonical report that explicitly defines:

- which rows are included;
- how voided rows are excluded;
- how degraded rows are reported;
- whether PnL is gross or net;
- how fees/slippage are handled;
- how partial exits are aggregated;
- how PF handles zero gross loss;
- minimum sample and confidence reporting.

Target remains **expectancy > 0 and PF > 1**, not win rate.

### Priority 5 — update all status surfaces together

Synchronize these surfaces in one change:

- `CLAUDE.md`;
- `README.md`;
- `ARCHITECTURE.md`;
- dashboard copy and Positions view;
- cron source config;
- runtime deployed scripts;
- any vault status note.

Every surface should say: **Phase 5 operational, not promoted; Phase 3 validation and Phase 4 hardening remain incomplete; Phase 6 is off.**

## 7. Recommended phase promotion contract

### To mark Phase 5 “promoted”

All must be true:

- at least 50 forward trades, or a separately approved sample-size rule;
- valid/degraded/voided inclusion policy documented;
- no unresolved price-unit ambiguity in new fills;
- all new entries have signal and price provenance;
- all new exits have fill lineage and cost snapshot;
- archive state is consistent;
- deterministic report computes net expectancy and PF;
- results remain positive on the agreed out-of-sample/forward window;
- no open operational incidents affecting measurement.

### To move toward Phase 6

Only after Phase 5 promotion:

- prove serial throughput is the actual bottleneck;
- define the delegated task boundary;
- register only the required profile(s);
- preserve the same DB, compute, budget, and audit invariants.

## 8. Immediate worklist

1. **Do not delete data.** Add classification/reporting first. *(kept — voided rows retained)*
2. Fix `/150.0` monitor fallback. *(still open)*
3. Add native price/provenance fields for new fills. *(still open)*
4. Reconcile five `closed` rows that already have archive rows. *(still open)*
5. Investigate three `missing_trade_fills` rows. *(still open)*
6. Separate the two `voided_invalid_sol_usd` rows from strategy metrics. *(still open)*
7. Decide how six `missing_reserve_snapshot` rows are reported. *(partially addressed 2026-08-28 — new fills are reconstructable; decision on backlog rows still open)*
8. Build the real Positions data view. *(still open)*
9. Run a clean forward sample to at least 50 trades. *(in progress — forward corpus growing: 14,532 price_snapshots)*
10. Recalculate promotion metrics deterministically and document the decision. *(still open)*

### Completed 2026-08-28 (operational changes this audit)

- **Reserve snapshots at fill time** — `resolve_pool()` (`wallet_common.py`) returns `reserves_base`/`reserves_quote` (DexScreener `liquidity.base/quote`, or Gecko `reserve_in_usd` constant-product backout); `wallet_monitor_v3.py` writes best-effort exit reserves. Verified: rebuild test → `reconstructable=1`; 8/8 paper_ledger tests pass.
- **OHLCV three-tier fallback** — `ohlcv_for()` = Birdeye → Gecko → Dexscreener bars. New `dex_bars` MCP tool in `theia-dexdata` (binary dexscreener endpoint decoder; urllib primary, curl_cffi fallback; cache 120s, no empty-cache).
- **`MAX_OPEN_PER_WALLET` 3→5** — pipeline v3/v4 + repo. Rationale: 9 wallet-cap skips on a firing wallet that closed 3 profitable trades the same window (+0.70 SOL, avg +47% ROI). Revisit if single-wallet concentration becomes a risk.
- **Coverage audit re-run** (`coverage_audit.py` → `coverage_audit_live.json`): `price_snapshots` 14,532 (was 1,088 at M-06); `tokens_with_all_required` still 0 — bottleneck is `forward_ohlcv_ge_60` (1 mint). Reserves in `pools` table still 4 (backfill scope, distinct from fill-time snapshots).

## 9. Verification performed

- Source files and project docs inspected.
- Runtime cron configuration inspected.
- Runtime SQLite schema and row counts inspected in read-only mode.
- Python compilation completed successfully with `python3 -m compileall -q compute cron mcp`.
- **2026-08-28:** `uv run --with pytest` → 8/8 `compute/tests/test_paper_ledger.py` pass (incl. the no-fabricate degradation test). `dex_bars` MCP tool live-tested: res=15 → 152 bars full-from-launch; cross-validated against GeckoTerminal prices. `coverage_audit.py` re-run deterministically against live theia.db.
- The bare `python3` environment does not have `pytest` installed; full-suite runs use `uv run --with pytest` (no global install required). A full-project pytest pass beyond the paper_ledger module was **not** claimed by this audit.
- Repository had substantial pre-existing/uncommitted changes at audit time; they were not modified by this audit.

## Bottom line

Theia is a **live forward paper-validation system**, not a finished profitable strategy and not a Phase 6 system.

The most important work is not adding more strategy ideas. It is making every paper trade answer, from stored data:

> **What signal triggered it, what price was used, what unit/source produced that price, why did it pass, what costs were modeled, how did it exit, and can the result be reconstructed?**

Until that answer is reliable and the forward sample passes the promotion gate, the correct state remains:

> **Phase 5 operational — validation in progress — not promoted.**

**2026-08-28 close-out:** the reconstructability gap is now closed for *new* trades (fill-time reserve snapshots + verified `reconstructable=1`), and OHLCV coverage gained a third source. The remaining blockers are the historical backlog (11 non-reconstructable rows), `forward_ohlcv_ge_60` coverage (1 mint), and a clean forward sample of ≥50 trades.
