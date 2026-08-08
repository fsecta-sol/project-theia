# PROJECT THEIA — Architecture (v2, Hermes-driven)

> **Why v2.** The v1 design (old `design/*.md`) was built entirely on a *copy-trade*
> thesis: follow smart-money wallet buys. We tested that thesis first with a throwaway
> replay harness and it **failed** — no edge net of VPS latency + fees; the edge, if any,
> lives in the first seconds we can't reach. Details preserved in agent memory
> (`theia-replay-verdict`). v2 keeps the good *bones* (layered Hermes architecture, the
> non-negotiable principles, the free-tier data plumbing) and throws out the copy-trade
> strategy.

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
                        │           execute_code · Telegram interface           │
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

```
  1. GROUNDING VERIFIER (anti-hallucination)
     · every knowledge note must cite a source (URL / on-chain tx / API response);
       an unsourced claim is REJECTED before it is saved
     · every P&L / screening number must come from a compute lib with logged inputs;
       an LLM-produced number is REJECTED  (verify-don't-speculate = enforced, not hoped)
  2. POLICY GATE (on-task + safe)
     · before any consequential action (open/close paper trade, promote a hypothesis,
       change a param) a deterministic policy returns ALLOW / DENY / ESCALATE — logged
     · edge cases go to the human (Telegram), never guessed
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
Two specialized subagent profiles are registered for delegation:

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


