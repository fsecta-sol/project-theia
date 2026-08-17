# Project Theia — Solana Memecoin Paper-Trading Agent

**Theia** is a Hermes-driven, single-VPS paper-trading agent for the **Solana memecoin market**. It hunts a *mechanical, retail-reachable* edge through survival screening, disciplined exits, and slow-timing selectivity — not speed.

> Target: **expectancy > 0 AND profit_factor > 1**, net of latency + fees.  
> Win-rate ≥ 50% is a milestone, never the goal.

---

## What Theia Is (and Isn't)

| What Theia Does | What Theia Does NOT Do |
|-----------------|------------------------|
| Discover new memecoin pools via free-tier APIs | ❌ Launch sniping / front-running / same-block fills |
| Screen tokens for rug/honeypot/wash-farm signals | ❌ Latency arbitrage / MEV (speed — we lose) |
| Form falsifiable hypotheses with testable `rule_spec` | ❌ Insider info / pre-announcement advantage |
| Backtest on stored history (API-free, deterministic) | ❌ Market-making at size / moving the book |
| Paper-trade with simulated fills (live gas + slippage) | ❌ Real money / signing keys anywhere |
| Learn Solana mechanics and document into second brain | ❌ LLM does money math (PnL, sizing, expectancy) |

---

## Architecture (4 Layers)

```
L4  HERMES AGENT (profile "theia")
    ├─ orchestrates via skills
    ├─ cron · subagents · FTS5 memory · execute_code · Hermes channels
    └─ harness: grounding verifier + policy gate + budget breaker

L3  SKILLS (playbooks — named, auditable procedures)
    ├─ theia-learn-solana      → research topic, write to vault
    ├─ theia-screen-token      → survival screening (rug/wash/honeypot)
    ├─ theia-form-hypothesis   → testable rule_spec + vault note
    ├─ theia-backtest           → API-free backtest on stored history
    ├─ theia-paper-trade        → simulated fill (AMM + gas + slippage)
    ├─ theia-monitor            → stops/TP/trail/time + emergency exit
    ├─ theia-archive            → FIFO PnL, immutable ledger
    ├─ theia-evaluate-expectancy → promote/reject gate
    ├─ theia-build-tool         → delegate coding to subagent
    ├─ theia-xscraper           → X.com research
    ├─ theia-harness            → grounding + policy verification
    └─ theia-delegate           → parallel subagent dispatch

L2  COMPUTE LIBS (deterministic math — execute_code only)
    ├─ expectancy.py, pnl.py (FIFO), wilson.py
    ├─ amm_sim.py, gas_sim.py, exit_engine.py
    ├─ screen_score.py, backtest_engine.py, harness.py
    └─ knowledge_graph.py (red-string auto-discovery)

L1  MCP SERVERS (data boundary — secrets, rate-limit, cache)
    ├─ theia-store      → SQLite (ONLY writer) — trades, screens, hypotheses
    ├─ theia-chainrpc   → Helius RPC — swaps, PnL, creator, gas
    ├─ theia-dexdata    → GeckoTerminal + DexScreener — pools, OHLCV
    ├─ theia-birdeye    → Birdeye free tier — token lists, top traders
    ├─ theia-security   → GoPlus — honeypot, mint/freeze, LP flags
    ├─ theia-xscraper   → X.com — profile lookup, tweets (keyless + cookie)
    ├─ theia-obsidian   → Vault gateway — read/write Obsidian notes
    └─ theia-webscraper → Tiered web fetch — curl_cffi → StealthyFetcher (CF bypass)

L0  INFRA
    └─ VPS · SQLite WAL · DiskCache · token-bucket · .env secrets · Syncthing
```

---

## Non-Negotiable Principles

1. **VERIFY, DON'T SPECULATE.** No fact without corroboration and a reconstructable source.
2. **THE LLM NEVER DOES MONEY MATH.** PnL, expectancy, sizing, screening → `compute/` libs only.
3. **PAPER ONLY.** No signing keys. Fills simulated off live reserves/gas/fees.
4. **STAY WITHIN FREE BUDGET.** All 8 MCPs use free API tiers. 28/29 tools verified with real calls.
5. **EARNED AUTONOMY.** Scope widens only on audited, out-of-sample results.

---

## Quick Start

### Run Tests

```bash
# All 59 golden tests (33 compute + 26 MCP/obsidian/webscraper)
python3 -m pytest compute/tests/ mcp/tests/test_mcp_servers.py \
  mcp/theia-obsidian/tests/test_obsidian.py \
  mcp/theia-webscraper/tests/test_webscraper.py -q
```

### Deploy to Hermes Server

```bash
# Dry run (prints plan, changes nothing)
./deploy/deploy.sh

# Deploy with backups
./deploy/deploy.sh --apply
```

**Deploy does:**
1. rsync repo root (`mcp/`, `compute/`, `profile/`, `cron/`) → `~/.hermes/theia/`
2. Copy skills → `~/.hermes/skills/`
3. Build per-MCP `.venv` + `pip install`
4. Append missing secrets from local `.secret` → `~/.hermes/.env`
5. Merge cron jobs (additive, backup first, all `enabled=false`)

**Manual post-deploy:**
- Register MCP servers: `hermes mcp install ~/.hermes/theia/mcp/<name>`
- Set Theia profile identity from `profile/IDENTITY.md`
- Smoke-test per layer → THEN enable cron jobs one at a time

---

## Workflow Loop

```
LEARN mechanics ──► DISCOVER pools ──► SCREEN tokens
       │                              │
       ▼                              ▼
FORM hypothesis ──► BACKTEST history ──► PAPER trade
       │                              │
       ▼                              ▼
EVALUATE expectancy ──► ARCHIVE ──► refine / repeat
```

---

## Project Structure

| Directory | What |
|-----------|------|
| `mcp/` | 8 MCP servers + `common/theia_net.py` (shared cache/rotator) |
| `compute/` | Deterministic libs + `tests/` (33 tests) |
| `skills/` | 12 skill playbooks (SKILL.md each) |
| `profile/` | Hermes identity prompts (theia, batch-enricher, builder) |
| `cron/` | Task runner + jobs schedule |
| `deploy/` | `deploy.sh` + `env.additions` |

---

## Secrets

Store in repo-root `.secret` (gitignored):
- `HELIUS_API_KEY=key1,key2,key3,key4` (4-key round-robin)
- `BIRDEYE_API_KEY`, `ALCHEMY_API_KEY`
- `GOPLUS_APP_KEY` / `GOPLUS_APP_SECRET`
- Optional: `X_AUTH_TOKEN` + `X_CT0` for X.com cookies

Deploy copies values to server `.env` without ever printing them.

---

## See Also

- [ARCHITECTURE.md](ARCHITECTURE.md) — full design, layer rules, storage split
- [CLAUDE.md](CLAUDE.md) — MCP table, compute libs, known limitations
