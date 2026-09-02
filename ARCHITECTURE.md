# PROJECT THEIA — Architecture (v2, Hermes-driven)

> **Why v2.** The v1 design (old `design/*.md`) was built entirely on a *copy-trade*
> thesis: follow smart-money wallet buys. We tested that thesis first with a throwaway
> replay harness and it **failed** — no edge net of VPS latency + fees; the edge, if any,
> lives in the first seconds we can't reach. Details preserved in agent memory
> (`theia-replay-verdict`). v2 keeps the good *bones* (layered Hermes architecture, the
> non-negotiable principles, the free-tier data plumbing) and throws out the copy-trade
> strategy.

---

## CURRENT STATE — verified live 2026-09-01 (supersedes the 08-09 audit below)

> Every number in this section was pulled from the live DB / cron logs / API probes on
> 2026-09-01 (WIB). The **Build reality (2026-08-09)** section below is kept as historical
> audit context; where they disagree, this section wins.

### Phase scoreboard (verified, not aspirational)

| Phase | State | Evidence (2026-09-01) |
|---|---|---|
| P0 Foundation | ✅ DONE | L1 probes live, L2 `pytest compute/tests/` = **67 passed** (3.9s) |
| P1 Knowledge | ✅ baseline + ongoing | Obsidian vault live; nightly auto-digest running |
| P2 Discovery + screening | 🟢 OPERATIONAL | GMGN-first v2: 9 sorts → 250 unique wallets/run, gate pass=8 fail=242, **17 tracked wallets**; source-2 (Dexscreener trending) live every 3h; 30,421 scan rows over **403 distinct wallets** in `wallet_scan_history` |
| P3 Hypothesis + backtest | ⚠️ VALIDATION | `hyp_wallet_cluster_latency` in-sample n=16 PF 1.57; OOS gate NOT passed; all organic-only rule batteries blocked by day-concentration guard (research-runner: "no rule crossed the hardened gate") |
| P4 Harness + guardrails | 🟡 NO-AGENT GUARDRAILS ACTIVE | LLM harness still unwired (`llm_shots`=0, `budget_ledger`=0, `tasks`=0); the *pipeline's* deterministic guards (liq>$5k, price cap, dedup, exposure cap, entry-window) are the live authority |
| P5 Forward paper trade | 🟢 OPERATIONAL, NOT PROMOTED | 13 trades / 13 archives / 0 open; see ledger stats below |
| P6 Delegation | 🔴 NOT STARTED | unchanged |

### Live cron (all no-agent, 0 LLM tokens) — all completing, health watchdog green

| Job | Cadence | Last completed (WIB 09-01) |
|---|---|---|
| theia-wallet-pipeline (v4) | 5 min | 20:40 — "0 new signals from 17 wallets" |
| theia-wallet-monitor (v3) | 5 min | 20:40 — "no open positions" |
| theia-wallet-discovery (GMGN v2) | 1 h | 20:00 — pass=8/250, tracked=17 |
| theia-source2-discovery | 3 h | 18:00 — 40 pools → 6 pass prefilter, OHLCV corpus +~1,400 rows |
| theia-pipeline-health | 5 min | 20:40 — **all checks OK** |
| theia-research-runner | 12 h | 12:00 — no gate HIT (concentration guard held) |
| theia-wallet-report + 7 legacy jobs | — | disabled |

### Forward paper ledger — computed from `archives` (11 valid of 13; 2 voided `invalid_sol_usd`)

```
n=11  total=+1.6187 SOL  expectancy=+0.1472  PF=3.288  win_rate=54.5%
exit mix: time_stop=6  hard_stop=4  tp_4x=1
⚠ top single win (+0.998, tp_4x) = 43% of gross profit — concentration risk, same
  single-wallet-artifact pattern that killed smart-wallet-follow. NOT promotable.
reconstructable=2/13 (reserves captured at fill only since the 08-28 fix; 11 legacy=0)
```

**Promotion verdict: NOT PASSED.** Sample still tiny, profit concentrated in one trade,
and every organic-only rule battery (dip_reversal n=9319, volume_lowbuy n=2008 — both
exp>0/PF>1 headline) fails the **day-concentration guard** (positive days are a minority
of active days). The 240m time-stop "improvement" was proven a recent-day artifact
(2026-09-01 exit-tuning verdict). Gate-v2 whale cohort (B2) is the current forward proof
target: ≥2 weeks paper before any promotion call.

### Research board (post 08-31/09-01 batteries)

- A1 exit tuning — done, no edge (240m = day-concentration artifact; live 60m kept)
- B1 holdings-gate — veto-plausible: whale-exited cohort PF 0.225 (n=11 losers cluster);
  entry signal unproven (n=1). Candidate: deploy as VETO in whale pipeline, never as trigger
- B2 gate-v2 whale cohort forward — RUNNING (the live proof target)
- B3 operator-hub veto — designed, untested (whales trace to 2-node funder hub HF3s↔F1ZL)
- C2 early-holders — PARKED: snapshot depth degenerate (top10_share≈1.0), 0 corpus overlap,
  survivor bias. Needs holder-API budget before retry
