# Theia — Hermes profile bundle (review-before-deploy)

Everything here is written **locally for your review**. Nothing is deployed to the Hermes
server until you approve and we run `deploy/deploy.sh`. Theia is a **separate Hermes profile**
that **reads** your existing second brain at `/home/hermes/vault` (read-only) but keeps its own
identity, skills, MCP servers, and cron.

## What maps where on the server

| Local (here) | Server target | How it installs |
|---|---|---|
| `profile/IDENTITY.md` | Theia profile system-prompt | set as the Theia agent identity (exact wiring confirmed against `hermes` CLI at deploy) |
| `mcp/theia-*/manifest.yaml` (+ `server.py`) | `~/.hermes/theia/mcp/<name>/` | `hermes mcp install` from the manifest, **or** `deploy.sh` (copy → venv → register `mcp_servers.<name>` in `config.yaml`) |
| `compute/*.py` | `~/.hermes/theia/compute/` | copied; skills call them via `execute_code` |
| `skills/theia-*/SKILL.md` | `~/.hermes/skills/<name>/` | copied (same format as existing skills) |
| `cron/theia-jobs.json` | merged into `~/.hermes/cron/jobs.json` | additive merge, **backup first** |
| `deploy/env.additions` (names only) | appended to `~/.hermes/.env` | `deploy.sh` copies real values from local `.secret` (never printed) |

## Safety rules for deploy (non-negotiable)

- **Additive only.** New files use the `theia-*` namespace. The running `config.yaml`,
  `jobs.json`, and existing skills (incl. the 2895-run `knowledge-curator`) are **backed up
  before any edit** and only appended to.
- **Nothing goes live until smoke-tested** per layer (each MCP answers a probe; compute libs
  pass unit tests; one dry-run learn→screen→backtest cycle before enabling cron).
- **Theia writes to the vault only via `00-Inbox/_knowledge/`** (your `knowledge-curator`
  integrates it). It never edits `03-Areas/concepts/` directly.
- **`theia-store` is the only writer of the Theia DB** (`~/.hermes/theia/theia.db`).

## Layers (build order)

```
1. theia-store MCP  (DB — foundation)      ← this bundle starts here
2. data MCPs        (chainrpc/dexdata/birdeye/security)
3. compute libs     (expectancy/wilson/pnl/amm/gas/exit/screen)
4. skills           (learn/screen/hypothesis/backtest/evaluate/paper-trade/monitor/archive)
5. cron + profile activation + deploy.sh
```

## Builder capability — Hermes subagent

Theia does **not** hand-code tools with its own small model. It delegates building/maintaining
code (compute libs, MCP tools, scripts) to a **Hermes subagent** (`theia-builder` profile,
`deepseek-v4-pro` @ high) — then **verifies** the output with tests before trusting it.
Wired via the `theia-build-tool` skill; full contract in
[../ARCHITECTURE.md](../ARCHITECTURE.md) → "The builder capability". Division of labor:
**Theia specs → subagent builds → the harness verifies.**

See [../ARCHITECTURE.md](../ARCHITECTURE.md) for the full design and principles.
