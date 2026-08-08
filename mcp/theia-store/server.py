#!/usr/bin/env python3
"""theia-store — the ONLY writer of Theia's SQLite DB (FastMCP stdio server).

Every P&L-affecting figure is stored with enough inputs to be re-derived; this
server just persists/queries — it never computes money math (that's the compute
libs). DB path: $THEIA_DB or ~/.hermes/theia/theia.db.
"""
from __future__ import annotations

import json
import os
import sqlite3
import time
from pathlib import Path

from mcp.server.fastmcp import FastMCP

DB_PATH = os.environ.get("THEIA_DB", str(Path.home() / ".hermes" / "theia" / "theia.db"))
SCHEMA = Path(__file__).parent / "schema.sql"
mcp = FastMCP("theia-store")


def _conn() -> sqlite3.Connection:
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    return c


def _init() -> None:
    c = _conn()
    # Base schema: all CREATE IF NOT EXISTS statements
    base = SCHEMA.read_text()
    # Split: run CREATE statements first, then ALTER statements separately
    creates = []
    alters = []
    for stmt in base.split(";"):
        s = stmt.strip()
        if not s or s.startswith("--"):
            continue
        if s.upper().startswith("ALTER TABLE"):
            alters.append(s)
        else:
            creates.append(s)
    for s in creates:
        c.execute(s + ";")
    for s in alters:
        try:
            c.execute(s + ";")
        except Exception:
            pass  # column already exists — safe to skip
    c.commit()
    c.close()


def _now() -> int:
    return int(time.time())


def _rows(cur) -> list[dict]:
    return [dict(r) for r in cur.fetchall()]


# --- tokens / pools / prices -------------------------------------------------
@mcp.tool()
def upsert_token(mint: str, symbol: str = "", name: str = "", created_ts: int = 0,
                 source: str = "", status: str = "candidate") -> dict:
    """Insert or update a token registry row."""
    c = _conn()
    c.execute("""INSERT INTO tokens(mint,symbol,name,created_ts,first_seen_ts,source,status)
                 VALUES(?,?,?,?,?,?,?)
                 ON CONFLICT(mint) DO UPDATE SET symbol=excluded.symbol,
                   name=excluded.name, status=excluded.status""",
              (mint, symbol, name, created_ts, _now(), source, status))
    c.commit(); c.close()
    return {"ok": True, "mint": mint}


@mcp.tool()
def get_token(mint: str) -> dict:
    c = _conn(); r = c.execute("SELECT * FROM tokens WHERE mint=?", (mint,)).fetchone(); c.close()
    return dict(r) if r else {}


@mcp.tool()
def upsert_pool(pool_addr: str, mint: str, dex: str = "", amm_model: str = "v2",
                liquidity_usd: float = 0, reserves_base: float = 0,
                reserves_quote: float = 0, price: float = 0) -> dict:
    c = _conn()
    c.execute("""INSERT INTO pools(pool_addr,mint,dex,amm_model,liquidity_usd,
                   reserves_base,reserves_quote,price,updated_ts)
                 VALUES(?,?,?,?,?,?,?,?,?)
                 ON CONFLICT(pool_addr) DO UPDATE SET liquidity_usd=excluded.liquidity_usd,
                   reserves_base=excluded.reserves_base, reserves_quote=excluded.reserves_quote,
                   price=excluded.price, updated_ts=excluded.updated_ts""",
              (pool_addr, mint, dex, amm_model, liquidity_usd, reserves_base,
               reserves_quote, price, _now()))
    c.commit(); c.close()
    return {"ok": True, "pool_addr": pool_addr}


@mcp.tool()
def record_price_snapshots(pool_addr: str, ohlcv: list, currency: str = "token") -> dict:
    """ohlcv = [[ts,o,h,l,c], ...]. Idempotent per (pool,ts,currency)."""
    c = _conn()
    c.executemany("""INSERT OR REPLACE INTO price_snapshots(pool_addr,ts,o,h,l,c,currency)
                     VALUES(?,?,?,?,?,?,?)""",
                  [(pool_addr, r[0], r[1], r[2], r[3], r[4], currency) for r in ohlcv])
    c.commit(); n = c.total_changes; c.close()
    return {"ok": True, "written": n}