- C1/C3/C4 — waiting on data maturity

### Layer health (probed live 2026-09-01)

- **L1 data:** Helius `getHealth` ok with real key (4-key rotation); Birdeye 200 with real
  key; Dexscreener + GeckoTerminal 200 keyless; GMGN 403 direct (CF — browser-tier scrape
  working via discovery, 250 wallets/run); **GoPlus endpoint currently connection-times-out
  from the VPS** — impact contained because v4 screening is liq/price only (last GoPlus
  screens row 2026-08-22); Obsidian vault dir OK; `theia-chainrpc.health` = ok
- **L2 compute:** 67/67 tests pass. Money math still 100% via libs (all numbers above from
  `expectancy.py`-style deterministic computation over DB rows)
- **L3 skills:** `theia-current-state` patched 08-28; 8 design-era skills stale (documented
  gap list there); no new drift found 09-01
- **L4 orchestration:** 6 no-agent jobs healthy; LLM-harness path still unwired by design
  (P4 partial); orchestrator model is now `z-ai/glm-5.2` via jembatan.ai (config changed
  from the `deepseek-v4-*` era; subagent table below is historical)

### Known drift (as of 09-01)

- Runtime scripts ahead of repo persists (v4/v3 only in `~/.hermes/profiles/theia/scripts/`)
- 11 uncommitted dashboard changes (Market Data view, lightweight-charts v5 work)
- `price_snapshots_v2` table exists but empty (0 rows) — v1 table has 55,246 rows
- Gateway runs under systemd user service; a reboot kills all cron until gateway restart
  (documented restart procedure in agent memory)

### Design critique — data-quality gates (user discussion 2026-09-01, open items)

User thesis: the repeated "no edge" verdicts are partly a **data-quality artifact**, not
proof of no edge. Three concrete gaps identified and accepted as open work:

1. **Timing window unproven for the current cohort.** T+25–35m entry was tuned on the OLD
   cohort (wr7≥0.6 scalpers) whose T+1–5m edge died <30m. Gate-v2 whales (txs7≥500,
   rPnl7d≥$10k) have a different profile; the optimal entry delay may be shorter. Open
   item: backtest a T+{5,10,15,25,35}m entry grid on `wallet_signals` + `price_snapshots`
   per-mint history — the data exists.
2. **Backtest inputs skew to "already falling" charts.** Entry signals observed late
   (post-25m) are disproportionately post-spike/pullback shapes, and retro-fetched OHLCV
   contaminates tails (proven 08-31/09-01 artifacts). Verdicts computed on this data are
   biased toward "no edge". Fix direction: forward-only tape recording (next item) +
   organic-only provenance guard (already enforced in research_runner).
3. **Token "fame"/liveness is unmeasured.** Currently the pipeline records 1m OHLCV only
   for mints that produced a screened signal (event-driven, not lifecycle). DexScreener's
   free pool attributes expose richer LIVE popularity signals per pool: buys/sells/buyers/
   sellers over m5/m15/m30/h1/h6/h24 windows + volume_usd per window — a direct
   "is this token still crowded" measure that costs one keyless API call. Open item:
   record these per-signal (token_activity_snapshots table) and use as entry/exit context
   (buyer count trend, buy/sell imbalance, volume z-score across windows).

### Tape-recorder redesign — full-window ingress/egress cycle (user discussion 2026-09-02, open item)

**Current coverage gap (measured 2026-09-02):** of 142 pools in `price_snapshots`, only
77 have ~full 1m coverage (≥95% of expected candles); 100 pools have <500 candles;
median candle count per pool is **8** (minutes, not lifecycle). 131/142 pools have no
new candle for >24h — recorded once at signal time, never revisited. The corpus is a
collection of snapshots, not price histories.

**Design: token lifecycle recorder (`token_lifecycle_recorder.py`, planned no-agent cron
every 15 min) — a closed ingress/egress cycle, not an append-only pile:**

```
  INGRESS                          HEALTH CHECK (per tick)          EGRESS
  ─────────                        ──────────────────────           ──────
  whale-signal mints        ──►   1 call DexScreener/pool:   ──►  DEAD → tokens.status='dead',
  source-2 trending mints         liq_usd, vol24, txns24           death_reason set, STOP
  (all mints, not just            + last candle age from           fetching (stored candles
   screen-passers)                price_snapshots                  kept as backtest fodder)
                                  ──► ALIVE → full-window
                                      backfill (dex_bars res=15,
                                      incremental via cache)
```

- **Health/dead thresholds (initial, tunable):** liq_usd < 5k, vol24 < 1k, txns24 < 20,
  or last candle > 24h old → dead. Dead tokens exit the fetch cycle; their stored
  OHLCV remains queryable for backtests.
- **Full-window mandate:** record from pool creation (dex_bars res=15 returns full
  history from launch), not from first signal. All rows carry provenance (organic
  forward-record vs retro-fetch) so backtests can exclude contaminated tails.
