-- Theia store — SQLite (OLTP + WAL). Owned exclusively by theia-store MCP.
-- Every number here is reconstructable from stored inputs. No black boxes.
-- USD unless a column says _sol/_native/_lamports. Times are UTC epoch seconds.

PRAGMA journal_mode=WAL;

-- token registry ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tokens (
  mint         TEXT PRIMARY KEY,
  symbol       TEXT,
  name         TEXT,
  created_ts   INTEGER,
  first_seen_ts INTEGER,
  source       TEXT,                 -- discovery source
  status       TEXT DEFAULT 'candidate'  -- candidate|screened|traded|archived|rejected
);

-- pool / market snapshot -----------------------------------------------------
CREATE TABLE IF NOT EXISTS pools (
  pool_addr      TEXT PRIMARY KEY,
  mint           TEXT REFERENCES tokens(mint),
  dex            TEXT,
  amm_model      TEXT,               -- v2|clmm|bonding
  liquidity_usd  REAL,
  reserves_base  REAL,
  reserves_quote REAL,
  price          REAL,
  updated_ts     INTEGER
);

-- cached price path → API-free backtests -------------------------------------
CREATE TABLE IF NOT EXISTS price_snapshots (
  pool_addr TEXT, ts INTEGER,
  o REAL, h REAL, l REAL, c REAL, currency TEXT DEFAULT 'token',
  -- v1.1: volume + mcap per candle (needed for volume-confirmed dip reversal)
  v REAL DEFAULT 0, mcap REAL DEFAULT 0,
  PRIMARY KEY (pool_addr, ts, currency)
);

-- screening results (honeypot/wash/rug), re-checked on entry ------------------
CREATE TABLE IF NOT EXISTS screens (
  mint TEXT REFERENCES tokens(mint),
  screen_ts INTEGER,
  is_honeypot INTEGER, buy_tax REAL, sell_tax REAL,
  mint_auth_live INTEGER, freeze_auth_live INTEGER,
  lp_locked INTEGER, top10_share REAL,
  wash_score REAL, rug_score REAL, screen_score REAL,
  verdict TEXT, reject_reason TEXT,
  PRIMARY KEY (mint, screen_ts)
);

-- strategy hypotheses (numbers half; prose half lives in the Obsidian vault) --
CREATE TABLE IF NOT EXISTS hypotheses (
  id TEXT PRIMARY KEY,              -- e.g. H-0007  (== note_path stem in vault)
  title TEXT,
  note_path TEXT,                  -- vault path to the rationale note
  rule_spec TEXT,                  -- JSON: the deterministic selection/screening rule
  status TEXT DEFAULT 'draft',     -- draft|backtesting|paper|promoted|rejected
  created_ts INTEGER,
  best_expectancy REAL, best_pf REAL, best_winrate REAL
);

-- backtest runs of a hypothesis over stored history --------------------------
CREATE TABLE IF NOT EXISTS backtests (
  id TEXT PRIMARY KEY,
  hypothesis_id TEXT REFERENCES hypotheses(id),
  window_start INTEGER, window_end INTEGER, params TEXT,
  n_trades INTEGER, expectancy REAL, profit_factor REAL,
  win_rate REAL, max_dd REAL, ran_ts INTEGER
);

-- live paper positions -------------------------------------------------------
CREATE TABLE IF NOT EXISTS paper_trades (
  trade_id TEXT PRIMARY KEY,
  mint TEXT REFERENCES tokens(mint),
  hypothesis_id TEXT REFERENCES hypotheses(id),
  state TEXT DEFAULT 'open',        -- open|scaling_out|closing|archived|discarded
  entry_ts INTEGER, entry_price REAL, size_sol REAL,
  stop_price REAL, tp_ladder TEXT, opened_by TEXT
);

