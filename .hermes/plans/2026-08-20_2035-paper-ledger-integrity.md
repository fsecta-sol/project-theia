# Paper-Trade Ledger Integrity & Forward-Pipeline Fixes Plan

> **For Hermes:** Use the `theia-build-tool` workflow and delegate non-trivial code changes to an isolated Theia builder worktree. This document is a plan only; no implementation is performed in plan mode.

**Goal:** Make every forward paper trade append-only, timestamp-consistent, fee-aware, and fully reconstructable from stored fills before collecting more validation data.

**Architecture:** Keep `/home/hermes/project-theia` as the source of truth. Centralize paper-trade ledger writes behind one validated path, have the pipeline record entry fills and the monitor record every exit fill, then derive archive P&L and expectancy from those fills through deterministic compute libraries. Legacy rows that lack evidence must remain preserved but explicitly marked non-reconstructable; never fabricate missing fills.

**Tech Stack:** Python 3.11, SQLite, `compute/exit_engine.py`, `compute/pnl.py`, `compute/expectancy.py`, `mcp/theia-store`, no-agent cron scripts, pytest in a project venv.

---

## Verified context

- DB: `/home/hermes/.hermes/theia/theia.db`
- Latest stored execution: 2026-08-18 07:19 WIB; no later cron execution is present in `executions.db`.
- Forward ledger: 3 paper trades, 3 archives, 0 `trade_fills`, 0 open trades.
- Deterministic evaluation of the 3 archived P&Ls: `n=3`, expectancy `-0.175015 SOL/trade`, profit factor `0`, total `-0.525045 SOL`, gate failed.
- `cron/wallet_monitor_v2.py` writes archives directly and uses `INSERT OR REPLACE`, bypassing the append-only `theia-store.close_trade()` path.
- `wallet_monitor_v2.py` stores `exit_ts=now` but `hold_secs=exit_engine.hold_secs`; the three historical rows therefore disagree with their timestamps.
- The deployed copies of `wallet_pipeline_v3.py` and `wallet_monitor_v2.py` match the repo by SHA-256.
- The current environment lacks `pytest`; install/use a project-local venv during implementation rather than relying on the Hermes runtime interpreter.

## Non-goals

- Do not alter or retroactively invent the three historical fills.
- Do not promote or reject the wallet hypothesis solely from these three trades.
- Do not add signing, live-money execution, or faster-than-retail execution paths.
- Do not change entry/exit strategy parameters until ledger correctness is independently verified.

---

## Priority 0 — contain and preserve evidence

### Task 1: Add an operational freeze and backup procedure

**Files:**
- Create: `mcp/theia-store/migrations/002_archive_integrity.sql`
- Create: `scripts/backup_theia_db.sh` (or document the exact SQLite backup command in `README.md`)
- Modify: `README.md` or `CLAUDE.md` with the temporary validation gate

**Steps:**
1. Before any migration, create a consistent SQLite backup using the SQLite backup API or `.backup`, not a raw copy of a live WAL database.
2. Document that no new forward paper trades should be accepted until the ledger-integrity smoke test passes.
3. Record the backup path, DB hash, schema version, and migration timestamp in the implementation log.

**Acceptance:** The backup opens read-only and contains the same row counts as the live DB; no historical row is modified.

### Task 2: Add explicit quality status for legacy archives

**Files:**
- Modify: `mcp/theia-store/schema.sql` (`archives` table)
- Create: `mcp/theia-store/migrations/002_archive_integrity.sql`
- Modify: `mcp/theia-store/server.py`
- Test: `mcp/tests/test_archive_integrity.py`

**Design:** Add fields such as `reconstructable INTEGER NOT NULL DEFAULT 0` and `integrity_error TEXT`. Mark the existing three rows as `reconstructable=0` with an honest reason such as `missing_trade_fills`; do not manufacture entry/exit fills from archive P&L.

**Acceptance:** Reports separate `legacy_non_reconstructable` rows from valid forward trades. Valid expectancy samples exclude legacy rows unless an explicit audit mode is requested.

---

## Priority 1 — one canonical, append-only ledger path

### Task 3: Make archive writes append-only and validate prerequisites

**Files:**
- Modify: `mcp/theia-store/server.py:record_fill, close_trade`
- Modify: `mcp/theia-store/schema.sql`
- Test: `mcp/tests/test_archive_integrity.py`

**Steps:**
1. Replace any archive `INSERT OR REPLACE` behavior with `INSERT OR IGNORE` or a deliberate duplicate error.
2. Make `close_trade()` refuse to mark a trade reconstructable unless it has at least one entry fill and one exit fill.
3. Validate `exit_ts >= entry_ts` and derive `hold_secs` only as `exit_ts - entry_ts` in one place.
4. Make close and archive insertion atomic in one transaction.
5. Keep already-archived rows immutable; a second close attempt must not overwrite P&L, reason, timestamps, or fees.