- **Rate/budget:** ~150 DexScreener calls/run at ~50 live pools (2–3 calls per pool for
  500-bar batches), keyless, through the existing `wallet_common` token-bucket + disk
  cache. Well within free tier.
- **Why:** closes data-quality critique items #2 and #3 — backtests get honest
  lifecycle histories (including the tokens that died instantly, which the current
  event-driven capture misses → survivor-bias fix), and fame/liveness metrics
  (buy/sell imbalance, buyer-count trend) become computable per token over its full life.

**Verified supporting facts (2026-09-02):** DexScreener free pool payload carries
liq_usd, volume_usd.h24, txns24 {buys, sells} per token in one keyless call (live probe
on MukLDtJ8Cx9: liq $325k, vol24 $7.8M, txns24 275k buys / 26.9k sells). Helius free
tier additionally verified: webhook CRUD works (api.helius.xyz, `webhookType=enhanced`,
≥3 hooks), `/v0/transactions` parse + getProgramAccounts allowed, 30 rapid RPC calls
without 429 — enabling a seconds-latency detection path later (test receiver + tunnel
round-trip verified 200 OK; a real SWAP delivery was not observed in the test window
because the tracked whale did not trade — test webhook cleaned up after).

**Postmortem raw-data re-audit (2026-09-02):** the 08-17 smart-wallet-follow postmortem's
own inputs were audited (see vault note caveat for full numbers). Findings: swap tape
strong (2,979 txs / 196 days — strategic verdict stands), but pre-entry OHLCV context is
shallow (median 4h lookback) and **only 197 of 630 whale-traded mints (31%) ever had
OHLCV fetched** → tactical entry-rule verdicts (dip-buy dead, T+1m worst) are NOT settled
and must be re-derived from the full-window lifecycle tape once this recorder is live.
The timing-grid retest (open item #1 above) inherits this: it is a re-test of tainted
verdicts, not a confirmation of them.

### Bias inventory — full impact map (user discussion 2026-09-02, reference for all future verdicts)

Six identified biases, with DIRECTION of distortion (not uniform — some push pessimistic,
some optimistic, so per-verdict audit is mandatory, no single-direction correction):

| # | Bias | Evidence | Distortion direction |
|---|---|---|---|
| 1 | Survivor bias in universe (only 197/630 whale-traded mints had OHLCV fetched) | postmortem re-audit | Measured expectancy OVERSTATED → "no edge" verdicts likely still too optimistic; strategy possibly worse than measured |
| 2 | Shallow pre-entry context (median 4h candles before whale buy) | postmortem re-audit | Entry-rule verdicts invalid where they depend on pre-buy chart shape (dip-buy dead, T+1m worst, timing optimum) |
| 3 | Event-driven recording (only screen-passing mints, only from T+35m detection) | coverage audit: median 8 candles/pool, 131/142 pools dead >24h | Corpus over-represents post-spike/falling charts → backtests skewed toward "no edge" |
| 4 | Retro-fetch contamination (`_now` cache keys + adjacent fetch days dominating tails) | proven twice: 08-31 GATE_HIT, 09-01 exit-240m artifacts | False POSITIVES → risk of promoting bad rules; day-concentration guard is a patch, not a system |
| 5 | Day-concentration / regime bias | top forward win = 43% of gross profit; 240m gain only on 08-30/31 | Aggregate exp>0 can be single-day regime, not mechanical edge |
| 6 | GMGN as trust-provider data (not reconstructable) | Gate V2 fit to provider stats | If GMGN's wash-filtering leaks, our gate inherits the leak; thresholds (rPnl≥10k, txs≥500) fitted to possibly-biased provider numbers |

**Impact on decisions currently LIVE:**

| Active decision | Data source | Status |
|---|---|---|
| Gate V2 thresholds (rPnl≥10k, txs≥500, vol≥100k) | OOS persistence test n=269 | ⚠️ fitted within a biased ecosystem — parameters may be overfit to bias |
| 17 tracked wallets | Gate V2 output | ⚠️ inherits #1 |
| Entry timing T+25–35m | postmortem backtest (shallow pre-entry) | 🔴 UNSETTLED — optimal timing likely different |
| liq>$5k veto, price cap 1.5×, MAX_OPEN_PER_WALLET 5 | postmortem v2–v5 | ⚠️ liq veto safe (consistent direction); price cap not re-verified |
| exit time-stop 60m | M-04 | ⚠️ organic-only but day-concentration not audited as strictly as 09-01 battery |
| B2 forward cohort (≥2 weeks) | paper fills — correct organic data | ✅ the ONLY clean decision path live — sample still small |

**Net effects:** (a) false rejection is real — "no edge" verdicts were computed on flawed
data and must not be treated as law; (b) false acceptance nearly happened (08-31 GATE_HIT
would have promoted an artifact — caught only by the guard); (c) distortion directions
differ per bias, so every tactical verdict needs individual audit; (d) the two truth
anchors are the on-chain swap tape (structural findings: wallet decomposition, latency
discriminator) and forward paper fills (B2). **Standing rule until the lifecycle
recorder produces a full-window tape: keep accumulating forward sample; change nothing
based on legacy verdicts; re-derive tactical rules only from clean tape.**

### Storage decision record — SQLite now, TimescaleDB later (2026-09-02)

User question: migrate `theia.db` from SQLite to TimescaleDB/PostgreSQL?

**Decision: stay on SQLite for now; migrate to TimescaleDB (not vanilla Postgres) when a
measured trigger fires. Design new tables migration-friendly from day one.**

Measured facts (2026-09-02): `theia.db` = 22 MB; `price_snapshots` = 61k rows;
`wallet_scan_history` = 34k rows; the 3.3 GB under `~/.hermes/theia/` is API disk cache
(2.1 GB) + MCP venvs (1.2 GB), NOT the database. VPS headroom: 8 cores, 31 GB RAM,
45 GB free disk. Single-writer access pattern (pipeline/monitor/recorder via flock).
SQLite is comfortable at this scale by orders of magnitude.

**Migration triggers (any one):**
- `price_snapshots` exceeds **~10M rows** (full-window 1m tape: ~50 live pools ×
  1,440 candles/day ≈ 26M rows/year — reachable within a year of the recorder running)
- Backtests need continuous rollups (1m → 5m/15m/1h via `time_bucket` + continuous
  aggregates) that SQLite would re-scan every run
- Concurrent access contention (recorder + monitor + dashboard + backtest hitting
  the DB simultaneously and locking)

**Why TimescaleDB and not vanilla Postgres when triggered:** hypertables auto-partition
by time, `time_bucket` is native, continuous aggregates compute rollups incrementally —
exactly the OHLCV access pattern. Vanilla PG gives the rewrite cost without the
time-series payoff.

**Migration cost when triggered:** SQL dialect changes across ~6 live scripts
(`INSERT OR IGNORE` → `ON CONFLICT DO NOTHING`, `PRAGMA`, inline `MIN()`); `theia-store`
MCP rewrite (the single-writer boundary); one more service to run/backup on the VPS.
Mitigation: introduce a single `db.py` access module first so the 6 scripts swap an
import, not their SQL one by one. Migration path: per-month dump of `price_snapshots`
→ `\copy` → `create_hypertable`. Hermes-internal DBs (`state.db`, cron DBs) stay SQLite
— this decision covers Theia's own data only.

**Explicit scope note:** storage migration does NOT address the bias inventory above —
that is a what-we-record problem, not a where-we-store problem. Priority order is
unchanged: lifecycle recorder first (with PG-ready schema: `(pool_addr, ts)` PK +
provenance column), storage migration later if/when triggers fire.

---

## Build reality & sequencing — HISTORICAL AUDIT (2026-08-09)

> **This section is the ground truth; everything below it is *intended design*.** The audit
> found a healthy skeleton with unwired seams: every layer's components exist and pass their
> own unit tests, but the arrows *between* layers mostly don't, and the core edge has never
> been tested. Read this before trusting any capability claim further down.

### Status by layer

- **L1 — MCP servers (data): ✅ built & working.** 8 servers, 28/29 tools respond.
- **L2 — Compute libs (math): ✅ built.** 19 deterministic libs with real logic; 33 unit
  tests pass. (2 benign placeholders: `harness.py` model-cost, `discovery_filter.py` no-data.)
- **L3 — Skills (playbooks): 🟡 written, seam-blind.** They call real MCP tools, but the
  screening path (`theia-screen-token`, `theia-backtest`) never consults the knowledge base.
- **L4 — Orchestration: 🔴 mostly unwired.** Harness never invoked in prod (`llm_shots`=0),
  budget breaker never tracked (`budget_ledger`=0), task queue never used (`tasks`=0),
  delegation unregistered + stubbed. (Cron token-burn fixed 2026-08-09.)

### The seams are the work — not the boxes

Every box exists; the arrows between them mostly don't. Unwired seams: knowledge→screening
rule · harness→loop · budget→action · task→execution · delegate→subagent · note→decision.
**These seams, not any single component, are the remaining work.** Unit tests (all 33 are
component-level over synthetic data — none cross a seam) measure brick health, not whether
the castle stands. Empty trading tables are the honest tell.

### The one thing NOT proven: the edge

Every trading table (`tokens`→`archives`) is empty; **no backtest has ever run.** Whether
survival-screening yields `expectancy>0` net of costs is **unvalidated** — and it is the
entire justification for this architecture. Per principle #5 (EARNED AUTONOMY), the rest has
**not yet earned its complexity**; building it before validating the edge was the original
design's root mistake.

### Sequencing — validate before you build (the vertical slice)

Build order = the rollout phases (see `CLAUDE.md` → *Rollout phases*). **Phase gate #1 is one
working vertical slice, not "all files present":**

```
discover → screen (real GoPlus signal) → backtest on stored history → an expectancy number
```

Getting that single path to run end-to-end forces the wiring of every seam on it and answers
the edge question. Parked pieces switch on **one phase at a time, only after** their gate.

### Active now vs parked

- **Active (Phase 1 — knowledge-first):** L1 MCP · L2 compute · `theia-learn` · `task_runner`
  (0-LLM infra) · the Obsidian second brain.
- **Parked until their phase:** discovery/screening (P2) · backtest/hypothesis (P3) ·
  harness + budget breaker (P4) · paper-trade + monitor (P5) · subagent delegation (P6).
  Their code/docs existing is **scaffolding — "not yet," not "broken."**

## The new goal

1. **Learn Solana deeply first** — build a *second brain* (Obsidian, hosted on the server,
   synced via Syncthing) of verified knowledge: account model, fees, SPL tokens, DEX/AMM
   mechanics, how tokens & swaps are actually created, pump.fun bonding curve & graduation.
2. **Then find a *mechanical* edge in the memecoin market** — not a speed edge (we lose that),
   but a **selection / screening** edge: most memecoins die to zero, so a filter that avoids
   rugs/honeypots/wash-farms and picks survivable setups raises expectancy *without* needing
   to be fast.
3. **PoC paper trade.** Success metric is **expectancy > 0 AND profit_factor > 1** net of
   latency+fees. **Win-rate ≥ 50% is a milestone, NOT the target** — a high win-rate with a
   bad payoff ratio still loses (proven this session: a 75%-win wallet with profit_factor
   0.03). Every P&L number is deterministic code, never the LLM.

## What Theia (Hermes) "fires" at

```
                        ┌───────────────────────────────────────────────────────┐
                        │           HERMES AGENT  —  profile "THEIA"            │
                        │  LLM role: orchestrate · sequence · judge qualitative │
                        │  native:  cron · subagents · FTS5 memory ·            │
                        │           execute_code · Hermes channels           │
                        └───────────────────────────┬───────────────────────────┘
                                                    │ fires DOWNWARD through Skills only
        ┌───────────────────────────────┬───────────┴───────────────┬───────────────────────────┐
        ▼                               ▼                           ▼                           ▼
  L3 SKILLS · LEARN            L3 SKILLS · RESEARCH          L3 SKILLS · STRATEGY        L3 SKILLS · OPERATE
  learn-topic                 discover-tokens               form-hypothesis             screen-token
  document-mechanic           map-token-lifecycle           backtest-hypothesis         paper-trade
  diagram-mechanic            trace-swap-route              evaluate-expectancy         monitor-position
  link-notes                  sample-launches               refine-strategy             archive-result
        │                               │                           │                           │
        └───────────────┬───────────────┴───────────┬───────────────┴───────────────┬───────────┘
                        ▼                           ▼                               ▼
              L2 COMPUTE (execute_code)     L1 DATA ACCESS (MCP servers)     (the only writer = wallet-store)
              deterministic · logged        the capability / secret /
              NO LLM money math             rate-limit / cache boundary
              ─────────────────────         ────────────────────────────
              expectancy · profit_factor    theia-obsidian   second brain (Syncthing on server)
              wilson · pnl (FIFO)           theia-webscraper curl_cffi (fast) → StealthyFetcher (CF bypass)
              amm-sim · gas-sim             dexdata-mcp    GeckoTerminal + Dexscreener
              exit-engine                   chain-rpc-mcp  Helius: tx history · parse_swaps · gas · sim
              wash-score · rug-score        birdeye-mcp    token lists · top traders · wallet PnL (x-check)
              screen-score                  security-mcp   GoPlus honeypot / mint / LP flags
                                            wallet-store   SQLite/DuckDB — trades · hypotheses · results
                                                    │
                           L0 INFRA:  VPS · SQLite(WAL)/DuckDB · TTL cache · per-source token-bucket · .env secrets
                           TASK QUEUE:  SQLite `tasks` table — polled by task_runner; deps, retry, resume
```


## The loop (learn → hypothesize → test → PoC)

```
  LEARN mechanics ──► DOCUMENT to second brain ──► FORM hypothesis
  (how tokens/swaps/            (Obsidian)              (a testable selection/screening rule)
   launches work)                                             │
        ▲                                                     ▼
        │                                              BACKTEST on stored history
        │                                              (screen first: wash + rug + honeypot)
        │                                                     │
        │                                                     ▼
        │                                              PAPER TRADE  (realistic fill:
        │                                               AMM impact + live gas + latency)
        │                                                     │
        │                                                     ▼
        └──── refine ◄──── EVALUATE  expectancy>0 · profit_factor>1 · (win-rate≥50% = milestone)
                           lessons + verified facts feed back into the second brain
```

## Layer-placement rule (unchanged — memorize)

- **"Talk to an API / DB / chain / the vault"** → an **MCP server** (L1). Secrets, the
  token-bucket rate-limiter, and the TTL cache live *inside* the server.
- **"Do exact math / score a decision"** → an **`execute_code` compute lib** (L2). Pure,
  reproducible, logged. Every P&L / screening number is born here — never the LLM.
- **"Run this N-step procedure the same way each time"** → a **Skill** (L3).
- **"Decide which procedure to run, when, on what, remembering results"** → **Hermes**
  (cron · subagents · memory · policy) (L4).

The agent talks **only downward through Skills**, so every action is a named, auditable
skill invocation.

## Non-negotiable principles (kept from v1 — they still win)

1. **VERIFY, DON'T SPECULATE.** No fact/label/number asserted without corroboration and a
   reconstructable source. Knowledge-base claims cite where they came from.
2. **THE LLM NEVER DOES MONEY MATH.** Cost basis, PnL, expectancy, price impact, gas,
   position size, screening scores → deterministic `execute_code` only.
3. **PAPER ONLY.** No signing keys anywhere. Fills simulated off *live* reserves/gas/fees.
4. **STAY WITHIN FREE BUDGET.** Free-tier public APIs; respect per-source limits, degrade to
   cache, never hammer or risk a ban.
5. **EARNED AUTONOMY.** The agent widens its scope only on audited, out-of-sample results.

## The second brain (Obsidian)

Hosted on the server, synced to the agent via **Syncthing**, reached through `theia-obsidian`.
Knowledge modules (each note = verified facts + `[[wikilinks]]` + diagrams):

```
1. Solana fundamentals   account model · SPL token · PDA · CU & fees · slots/finality
2. DEX & swap mechanics   Raydium CPMM/CLMM · Jupiter routing · pump.fun bonding curve
3. Token lifecycle        creation · launch · mint/freeze authority · LP · graduation
4. Failure modes          rug · honeypot · wash trade · sniper/MEV
5. Strategy hypotheses     each edge idea + how it is tested in the harness + its result
```

## Reality check — the edge must fit our constraints

We have **no institutional advantage**: not capital, not speed/latency, not information.
Free API tier + small (paper) size + one VPS. So we explicitly do **not** chase edges that
need any of those:

```
  ✗ launch sniping / front-running / same-block fills   (speed — we lose)
  ✗ latency arbitrage / MEV                             (speed + infra — we lose)
  ✗ insider / pre-announcement info                     (information — we don't have)
  ✗ market-making at size / moving the book             (capital — we don't have)
```

What **is** reachable for a slow, small, retail agent — "slow edges" that survive because
they don't need speed and sit below institutions' size threshold:

```
  ✓ SURVIVAL SCREENING   most memecoins die to zero; filtering out rug/honeypot/wash/
                         mint-live tokens raises expectancy by avoiding the −100% tail
  ✓ DISCIPLINE           consistent sizing + stops + exit ladder, run 24/7 by a bot with
                         no emotion/FOMO — the edge is in NOT blowing up
  ✓ PATIENCE/SELECTIVITY ignore 99% of tokens; act only on setups that pass strict rules —
                         time is our free resource, speed is not
  ✓ SLOW TIMING          post-graduation (pump.fun→Raydium) plays measured in MINUTES,
                         not milliseconds — a VPS can reach these
  ✓ REGIME               trade only when the memecoin market is hot; sit out the rest
```

Honest caveat: even these may not clear `expectancy>0` — that is exactly what the PoC
tests. Small-cap illiquidity means slippage/exit risk is real even on paper; we measure it,
never assume it away.

## How Theia runs 24/7 (within free limits)

Hermes' built-in **cron** + a **persistent task queue** (in the wallet-store DB, so a
restart resumes) drive a perpetual loop. The key trick: split work into **API-bound** vs
**API-free**, so hitting a rate limit doesn't stop the agent — it switches to work that
needs no API and stays productive.