@mcp.tool()
def get_price_path(pool_addr: str, ts_from: int, ts_to: int, currency: str = "token") -> list:
    c = _conn()
    cur = c.execute("""SELECT ts,o,h,l,c FROM price_snapshots
                       WHERE pool_addr=? AND currency=? AND ts>=? AND ts<=? ORDER BY ts""",
                    (pool_addr, currency, ts_from, ts_to))
    out = [list(r) for r in cur.fetchall()]; c.close()
    return out


# --- screens -----------------------------------------------------------------
@mcp.tool()
def record_screen(mint: str, verdict: str, is_honeypot: int = 0, buy_tax: float = 0,
                  sell_tax: float = 0, mint_auth_live: int = 0, freeze_auth_live: int = 0,
                  lp_locked: int = 0, top10_share: float = 0, wash_score: float = 0,
                  rug_score: float = 0, screen_score: float = 0, reject_reason: str = "") -> dict:
    c = _conn()
    c.execute("""INSERT OR REPLACE INTO screens(mint,screen_ts,is_honeypot,buy_tax,sell_tax,
                   mint_auth_live,freeze_auth_live,lp_locked,top10_share,wash_score,rug_score,
                   screen_score,verdict,reject_reason)
                 VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
              (mint, _now(), is_honeypot, buy_tax, sell_tax, mint_auth_live, freeze_auth_live,
               lp_locked, top10_share, wash_score, rug_score, screen_score, verdict, reject_reason))
    c.commit(); c.close()
    return {"ok": True, "mint": mint, "verdict": verdict}


@mcp.tool()
def get_latest_screen(mint: str) -> dict:
    c = _conn()
    r = c.execute("SELECT * FROM screens WHERE mint=? ORDER BY screen_ts DESC LIMIT 1",
                  (mint,)).fetchone(); c.close()
    return dict(r) if r else {}


# --- hypotheses / backtests --------------------------------------------------
@mcp.tool()
def upsert_hypothesis(id: str, title: str, note_path: str, rule_spec: dict,
                      status: str = "draft") -> dict:
    c = _conn()
    c.execute("""INSERT INTO hypotheses(id,title,note_path,rule_spec,status,created_ts)
                 VALUES(?,?,?,?,?,?)
                 ON CONFLICT(id) DO UPDATE SET title=excluded.title,
                   note_path=excluded.note_path, rule_spec=excluded.rule_spec,
                   status=excluded.status""",
              (id, title, note_path, json.dumps(rule_spec), status, _now()))
    c.commit(); c.close()
    return {"ok": True, "id": id}


@mcp.tool()
def get_hypothesis(id: str) -> dict:
    c = _conn(); r = c.execute("SELECT * FROM hypotheses WHERE id=?", (id,)).fetchone(); c.close()
    return dict(r) if r else {}


@mcp.tool()
def list_hypotheses(status: str = "") -> list:
    c = _conn()
    q = "SELECT * FROM hypotheses" + (" WHERE status=?" if status else "") + " ORDER BY created_ts DESC"
    cur = c.execute(q, (status,) if status else ()); out = _rows(cur); c.close()
    return out


@mcp.tool()
def record_backtest(id: str, hypothesis_id: str, window_start: int, window_end: int,
                    params: dict, n_trades: int, expectancy: float, profit_factor: float,
                    win_rate: float, max_dd: float) -> dict:
    """Persist a backtest result AND update the hypothesis' best metrics."""
    c = _conn()
    c.execute("""INSERT OR REPLACE INTO backtests(id,hypothesis_id,window_start,window_end,
                   params,n_trades,expectancy,profit_factor,win_rate,max_dd,ran_ts)
                 VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
              (id, hypothesis_id, window_start, window_end, json.dumps(params), n_trades,
               expectancy, profit_factor, win_rate, max_dd, _now()))
    c.execute("""UPDATE hypotheses SET best_expectancy=MAX(COALESCE(best_expectancy,-1e18),?),
                   best_pf=MAX(COALESCE(best_pf,0),?), best_winrate=MAX(COALESCE(best_winrate,0),?)
                 WHERE id=?""", (expectancy, profit_factor, win_rate, hypothesis_id))
    c.commit(); c.close()
    return {"ok": True, "id": id}


# --- paper trades / fills / archive -----------------------------------------
@mcp.tool()
def open_paper_trade(trade_id: str, mint: str, hypothesis_id: str, entry_ts: int,
                     entry_price: float, size_sol: float, stop_price: float = 0,
                     tp_ladder: list | None = None, opened_by: dict | None = None) -> dict:
    c = _conn()
    c.execute("""INSERT INTO paper_trades(trade_id,mint,hypothesis_id,state,entry_ts,
                   entry_price,size_sol,stop_price,tp_ladder,opened_by)
                 VALUES(?,?,?,'open',?,?,?,?,?,?)""",
              (trade_id, mint, hypothesis_id, entry_ts, entry_price, size_sol, stop_price,
               json.dumps(tp_ladder or []), json.dumps(opened_by or {})))
    c.commit(); c.close()
    return {"ok": True, "trade_id": trade_id}


@mcp.tool()
def record_fill(trade_id: str, seq: int, kind: str, ts: int, qty: float, price: float,
                reserves_base: float = 0, reserves_quote: float = 0, base_fee: float = 0,
                priority_fee: float = 0, native_usd: float = 0, gas_sol: float = 0,
                slippage: float = 0, amm_model: str = "v2") -> dict:
    """Record one fill with the full snapshot needed to re-derive PnL/gas/slippage."""
    c = _conn()
    c.execute("""INSERT OR REPLACE INTO trade_fills(trade_id,seq,kind,ts,qty,price,
                   reserves_base,reserves_quote,base_fee,priority_fee,native_usd,gas_sol,
                   slippage,amm_model) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
              (trade_id, seq, kind, ts, qty, price, reserves_base, reserves_quote, base_fee,
               priority_fee, native_usd, gas_sol, slippage, amm_model))
    c.commit(); c.close()
    return {"ok": True, "trade_id": trade_id, "seq": seq}


@mcp.tool()
def close_trade(trade_id: str, exit_ts: int, realized_pnl_sol: float, roi: float,
                expectancy_contrib: float, gas_sol_total: float, slippage_total: float,
                exit_reason: str) -> dict:
    """Mark a paper trade archived and write the immutable ledger row."""
    c = _conn()
    r = c.execute("SELECT entry_ts,mint,hypothesis_id FROM paper_trades WHERE trade_id=?",
                  (trade_id,)).fetchone()
    entry_ts = r["entry_ts"] if r else 0
    c.execute("""INSERT OR IGNORE INTO archives(trade_id,mint,hypothesis_id,entry_ts,exit_ts,
                   hold_secs,realized_pnl_sol,roi,expectancy_contrib,gas_sol_total,
                   slippage_total,exit_reason,created_ts)
                 VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
              (trade_id, r["mint"] if r else "", r["hypothesis_id"] if r else "", entry_ts,
               exit_ts, max(0, exit_ts - entry_ts), realized_pnl_sol, roi, expectancy_contrib,
               gas_sol_total, slippage_total, exit_reason, _now()))
    c.execute("UPDATE paper_trades SET state='archived' WHERE trade_id=?", (trade_id,))
    c.commit(); c.close()
    return {"ok": True, "trade_id": trade_id}


@mcp.tool()
def get_open_trades() -> list:
    c = _conn(); out = _rows(c.execute("SELECT * FROM paper_trades WHERE state!='archived'")); c.close()
    return out


# --- knowledge index / state / heartbeat / budget ---------------------------
@mcp.tool()
def index_note(note_path: str, topic: str = "", status: str = "draft",
               sources: list | None = None) -> dict:
    c = _conn()
    c.execute("""INSERT OR REPLACE INTO knowledge_index(note_path,topic,status,sources,last_updated)
                 VALUES(?,?,?,?,?)""",
              (note_path, topic, status, json.dumps(sources or []), _now()))
    c.commit(); c.close()
    return {"ok": True, "note_path": note_path}


@mcp.tool()
def set_state(k: str, v: str) -> dict:
    c = _conn()
    c.execute("INSERT OR REPLACE INTO kv_state(k,v,updated_ts) VALUES(?,?,?)", (k, v, _now()))
    c.commit(); c.close()
    return {"ok": True, "k": k}


@mcp.tool()
def get_state(k: str) -> dict:
    c = _conn(); r = c.execute("SELECT v FROM kv_state WHERE k=?", (k,)).fetchone(); c.close()
    return {"k": k, "v": r["v"] if r else None}


@mcp.tool()
def heartbeat(note: str = "") -> dict:
    c = _conn()
    c.execute("INSERT OR REPLACE INTO heartbeat(loop_ts,note) VALUES(?,?)", (_now(), note))
    c.commit(); c.close()
    return {"ok": True, "loop_ts": _now()}


@mcp.tool()
def budget_add(source: str, window_start: int, cost: int, limit_: int) -> dict:
    """Add `cost` to a source's spend in the current window; returns remaining."""
    c = _conn()
    c.execute("""INSERT INTO budget_ledger(source,window_start,spent,limit_) VALUES(?,?,?,?)
                 ON CONFLICT(source,window_start) DO UPDATE SET spent=spent+excluded.spent""",
              (source, window_start, cost, limit_))
    r = c.execute("SELECT spent,limit_ FROM budget_ledger WHERE source=? AND window_start=?",
                  (source, window_start)).fetchone()
    c.commit(); c.close()
    spent, lim = r["spent"], r["limit_"]
    return {"source": source, "spent": spent, "limit": lim, "remaining": lim - spent,
            "degrade": spent >= 0.8 * lim, "deny": spent >= lim}


# ── Phase 1 v2 tools ─────────────────────────────────────────────────────────


@mcp.tool()
def upsert_token_v2(mint: str, symbol: str = "", name: str = "",
                    creator_wallet: str = "", created_ts: int = 0,
                    graduation_status: str = "bonding", graduation_ts: int = 0,
                    death_reason: str = "", time_regime: str = "",
                    source: str = "") -> dict:
    """Insert/update token with v2 schema columns (creator, graduation, regime)."""
    c = _conn()
    c.execute("""INSERT INTO tokens(mint,symbol,name,creator_wallet,created_ts,
                   first_seen_ts,graduation_status,graduation_ts,death_reason,
                   time_regime,source,status)
                 VALUES(?,?,?,?,?,?,?,?,?,?,?,'candidate')
                 ON CONFLICT(mint) DO UPDATE SET
                   symbol=COALESCE(NULLIF(excluded.symbol,''),tokens.symbol),
                   creator_wallet=COALESCE(NULLIF(excluded.creator_wallet,''),tokens.creator_wallet),
                   graduation_status=excluded.graduation_status,
                   graduation_ts=excluded.graduation_ts,
                   death_reason=excluded.death_reason,
                   time_regime=COALESCE(NULLIF(excluded.time_regime,''),tokens.time_regime)""",
              (mint, symbol, name, creator_wallet, created_ts,
               _now(), graduation_status, graduation_ts, death_reason,
               time_regime, source))
    c.commit(); c.close()
    return {"ok": True, "mint": mint}


@mcp.tool()
def record_price_snapshot(mint: str, price_sol: float = 0, price_usd: float = 0,
                          volume_24h: float = 0, liquidity_usd: float = 0,
                          source: str = "dexscreener") -> dict:
    """Record mint-level price snapshot. ATH computed atomically."""
    c = _conn()
    c.execute("""INSERT INTO price_snapshots_v2(mint,ts,price_sol,price_usd,
                   volume_24h,liquidity_usd,ath_usd,source)
                 VALUES(?,?,?,?,?,?,?,?)
                 ON CONFLICT(mint,ts) DO UPDATE SET
                   price_sol=excluded.price_sol,
                   price_usd=excluded.price_usd,
                   volume_24h=excluded.volume_24h,
                   liquidity_usd=excluded.liquidity_usd,
                   ath_usd=MAX(COALESCE(price_snapshots_v2.ath_usd,0),
                               excluded.price_usd),
                   source=excluded.source""",
              (mint, _now(), price_sol, price_usd, volume_24h, liquidity_usd,
               price_usd, source))
    c.commit(); c.close()
    return {"ok": True, "mint": mint}


@mcp.tool()
def upsert_corpus(mint: str, symbol: str = "", name: str = "",
                  creator_wallet: str = "", launch_ts: int = 0,
                  graduation_status: str = "", graduation_ts: int = 0,
                  death_reason: str = "", time_regime: str = "",
                  final_price_usd: float = 0, final_liquidity_usd: float = 0) -> dict:
    """Upsert labeled token into the backtest corpus."""
    c = _conn()
    time_to_label = ((graduation_ts - launch_ts) / 3600.0) if (graduation_ts > 0 and launch_ts > 0) else None
    c.execute("""INSERT OR REPLACE INTO token_corpus(mint,symbol,name,creator_wallet,
                   launch_ts,first_seen_ts,graduation_status,graduation_ts,death_reason,
                   time_regime,ath_usd,final_price_usd,final_liquidity_usd,
                   time_to_label_hours,created_ts)
                 VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
              (mint, symbol, name, creator_wallet, launch_ts, _now(),
               graduation_status, graduation_ts, death_reason, time_regime,
               0, final_price_usd, final_liquidity_usd, time_to_label, _now()))
    c.commit(); c.close()
    return {"ok": True, "mint": mint}


@mcp.tool()
def get_corpus(graduation_status: str = "", ts_from: int = 0, ts_to: int = 0) -> list:
    """Query labeled token corpus."""
    c = _conn()
    q = "SELECT * FROM token_corpus WHERE 1=1"
    params = []
    if graduation_status:
        q += " AND graduation_status=?"
        params.append(graduation_status)
    if ts_from:
        q += " AND graduation_ts>=?"
        params.append(ts_from)
    if ts_to:
        q += " AND graduation_ts<=?"
        params.append(ts_to)
    q += " ORDER BY launch_ts"
    out = _rows(c.execute(q, params)); c.close()
    return out


@mcp.tool()
def update_graduation(mint: str, status: str, ts: int,
                      death_reason: str = "", final_price_usd: float = 0,
                      final_liquidity_usd: float = 0) -> dict:
    """Update graduation status on both tokens and corpus; compute time_to_label."""
    c = _conn()
    c.execute("""UPDATE tokens SET graduation_status=?, graduation_ts=?,
                   death_reason=? WHERE mint=?""",
              (status, ts, death_reason, mint))
    c.execute("""UPDATE token_corpus SET graduation_status=?, graduation_ts=?,
                   death_reason=?, final_price_usd=?, final_liquidity_usd=?,
                   time_to_label_hours = CASE WHEN launch_ts > 0 THEN (? - launch_ts) / 3600.0 END
                 WHERE mint=?""",
              (status, ts, death_reason, final_price_usd, final_liquidity_usd, ts, mint))
    c.commit(); c.close()
    return {"ok": True, "mint": mint, "status": status}


# ── Agent Harness tools ──────────────────────────────────────────────────────

@mcp.tool()
def record_llm_shot(shot_id: str, session_id: str, skill: str,
                    inputs: dict, outputs: dict, grounding_verdict: dict,
                    policy_decision: str, policy_reason: str,
                    model: str, prompt_tokens: int, completion_tokens: int,
                    total_tokens: int, cost_usd: float) -> dict:
    """Log one LLM shot with full grounding + policy snapshot."""
    c = _conn()
    c.execute("""INSERT OR REPLACE INTO llm_shots(
                   shot_id,session_id,ts,skill,inputs,outputs,grounding_verdict,
                   policy_decision,policy_reason,model,prompt_tokens,
                   completion_tokens,total_tokens,cost_usd)
                 VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
              (shot_id, session_id, _now(), skill, json.dumps(inputs),
               json.dumps(outputs), json.dumps(grounding_verdict),
               policy_decision, policy_reason, model, prompt_tokens,
               completion_tokens, total_tokens, cost_usd))
    c.commit(); c.close()
    return {"ok": True, "shot_id": shot_id, "policy": policy_decision}


@mcp.tool()
def get_session_shots(session_id: str, limit: int = 50) -> list:
    c = _conn()
    cur = c.execute("""SELECT * FROM llm_shots WHERE session_id=?
                        ORDER BY ts DESC LIMIT ?""", (session_id, limit))
    out = _rows(cur); c.close()
    return out


@mcp.tool()
def upsert_context_window(session_id: str, last_shot_id: str = "",
                          summary: str = "", token_budget_remaining: int = 0,
                          shots_count: int = 0) -> dict:
    c = _conn()
    c.execute("""INSERT OR REPLACE INTO context_windows(
                   session_id,last_shot_id,summary,token_budget_remaining,
                   shots_count,updated_ts)
                 VALUES(?,?,?,?,?,?)""",
              (session_id, last_shot_id, summary, token_budget_remaining,
               shots_count, _now()))
    c.commit(); c.close()
    return {"ok": True, "session_id": session_id}


@mcp.tool()
def get_context_window(session_id: str) -> dict:
    c = _conn()
    r = c.execute("SELECT * FROM context_windows WHERE session_id=?",
                  (session_id,)).fetchone(); c.close()
    return dict(r) if r else {}


# ── Knowledge Graph tools ──────────────────────────────────────────────────

@mcp.tool()
def add_knowledge_link(from_note: str, to_note: str, link_type: str = "related",
                       source: str = "", confidence: float = 0.5) -> dict:
    """Add a red-string link between two knowledge notes."""
    c = _conn()
    c.execute("""INSERT OR REPLACE INTO knowledge_links(
                   from_note,to_note,link_type,source,confidence,discovered_ts)
                 VALUES(?,?,?,?,?,?)""",
              (from_note, to_note, link_type, source, confidence, _now()))
    c.commit(); c.close()
    return {"ok": True, "from": from_note, "to": to_note, "type": link_type}


@mcp.tool()
def get_knowledge_links(note: str, direction: str = "both") -> list:
    """Get links for a note. direction = both|from|to."""
    c = _conn()
    if direction == "from":
        cur = c.execute("SELECT * FROM knowledge_links WHERE from_note=? ORDER BY confidence DESC",
                        (note,))
    elif direction == "to":
        cur = c.execute("SELECT * FROM knowledge_links WHERE to_note=? ORDER BY confidence DESC",
                        (note,))
    else:
        cur = c.execute("""SELECT * FROM knowledge_links
                           WHERE from_note=? OR to_note=?
                           ORDER BY confidence DESC""", (note, note))
    out = _rows(cur); c.close()
    return out


@mcp.tool()
def discover_knowledge_links(seed_note: str, max_hops: int = 2) -> list:
    """BFS traversal of the knowledge graph from a seed note."""
    c = _conn()
    visited = {seed_note}
    frontier = [seed_note]
    results = []
    for _ in range(max_hops):
        next_frontier = []
        for n in frontier:
            cur = c.execute("""SELECT * FROM knowledge_links
                               WHERE from_note=? OR to_note=?""", (n, n))
            for row in cur.fetchall():
                r = dict(row)
                other = r["to_note"] if r["from_note"] == n else r["from_note"]
                if other not in visited:
                    visited.add(other)
                    next_frontier.append(other)
                results.append(r)
        frontier = next_frontier
        if not frontier:
            break
    c.close()
    return results


if __name__ == "__main__":
    _init()
    mcp.run()