**Acceptance tests:**
- Missing fills are rejected or marked non-reconstructable without changing the trade to a valid archive.
- Duplicate close cannot change an existing archive.
- Negative duration is rejected.
- `hold_secs` always equals `exit_ts-entry_ts`.

### Task 4: Route no-agent scripts through the canonical ledger writer

**Files:**
- Modify: `cron/wallet_pipeline_v3.py`
- Modify: `cron/wallet_monitor_v2.py`
- Prefer: add a small shared module such as `compute/paper_ledger.py` rather than duplicating SQL
- Test: `compute/tests/test_paper_ledger.py`

**Steps:**
1. Remove direct archive SQL from `wallet_monitor_v2.py`.
2. Use a shared local DB helper or the deployed store interface consistently; do not mix incompatible state transitions (`closed` versus `archived`).
3. Ensure an entry transaction creates the `paper_trades` row and sequence-0 entry fill atomically.
4. Ensure an exit transaction creates all exit fills, closes the trade, and writes the archive atomically.
5. Preserve the no-agent, zero-LLM property.

**Acceptance:** A test run of the monitor cannot produce an archive row without the corresponding fills, and a crash before commit leaves the trade open rather than half-closed.

---

## Priority 1 — fill capture and correct timestamps

### Task 5: Record complete entry fills

**Files:**
- Modify: `cron/wallet_pipeline_v3.py:213-233`
- Modify: `cron/wallet_common.py` if reserve/fee snapshots need normalization
- Modify: `mcp/theia-store/server.py` only if the helper needs a transactional API
- Test: `compute/tests/test_paper_ledger.py`

**Steps:**
1. Record sequence `0`, kind `entry`, with the simulated token quantity, SOL/token execution price, timestamp, gas, slippage, native/USD snapshot, AMM model, and the exact reserve snapshot returned by the data source.
2. Do not fill missing reserve fields with fabricated values. If the source does not expose the required reserves, record the limitation and mark the trade non-reconstructable rather than claiming full reconstruction.
3. Store the exact cost inputs used by the entry calculation, including the already computed `entry_gas` and slippage.
4. Use the same units consistently: `qty` in base-token units, `price` in SOL per token, gas/slippage in SOL.

**Acceptance:** Every newly opened paper trade has exactly one valid entry fill before it can be considered eligible for monitoring.

### Task 6: Return and use the actual exit timestamp from `exit_engine`

**Files:**
- Modify: `compute/exit_engine.py`
- Modify: `cron/wallet_monitor_v2.py`
- Test: existing exit-engine tests, plus `compute/tests/test_exit_engine.py` if absent

**Steps:**
1. Extend `simulate_exit()` to return the timestamp of the final exit event, without breaking the existing `exits` contract unless tests are updated deliberately.
2. For a hard stop, TP, trail, follow exit, or time stop, use the triggering path row timestamp.
3. For the spot fallback, use the monitor observation timestamp because that is the actual observed exit price time.
4. Write `exit_ts` from the engine result, not from the later monitor `now`, and derive `hold_secs` from it.

**Acceptance:** Unit tests cover hard-stop, TP, trail, time-stop, path-end, and spot fallback. Every resulting archive satisfies `hold_secs == exit_ts-entry_ts`.

### Task 7: Record every exit fill, including partial exits

**Files:**
- Modify: `compute/exit_engine.py` if exit events need timestamps
- Modify: `cron/wallet_monitor_v2.py`
- Modify: `mcp/theia-store/server.py` or shared ledger helper
- Test: `compute/tests/test_paper_ledger.py`

**Steps:**
1. Convert each exit event into a fill with a unique increasing sequence number, kind (`hard_stop`, `tp`, `trail`, `time_stop`, or `follow_exit`), timestamp, quantity, price, gas, slippage, and reserve snapshot.
2. Handle partial TP exits using remaining quantity correctly; never record more base quantity sold than the entry quantity.
3. Record the final close only after all exit fills are committed.
4. If no valid price or reserve snapshot exists, keep the position open and emit an explicit operational error rather than archiving a fabricated result.

**Acceptance:** Fill quantities sum to the entry quantity within a documented tolerance; sequence numbers are unique and ordered; the archive cannot be created with zero exit fills.

---

## Priority 1 — deterministic P&L and expectancy

### Task 8: Recompute paper P&L from fills, not an inline formula

**Files:**
- Create or modify: `compute/paper_trade_pnl.py` (prefer a focused adapter around `compute/pnl.py`)
- Modify: `cron/wallet_monitor_v2.py`
- Modify: `mcp/theia-store/server.py`
- Test: `compute/tests/test_paper_trade_pnl.py`