```
  API-BOUND (rate-limited)                 API-FREE (always runnable, 24/7)
  ────────────────────────                 ────────────────────────────────
  discover tokens (Gecko/Dex)              learn a Solana topic → write sourced note
  screen token (GoPlus + sim)              backtest a hypothesis on STORED history
  fetch live price / reserves              compute expectancy on archived paper trades
  pull wallet/tx history (Helius)          refine + link second-brain notes; plan next

  loop (each Hermes cron tick):
    1. task_runner polls `tasks` table — ready + deps satisfied → execute
    2. check per-source budget (token-bucket)
    3. budget ok      → run next API-bound task from the queue
    4. source >80%    → DEGRADE: serve cache / skip enrichment
    5. budget spent   → do API-FREE work (learn / document / backtest)
    6. persist state + heartbeat to DB   (crash → restart → reconcile → resume)
```

So "running 24/7 selama nggak kena limit" is guaranteed: a limit doesn't halt the agent, it
just shifts it to learning/backtesting until the window resets.

## Task runner — persistent queue with deps, retry, resume

> **Status (updated 2026-08-17): runner runs, queue unused, handlers honest.** The
> `task_runner.py` loop is real and runs 0-LLM (`no_agent` cron). Handlers are now honest:
> `backtest` is a REAL API-free walk-forward backtest on stored history
> (`compute.backtest_engine` → writes `backtests` row + updates hypothesis best_*);
> MCP-bound types (`discover-screen`, `label-corpus`, `wallet-pnl-enrich`) return
> `ok=false` with a clear "run via cron/agent" error instead of fake success; agent-only
> types (`monitor`, `delegate`) are left 'ready' for the agent — never executed here.
> `tasks`=0 still (nothing has ever enqueued a task) — the queue awaits Phase 2.