-- every entry/exit fill — full snapshot so PnL/slippage/gas re-derive ---------
CREATE TABLE IF NOT EXISTS trade_fills (
  trade_id TEXT REFERENCES paper_trades(trade_id),
  seq INTEGER, kind TEXT,           -- entry|tp|stop|trail|time_stop|follow_exit
  ts INTEGER, qty REAL, price REAL,
  reserves_base REAL, reserves_quote REAL,
  base_fee REAL, priority_fee REAL, native_usd REAL,
  gas_sol REAL, slippage REAL, amm_model TEXT,
  PRIMARY KEY (trade_id, seq)
);

-- immutable, append-only ledger (written once on close) ----------------------
CREATE TABLE IF NOT EXISTS archives (
  trade_id TEXT PRIMARY KEY,
  mint TEXT, hypothesis_id TEXT,
  entry_ts INTEGER, exit_ts INTEGER, hold_secs INTEGER,
  realized_pnl_sol REAL, roi REAL, expectancy_contrib REAL,
  gas_sol_total REAL, slippage_total REAL,
 exit_reason TEXT, created_ts INTEGER,
 reconstructable INTEGER NOT NULL DEFAULT 0,
 integrity_error TEXT
 );

 CREATE TRIGGER IF NOT EXISTS archives_immutable_update
 BEFORE UPDATE ON archives
 BEGIN
 SELECT RAISE(ABORT, 'archives are immutable');
 END;

 CREATE TRIGGER IF NOT EXISTS archives_immutable_delete
 BEFORE DELETE ON archives
 BEGIN
 SELECT RAISE(ABORT, 'archives are append-only');
 END;

-- mirror of the second-brain notes (prose stays in Obsidian) -----------------
CREATE TABLE IF NOT EXISTS knowledge_index (
  note_path TEXT PRIMARY KEY,
  topic TEXT, status TEXT,          -- verified|draft|needs-why|needs-source
  sources TEXT, last_updated INTEGER
);

-- persistent task queue → 24/7 resumability ----------------------------------
CREATE TABLE IF NOT EXISTS tasks (
  id TEXT PRIMARY KEY,
  type TEXT, payload TEXT, state TEXT DEFAULT 'ready',  -- ready|blocked|running|done|failed
  deps TEXT, budget_cost INTEGER DEFAULT 0,
  attempts INTEGER DEFAULT 0, result_ref TEXT, updated_ts INTEGER
);

-- per-source budget breaker --------------------------------------------------
CREATE TABLE IF NOT EXISTS budget_ledger (
  source TEXT, window_start INTEGER,
  spent INTEGER DEFAULT 0, limit_ INTEGER,
  PRIMARY KEY (source, window_start)
);

-- watchdog heartbeat / generic kv state --------------------------------------
CREATE TABLE IF NOT EXISTS heartbeat (loop_ts INTEGER PRIMARY KEY, note TEXT);
CREATE TABLE IF NOT EXISTS kv_state (k TEXT PRIMARY KEY, v TEXT, updated_ts INTEGER);

CREATE INDEX IF NOT EXISTS idx_tokens_status ON tokens(status);
CREATE INDEX IF NOT EXISTS idx_screens_mint ON screens(mint, screen_ts);
CREATE INDEX IF NOT EXISTS idx_trades_state ON paper_trades(state);
CREATE INDEX IF NOT EXISTS idx_archives_hyp ON archives(hypothesis_id);
CREATE INDEX IF NOT EXISTS idx_backtests_hyp ON backtests(hypothesis_id);

-- Phase 1 schema additions (v2) -----------------------------------------------
-- SQLite ALTER TABLE ADD COLUMN is idempotent when wrapped in a try block.
-- We use a migration guard: if the column exists the statement fails silently
-- because the schema.sql is executed via execscript on first connect.

-- tokens: new columns for creator & graduation tracking
ALTER TABLE tokens ADD COLUMN creator_wallet TEXT;
ALTER TABLE tokens ADD COLUMN graduation_status TEXT DEFAULT 'bonding';
ALTER TABLE tokens ADD COLUMN graduation_ts INTEGER;
ALTER TABLE tokens ADD COLUMN death_reason TEXT;
ALTER TABLE tokens ADD COLUMN time_regime TEXT;