**Steps:**
1. Convert stored entry/exit fills into the input shape required by `compute/pnl.py` or add a narrowly scoped fill-ledger adapter that uses the existing deterministic implementation.
2. Subtract recorded gas and slippage exactly once.
3. Compute archive `realized_pnl_sol`, ROI, and expectancy contribution from the deterministic result.
4. Have the archive writer store the calculation inputs or a stable reference so the result is reproducible.
5. Run `compute/expectancy.evaluate()` only over valid, reconstructable closed trades.

**Golden cases:**
- One entry plus one hard-stop exit.
- One entry plus two partial TP exits.
- Gas on entry and exit.
- Slippage on both sides.
- Missing reserve/fill data must fail honestly, not default to a made-up quote.

**Acceptance:** Re-running the calculation from DB fills reproduces the archive P&L exactly within a documented floating-point tolerance.

### Task 9: Add integrity and expectancy reporting

**Files:**
- Modify: `cron/wallet_report_v2.py`
- Modify: `mcp/theia-store/server.py` if a report query helper is needed
- Test: `cron/tests/test_wallet_report.py` or equivalent

**Report fields:** valid reconstructable trade count, legacy/non-reconstructable count, open count, missing-fill count, timestamp mismatch count, expectancy, profit factor, win rate, gross profit/loss, and data coverage window.

**Acceptance:** The daily report cannot present invalid legacy archives as a clean forward sample and cannot report a promotion-ready result for `n < 20`.

---

## Priority 2 — runtime health and deploy correctness

### Task 10: Add a cron freshness watchdog

**Files:**
- Modify: `cron/wallet_report_v2.py` or create `cron/pipeline_health.py`
- Modify: `cron/theia-jobs.json` if a no-agent health job is appropriate
- Modify: `deploy/deploy_sync.sh`
- Test: `cron/tests/test_pipeline_health.py`

**Checks:**
- Last successful pipeline, monitor, discovery, and report execution.
- Wrapper existence and executable bit.
- Runtime script hash equals the repo source hash.
- DB path is writable and has a recent heartbeat.
- A stale execution window generates an alert rather than silently claiming forward validation.

**Acceptance:** A simulated stale `executions.db` produces a visible alert; a healthy run produces no false alert.

### Task 11: Make deployment and runtime schema migration explicit

**Files:**
- Modify: `deploy/deploy_sync.sh`
- Create: migration runner or an idempotent `mcp/theia-store` migration mechanism
- Modify: `README.md` / `CLAUDE.md`

**Steps:**
1. Sync code and wrappers only after tests pass.
2. Apply the SQLite migration to `/home/hermes/.hermes/theia/theia.db` with a backup and verification.
3. Verify runtime/repo hashes after deployment.
4. Run one dry-run pipeline and one synthetic monitor/ledger smoke test against a temporary DB, not the live paper DB.
5. Re-enable forward collection only after all integrity checks pass.

**Acceptance:** Runtime schema version, script hashes, wrapper paths, and health checks are all recorded and verifiable.

---

## Test and validation sequence

1. Create a project-local venv and install the existing test requirements; do not alter the system Python.
2. Run the current relevant tests to establish a baseline.
3. Add failing unit tests for archive immutability, missing fills, timestamp consistency, partial exits, and P&L replay.
4. Implement each task in an isolated builder worktree, using `theia-build-tool`; review the diff before merge.
5. Run unit tests, then temporary-DB integration tests.
6. Run a synthetic end-to-end paper trade with deterministic fixture fills and verify the archive by replaying the DB fills.
7. Run the health check against the real runtime without opening a trade.
8. Only then migrate the live DB and resume the no-agent cron loop.
9. Treat the three existing rows as historical, non-reconstructable evidence; exclude them from the clean expectancy gate and retain their original P&L unchanged.

## Risks and open questions

- The current Gecko/DexScreener path may not expose raw base/quote reserves. This must be verified from the actual response schema before claiming reserve-level reconstruction; missing fields must cause an honest degraded status.
- Existing `compute/pnl.py` is wallet-swap oriented, while the paper ledger stores trade fills. The adapter must preserve FIFO and fee semantics rather than duplicating a second P&L implementation.
- A monitor observation can occur after the price-path event. The archive should distinguish `exit_event_ts` from `archived_at` if operational latency matters.
- The pipeline currently uses direct SQLite writes while a store MCP API already exists. Choose one canonical local transaction boundary and document it; avoid a network dependency that could make the no-agent guard fail.
- There is no current evidence of cron executions after 2026-08-18 07:19 WIB. Runtime health must be fixed and verified before interpreting the next sample as continuous forward testing.

## Definition of done

- No valid archive exists without complete entry/exit fill evidence.
- No archive can be overwritten.
- `hold_secs` exactly matches its timestamps.
- P&L replay from fills matches the stored archive result.
- Reports separate legacy invalid rows from valid forward trades.
- Cron freshness and runtime deployment are observable.
- A synthetic end-to-end paper trade passes all checks.
- Only after these gates pass may new forward trades count toward the minimum sample for expectancy evaluation.