The `tasks` table is the single source of truth for what Theia (and its subagents) must do.
The runner is pure Python, no LLM. It is what makes parallel delegation, retry, and crash
recovery possible.

```
  ┌─────────────────────────────────────────────────────────────┐
  │  TASK QUEUE (theia-store.tasks)                               │
  ├─────────────────────────────────────────────────────────────┤
  │  state: ready | blocked | running | done | failed            │
  │  deps: JSON array of task IDs that must be 'done' first      │
  │  attempts: 0..3 → retry with exponential backoff             │
  │  budget_cost: API-call budget reserved for this task         │
  └─────────────────────────────────────────────────────────────┘
                          │
                          ▼
                 cron/task_runner.py
                    1. unblock 'blocked' if deps done
                    2. fetch 'ready' (oldest first)
                    3. mark 'running', execute handler
                    4. mark 'done' or retry/'failed'
                    5. loop every 5s (daemon) or per cron tick
```

**Why not just cron:** Cron is time-based. The runner is event-based. It handles
"backtest H-A must wait until 3 wallet-enrich tasks finish" — something cron can't do.

## The agent harness — keeps Theia grounded (no "ngawang & halu")

The **harness** is a **deterministic supervisory wrapper** around the Hermes agent. The LLM
*proposes*; the harness *verifies and gates*. It is what guarantees the agent runs *sesuai*
— not drifting, not hallucinating. Four parts:

> **Status (2026-08-09): built, NOT yet wired — Phase 4.** `compute/harness.py` exists and is
> unit-tested, but it is not invoked in the live loop (`llm_shots`=0, `context_windows`=0,
> `budget_ledger`=0). Its grounding check is regex/keyword — a fabricated URL passes as a
> "source." The guarantees below are therefore **design intent, not current behavior**; today
> the agent self-applies the discipline (notes do cite sources), which is not the same as
> enforcement. Wire + harden this before it gates any money action.

```
  1. GROUNDING VERIFIER (anti-hallucination)
     · every knowledge note must cite a source (URL / on-chain tx / API response);
       an unsourced claim is REJECTED before it is saved
     · every P&L / screening number must come from a compute lib with logged inputs;
       an LLM-produced number is REJECTED  (verify-don't-speculate = enforced, not hoped)
  2. POLICY GATE (on-task + safe)
     · before any consequential action (open/close paper trade, promote a hypothesis,
       change a param) a deterministic policy returns ALLOW / DENY / ESCALATE — logged
     · edge cases go to the human (Hermes channel), never guessed
  3. WATCHDOG (liveness)
     · agent writes a heartbeat each loop; external watchdog restarts on crash/hang
     · on boot the reconciler rebuilds state FROM THE DB (never from memory) and resumes
     · idempotent, dedup-keyed tasks → a restart can't double-act
  4. BUDGET BREAKER (survival)
     · per-source spend tracked; ≥80% degrade to cache, 100% deny → shift to API-free work
```