-- pools: launch timestamp
ALTER TABLE pools ADD COLUMN launch_ts INTEGER;

-- mint-level price snapshots (separate from pool-level OHLCV price_snapshots)
CREATE TABLE IF NOT EXISTS price_snapshots_v2 (
  mint TEXT, ts INTEGER,
  price_sol REAL, price_usd REAL,
  volume_24h REAL, liquidity_usd REAL,
  ath_usd REAL,
  source TEXT DEFAULT 'dexscreener',
  PRIMARY KEY (mint, ts)
);

-- labeled token corpus for backtest (graduated | dead)
CREATE TABLE IF NOT EXISTS token_corpus (
  mint TEXT PRIMARY KEY,
  symbol TEXT, name TEXT,
  creator_wallet TEXT,
  launch_ts INTEGER,
  first_seen_ts INTEGER,
  graduation_status TEXT,
  graduation_ts INTEGER,
  death_reason TEXT,
  time_regime TEXT,
  ath_usd REAL,
  final_price_usd REAL,
  final_liquidity_usd REAL,
  time_to_label_hours REAL,
  created_ts INTEGER
);
CREATE INDEX IF NOT EXISTS idx_corpus_status ON token_corpus(graduation_status);
CREATE INDEX IF NOT EXISTS idx_corpus_creator ON token_corpus(creator_wallet);

-- Phase 2 tables (schema defined, NOT populated in Phase 1)
CREATE TABLE IF NOT EXISTS early_holders (
  mint TEXT, wallet TEXT, amount_usd REAL, pct_of_supply REAL,
  first_seen_ts INTEGER, source TEXT DEFAULT 'dexscreener',
  PRIMARY KEY (mint, wallet)
);
CREATE TABLE IF NOT EXISTS social_mentions (
  mint TEXT, tweet_id TEXT, mention_ts INTEGER,
  username TEXT, text TEXT,
  PRIMARY KEY (mint, tweet_id)
);

-- ── Agent Harness: context management per LLM shot ─────────────────────────
CREATE TABLE IF NOT EXISTS llm_shots (
  shot_id TEXT PRIMARY KEY,
  session_id TEXT,
  ts INTEGER,
  skill TEXT,
  inputs TEXT,              -- JSON
  outputs TEXT,             -- JSON
  grounding_verdict TEXT,   -- JSON
  policy_decision TEXT,     -- ALLOW | DENY | ESCALATE
  policy_reason TEXT,
  model TEXT,
  prompt_tokens INTEGER,
  completion_tokens INTEGER,
  total_tokens INTEGER,
  cost_usd REAL
);
CREATE INDEX IF NOT EXISTS idx_llm_shots_session ON llm_shots(session_id, ts);
CREATE INDEX IF NOT EXISTS idx_llm_shots_skill ON llm_shots(skill, ts);

CREATE TABLE IF NOT EXISTS context_windows (
  session_id TEXT PRIMARY KEY,
  last_shot_id TEXT,
  summary TEXT,             -- compressed digest for cheap prompt context
  token_budget_remaining INTEGER,
  shots_count INTEGER DEFAULT 0,
  updated_ts INTEGER
);

-- ── Knowledge Graph: red-string links between topics ───────────────────────
CREATE TABLE IF NOT EXISTS knowledge_links (
  from_note TEXT,
  to_note TEXT,
  link_type TEXT DEFAULT 'related',  -- related | prerequisite | extends | contrasts
  source TEXT,                       -- how the link was discovered (url, scrape, manual)
  confidence REAL DEFAULT 0.5,       -- 0..1, higher = stronger connection
  discovered_ts INTEGER,
  PRIMARY KEY (from_note, to_note, link_type)
);
CREATE INDEX IF NOT EXISTS idx_klinks_to ON knowledge_links(to_note);