**Core rule: the DB is the source of truth, never the model's memory.** Every asserted fact
and number is reconstructable from stored inputs, or it does not get to exist. That is the
whole answer to "tanpa ngawang & halu."

## Storage — SQLite for state, Obsidian for knowledge (split by data type)

Not either/or — **both**, split by what the data *is*:

```
  Decision rule:
    number touching money/decisions, or needs query/aggregate/transaction  → SQLite
    prose/knowledge/rationale a human reads & edits                         → Obsidian .md
    the two are linked by a shared stable id

  SQLite  (wallet-store-mcp — ONLY writer)     Obsidian .md  (second brain, Syncthing)
  ──────────────────────────────────────       ────────────────────────────────────────
  tokens · pools · price_snapshots             solana-fundamentals.md
  screens  (honeypot/wash/rug/scores)          dex-swap-mechanics.md
  hypotheses (rule spec + metrics)  ◄─[id]────► hypotheses/H-0007.md (idea·rationale·sources)
  backtests · paper_trades · trade_fills       token-lifecycle.md · failure-modes.md
  archives  (immutable ledger)                 (diagrams, [[wikilinks]])
  knowledge_index (mirror + sources) ─────────► points back at the .md files
  tasks · budget_ledger · heartbeat
```

Why the split: trades/screens/metrics **must** be structured to satisfy "no LLM math +
reconstructable + queryable expectancy" — markdown can't aggregate or transact reliably.
Knowledge is prose you read/sync — markdown + wikilinks + Obsidian's graph is the right
medium. SQLite keeps only an **index** of the notes (`knowledge_index`) so the agent can ask
"what do I know / what's still unverified" cheaply; the prose itself stays in Obsidian.

**Engine:** SQLite (OLTP + WAL) for all live writes; DuckDB optional, read-only, for
analytics scans over `archives`/`backtests`.

### Core tables (sketch)

```
tokens(mint PK, symbol, created_ts, source, first_seen_ts, status)
pools(pool_addr PK, mint FK, dex, amm_model, liquidity_usd,
      reserves_base, reserves_quote, price, updated_ts)
price_snapshots(pool_addr, ts, o,h,l,c, currency)      -- cached → API-free backtests
screens(mint FK, screen_ts, is_honeypot, buy_tax, sell_tax,
        mint_auth_live, freeze_auth_live, lp_locked, top10_share,
        wash_score, rug_score, screen_score, verdict,  PRIMARY KEY(mint,screen_ts))
hypotheses(id PK, title, note_path, rule_spec JSON, status,
           created_ts, best_expectancy, best_pf, best_winrate)   -- note_path → Obsidian
backtests(id PK, hypothesis_id FK, window_start, window_end, params JSON,
          n_trades, expectancy, profit_factor, win_rate, max_dd, ran_ts)
paper_trades(trade_id PK, mint FK, hypothesis_id FK, state,
             entry_ts, entry_price, size, stop_price, tp_ladder JSON, opened_by JSON)
trade_fills(trade_id FK, seq, kind, ts, qty, price,
            reserves_base, reserves_quote, base_fee, priority_fee, native_usd,
            gas_usd, slippage)                          -- full snapshot → reconstructable
archives(trade_id PK, mint, hypothesis_id, entry_ts, exit_ts,
         realized_pnl, roi, expectancy_contrib, exit_reason, created_ts)  -- immutable
knowledge_index(note_path PK, topic, status, sources JSON, last_updated)  -- mirrors Obsidian
llm_shots(shot_id PK, session_id, ts, skill, inputs, outputs, grounding_verdict,
           policy_decision, policy_reason, model, prompt_tokens, completion_tokens,
           total_tokens, cost_usd)                          -- per-LLM-shot audit log
context_windows(session_id PK, last_shot_id, summary,
                token_budget_remaining, shots_count, updated_ts)  -- rolling session state
tasks(id PK, type, payload JSON, state, deps JSON, budget_cost, attempts, result_ref)
                                                         -- persistent task queue (runner)
budget_ledger(source, window_start, spent, limit_)      -- the budget breaker
heartbeat(loop_ts, autonomy, note)                      -- the watchdog
```

Invariants: `wallet-store-mcp` is the only writer; `trade_fills` snapshots reserves + fees so
PnL/slippage/gas re-derive; `archives` are append-only; `hypotheses.note_path` ↔ Obsidian is
the bridge between the numeric and the prose halves.

## Subagent profiles

Theia runs under Hermes profile **`theia`** (system prompt in `profile/IDENTITY.md`).
Two specialized subagent profiles are *defined* for delegation (prompt files in `profile/`):

> **Status (2026-08-09): defined, NOT registered — Phase 6.** Only the `theia` profile is
> registered in Hermes; `theia-batch-enricher` and `theia-builder` exist as prompt files but
> are not wired as runnable profiles, and nothing dispatches to them (`_handle_delegate` is a
> stub). Delegation is a Phase-6 capability, switched on only when serial throughput demands it.

| Profile | Prompt File | Role | Model | Budget |
|---------|-------------|------|-------|--------|
| `theia` | `profile/IDENTITY.md` | Main orchestrator, judge qualitative | `deepseek-v4-flash` | Full |
| `theia-batch-enricher` | `profile/SUBAGENT_BATCH.md` | Batch IO worker (discovery, wallet PnL, labeling) | `deepseek-v4-pro` | 10K tokens, 20 turns |
| `theia-builder` | `profile/SUBAGENT_BUILDER.md` | Coding agent (compute libs, MCP tools, scripts) | `deepseek-v4-pro` | 40K tokens, 40 turns |

## The builder capability — Hermes subagent (Theia's coding agent)

Theia's own model is small (`deepseek-v4-flash`, low effort) — fine for orchestration and
judgment, weak for writing/maintaining tools. So **Theia never hand-codes tools with its own
model.** It **delegates all tool/program creation and maintenance to a Hermes subagent**
(profile `theia-builder`, model `deepseek-v4-pro` at high effort).

Division of labor: **Theia decides *what* tool is needed and *why* (the spec); the subagent
*builds and tests* it; the harness *verifies* it** by re-running the tests before anything is
trusted. Cheap orchestration model + strong coding model + deterministic verification — and it
respects the grounding rule: LLM-written code is a proposal until its tests pass.

Theia invokes the subagent headless and isolated via the Hermes subagent system:

```
hermes subagent run theia-builder \
  --task "<precise spec: inputs, outputs, and the tests it must pass>" \
  --worktree theia-build/<task>          # isolated git worktree — live code untouched until verified
  --max-turns 40
```

- Isolated worktree → the build happens in isolation; Theia merges only after tests pass.
- On max-turns cap hit the harness treats that as "needs a tighter spec or human review",
  never as success.

This is how new MCP tools, compute libs, and scripts get built *at runtime* without Theia's
weak model touching the code — and why the initial bundle (written here for your review) can be
handed to the subagent later for extension/maintenance.


